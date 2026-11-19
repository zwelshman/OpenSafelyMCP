#!/usr/bin/env python3
"""OpenSafely MCP server.

Remote streamable-HTTP MCP server exposing OpenSAFELY documentation RAG
(Langflow/Astra DB) plus live project scraping from opensafely.org.

Transport: streamable HTTP at /mcp (default PORT 10000).
Health check: GET /health — separate from the MCP endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

import aiohttp
from bs4 import BeautifulSoup
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Line buffering so logs print instantly in cloud control panels
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


# =============================================================================
# Configuration (env-driven; nothing hardcoded)
# =============================================================================

API_TIMEOUT: float = float(os.environ.get("OPENSAFELY_TIMEOUT", "30"))
MAX_PAGES_DEFAULT: int = int(os.environ.get("OPENSAFELY_MAX_PAGES", "8"))
REQUEST_DELAY: float = float(os.environ.get("OPENSAFELY_REQUEST_DELAY", "1.0"))
CONTENT_LIMIT: int = int(os.environ.get("OPENSAFELY_CONTENT_LIMIT", "10000"))
BASE_URL = "https://www.opensafely.org"
JOBS_BASE_URL = "https://jobs.opensafely.org"
TINY_HEADERS = {"User-Agent": "Mozilla/5.0 OpenSafelyMCP/1.0"}


# =============================================================================
# Patch Context.report_progress to tolerate unexpected kwargs ("current")
# =============================================================================

_orig_report_progress = Context.report_progress


def _safe_report_progress(self: Context, *args: Any, **kwargs: Any) -> None:
    if "current" in kwargs and "progress" not in kwargs:
        kwargs["progress"] = kwargs.pop("current")
    try:
        _orig_report_progress(self, *args, **kwargs)
    except Exception:
        pass  # progress reporting must never crash tool execution


Context.report_progress = _safe_report_progress


# =============================================================================
# Server registration
# =============================================================================

# Explicit transport security: the SDK auto-enables DNS rebinding protection
# with localhost-only allowed_hosts when transport_security is None AND the
# default host is 127.0.0.1 — which 421s production Host headers (Render's
# opensafelymcp.onrender.com) and rejected remote clients.
# Configured explicitly here instead: protection on, hosts/origins from env.
mcp: FastMCP = FastMCP(
    "OpenSafely-Rag-Retrieve",
    instructions=(
        "Tools for OpenSAFELY ehrQL documentation and live project data. "
        "Use query_knowledge_base for general questions about OpenSAFELY/ehrQL, "
        "search_docs_by_filename when you know the target document filename, "
        "get_doc_section_content for topic+section focused retrieval, and the "
        "scraper tools for live project/GitHub workspace discovery."
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=(
            os.environ.get("MCP_ENABLE_DNS_REBINDING_PROTECTION", "true").lower()
            not in ("false", "0", "no", "off")
        ),
        allowed_hosts=os.environ.get("MCP_ALLOWED_HOSTS", "opensafelymcp.onrender.com").split(","),
        allowed_origins=os.environ.get("MCP_ALLOWED_ORIGINS", "").split(","),
    ),
)


# =============================================================================
# Tool schemas / dataclasses
# =============================================================================

@dataclass
class DocChunk:
    """A single documentation chunk extracted from an HTML/Markdown page."""

    heading: str
    content: str
    code_blocks: List[str]
    metadata: Dict[str, str]


@dataclass
class ProjectListItem:
    """Basic project info from the list page."""

    url: str
    title: str
    organisation: str
    project_type: str
    date: str
    tags: List[str]


@dataclass
class OpenSafelyProject:
    """Complete OpenSAFELY project information."""

    project_id: str
    title: str
    url: str
    organisation: str
    project_type: str
    date: str
    tags: List[str]
    description: str
    full_content: str
    study_lead: str
    researchers: List[str]
    workspaces: List[Dict[str, str]]


# =============================================================================
# Langflow RAG / knowledge base helpers
# =============================================================================

def _build_langflow_tweaks() -> Dict[str, Dict[str, Any]]:
    """Map env vars into Langflow component config tweaks."""
    return {
        "ext:openrouter:OpenRouterComponent@official-Lbbp3": {
            "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
            "load_from_db": False,
        },
        "ext:datastax:AstraDBVectorStoreComponent@official-zF58p": {
            "token": os.environ.get("ASTRA_DB_APPLICATION_TOKEN", ""),
            "api_endpoint": os.environ.get("ASTRA_DB_API_ENDPOINT", ""),
            "load_from_db": False,
        },
    }


def _extract_langflow_message(result: Any) -> Optional[str]:
    """Pull the first message text out of a Langflow run result, if present."""
    if not result or not isinstance(result, list):
        return None
    for flow_output in result:
        outputs = getattr(flow_output, "outputs", None)
        for output in outputs or []:
            results = getattr(output, "results", None)
            if results and "message" in results:
                message = results["message"]
                text = getattr(message, "text", None)
                if text:
                    return text
    return None


# =============================================================================
# Documentation chunker (used to build the Astra DB corpus offline)
# =============================================================================

def chunk_documentation(
    html_or_markdown: str, source_url: str = ""
) -> List[DocChunk]:
    """Chunk an OpenSAFELY documentation page into heading-based sections.

    Extracts headings (h1-h6 in HTML, # headings in Markdown) and groups the
    content that follows each heading until the next heading of the same or
    higher level. Code blocks are preserved separately for metadata tagging.

    Args:
        html_or_markdown: Raw HTML or Markdown text of a documentation page.
        source_url: Optional source URL for provenance metadata.

    Returns:
        A list of DocChunk objects, one per heading section.
    """
    chunks: List[DocChunk] = []

    stripped = html_or_markdown.lstrip()
    is_html = stripped.startswith("<") or "<html" in stripped[:200].lower()

    if is_html:
        soup = BeautifulSoup(html_or_markdown, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

        for heading in headings:
            heading_text = heading.get_text(strip=True)
            level = int(heading.name[1])

            content_parts: List[str] = []
            code_blocks: List[str] = []

            for sibling in heading.next_siblings:
                if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    if int(sibling.name[1]) <= level:
                        break
                if getattr(sibling, "get_text", None):
                    text = sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                if getattr(sibling, "find_all", None):
                    for code in sibling.find_all(["code", "pre"]):
                        code_text = code.get_text(strip=True)
                        if code_text and code_text not in code_blocks:
                            code_blocks.append(code_text)

            chunks.append(
                DocChunk(
                    heading=heading_text,
                    content="\n".join(content_parts),
                    code_blocks=code_blocks,
                    metadata={"source_url": source_url, "level": str(level)},
                )
            )
    else:
        lines = html_or_markdown.splitlines()
        current_heading = ""
        current_level = 0
        current_content: List[str] = []
        current_code: List[str] = []
        in_code_block = False
        code_buffer: List[str] = []

        def flush() -> None:
            nonlocal current_content, current_code
            if current_heading or current_content:
                chunks.append(
                    DocChunk(
                        heading=current_heading,
                        content="\n".join(current_content).strip(),
                        code_blocks=list(current_code),
                        metadata={
                            "source_url": source_url,
                            "level": str(current_level),
                        },
                    )
                )
            current_content = []
            current_code = []

        for line in lines:
            if line.startswith("```") or line.startswith("~~~"):
                if not in_code_block:
                    in_code_block = True
                    code_buffer = []
                else:
                    in_code_block = False
                    block_text = "\n".join(code_buffer).strip()
                    if block_text and block_text not in current_code:
                        current_code.append(block_text)
                continue
            if in_code_block:
                code_buffer.append(line)
                continue

            heading_match = next(
                (m for m in ("# ", "## ", "### ", "#### ", "##### ", "###### ")
                 if line.startswith(m)),
                None,
            )

            if heading_match is not None:
                if current_heading:
                    flush()
                current_heading = line[len(heading_match):].strip()
                current_level = len(heading_match) - 1
            else:
                current_content.append(line)

        flush()

    return chunks


# =============================================================================
# MCP tools — knowledge base (Langflow RAG)
# =============================================================================

@mcp.tool(annotations={"readOnlyHint": True})
def query_knowledge_base(question: str) -> str:
    """Search the Astra DB RAG knowledge base for answers about OpenSAFELY/ehrQL.

    Use for general questions about OpenSAFELY, ehrQL, study design, codelists,
    dummy data generation, and other documentation topics. Semantic search finds
    relevant documentation chunks; an LLM generates the answer.

    Args:
        question: Natural language question (e.g. "How do I define a dataset
            in ehrQL?", "What are the required steps in project.yaml?").

    Returns:
        Answer text from the RAG pipeline over OpenSAFELY documentation.
    """
    try:
        from langflow.load import run_flow_from_json

        if not os.path.exists("flow.json"):
            return "Error: flow.json layout configuration file is missing from the server root directory."

        print(f"INFO: Executing Langflow flow for question: {question}")
        result = run_flow_from_json(
            flow="flow.json",
            input_value=question,
            tweaks=_build_langflow_tweaks(),
        )

        message = _extract_langflow_message(result)
        if message:
            return message
        return "No response generated by the Langflow pipeline."

    except Exception as exc:  # noqa: BLE001 — tool boundary; string errors are MCP-visible
        print(f"ERROR: Runtime execution failure: {exc}", file=sys.stderr)
        return f"Error executing Langflow graph: {exc}"


@mcp.tool(annotations={"readOnlyHint": True})
def search_docs_by_filename(filename: str) -> str:
    """Retrieve full documentation text for a specific file from the vector store.

    Use when general queries fail to pull direct file contents. Craft question
    targets a single filename or path in the ehrQL documentation corpus.

    Args:
        filename: Filename or path to retrieve (e.g. 'ethnicity.md',
            'how-to/ethnicity', 'dataset-definition.md', 'codelists.md').

    Returns:
        Full documentation text for the requested file.
    """
    target_question = f"Show me the full documentation text inside the file {filename}"
    print(f"INFO: Querying Vector Store for explicit file content: {filename}")
    return query_knowledge_base(target_question)


@mcp.tool(annotations={"readOnlyHint": True})
def get_doc_section_content(topic: str, section_header: Optional[str] = None) -> str:
    """Fetch a block of documentation from Astra DB for a topic, optionally by section.

    Use when you need detailed documentation on a specific topic and want to
    focus on a particular section of it.

    Args:
        topic: Topic to search (e.g. 'ethnicity definition', 'dataset
            definition', 'codelist usage', 'dummy data generation').
        section_header: Optional section header to focus on (e.g. 'Creating
            variables', 'Filtering patients', 'Importing codelists').

    Returns:
        Detailed documentation text for the topic and section.
    """
    refined_query = f"Provide all detailed documentation regarding {topic}"
    if section_header:
        refined_query += f" specifically focusing on the section: {section_header}"

    print(f"INFO: Fetching deep topic content for: {refined_query}")
    return query_knowledge_base(refined_query)


# =============================================================================
# Templates resource
# =============================================================================

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))


@mcp.resource("codebase://templates/{script_name}.py")
def get_any_template(script_name: str) -> str:
    """Fetch a reference script from the codebase templates directory."""
    target_path = os.path.abspath(os.path.join(TEMPLATES_DIR, f"{script_name}.py"))

    # Prevent directory traversal (e.g. script_name = "../../etc/passwd")
    if not target_path.startswith(TEMPLATES_DIR + os.sep) and target_path != TEMPLATES_DIR:
        return "Access denied: Invalid template location."

    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()

    return f"Template '{script_name}' not found."


# =============================================================================
# Async scraping helpers (opensafely.org / jobs.opensafely.org)
# =============================================================================

async def fetch_workspace_details(
    session: aiohttp.ClientSession, jobs_url: str
) -> List[Dict[str, str]]:
    """Fetch workspace details from a jobs.opensafely.org project page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    workspaces: List[Dict[str, str]] = []

    try:
        async with session.get(
            jobs_url, headers=headers, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as response:
            if response.status != 200:
                return workspaces

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            workspaces_header = soup.find(
                "h2", string=lambda text: text and "Workspaces" in text
            )
            if not workspaces_header:
                return workspaces

            workspaces_list = workspaces_header.find_next("ul", role="list")
            if not workspaces_list:
                return workspaces

            for li in workspaces_list.find_all("li", recursive=False):
                workspace_info: Dict[str, str] = {}

                workspace_link = li.find("a", href=True)
                if workspace_link:
                    workspace_info["name"] = workspace_link.get_text(strip=True)
                    workspace_info["workspace_url"] = (
                        JOBS_BASE_URL + workspace_link["href"]
                    )

                # GitHub repo / branch / created date live in dd elements
                # with sr-only dt labels
                for dd in li.find_all("dd"):
                    dt = dd.find_previous("dt")
                    if dt:
                        label = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)

                        if "GitHub repository" in label:
                            workspace_info["github_repo"] = value
                        elif "Git branch" in label:
                            workspace_info["branch"] = value
                        elif "Created at" in label:
                            workspace_info["created_at"] = value

                if workspace_info:
                    workspaces.append(workspace_info)

            return workspaces

    except Exception as exc:  # noqa: BLE001 — log-and-continue for scraper resilience
        print(f"Error fetching workspace details from {jobs_url}: {exc}")
        return workspaces


async def fetch_projects_list_page(
    session: aiohttp.ClientSession, page: int
) -> List[ProjectListItem]:
    """Fetch a single page of the projects list and return project info."""
    url = f"{BASE_URL}/projects/" if page == 1 else f"{BASE_URL}/projects/page/{page}/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as response:
            if response.status != 200:
                return []

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")
            projects: List[ProjectListItem] = []

            for link in soup.find_all("a", href=True):
                href = link["href"]
                if href.startswith(f"{BASE_URL}/project/") and href.endswith("/"):
                    container = link.find_parent("li")
                    if container:
                        normalized_text = " ".join(container.get_text(strip=True).split())
                        title = link.get_text(strip=True)

                        organisation = ""
                        project_type = ""
                        org_match = re.search(
                            r"(Research project|Service evaluation project|Short data report project)"
                            r"\s+run by\s+([^.]+)\.",
                            normalized_text,
                        )
                        if org_match:
                            project_type = org_match.group(1)
                            organisation = org_match.group(2).strip()

                        date = ""
                        date_match = re.search(
                            r"(January|February|March|April|May|June|July|August|"
                            r"September|October|November|December)\s+\d{4}",
                            normalized_text,
                        )
                        if date_match:
                            date = date_match.group(0)

                        tags = ["COVID-19"] if "COVID-19" in normalized_text else []

                        projects.append(
                            ProjectListItem(
                                url=href,
                                title=title,
                                organisation=organisation,
                                project_type=project_type,
                                date=date,
                                tags=tags,
                            )
                        )

            return projects

    except Exception as exc:  # noqa: BLE001 — log-and-continue for scraper resilience
        print(f"Error fetching projects page {page}: {exc}")
        return []


async def fetch_project_details(
    session: aiohttp.ClientSession, project_item: ProjectListItem
) -> Optional[OpenSafelyProject]:
    """Fetch detailed information for a single project from its detail page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        async with session.get(
            project_item.url, headers=headers, timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)
        ) as response:
            if response.status != 200:
                return None

            html = await response.text()
            soup = BeautifulSoup(html, "html.parser")

            project_id = project_item.url.rstrip("/").split("/")[-1]

            # Title: prefer og:title meta tag, fall back to h1
            title = project_item.title or project_id.title()
            og_title = soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"]
            else:
                h1 = soup.find("h1")
                if h1:
                    title = h1.get_text(strip=True)

            # Description: og:description or meta description
            description = ""
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                description = og_desc["content"]
            else:
                meta_desc = soup.find("meta", attrs={"name": "description"})
                if meta_desc and meta_desc.get("content"):
                    description = meta_desc["content"]

            # Full content: main or article element text
            full_content = ""
            main = soup.find("main")
            if main:
                full_content = main.get_text(strip=True)
            else:
                article = soup.find("article")
                if article:
                    full_content = article.get_text(strip=True)

            # Study lead: "Study lead(s): Name..." followed by other labels or end
            study_lead = ""
            researchers: List[str] = []
            lead_match = re.search(
                r"Study leads?:\s*(.+?)"
                r"(?:Organisation:|Project type:|Start date:|Topic area:|Date of approval:|$)",
                full_content,
            )
            if lead_match:
                study_lead = lead_match.group(1).strip()
            else:
                lines = full_content.split("\n")
                for i, line in enumerate(lines):
                    if "Study lead:" in line or "Study leads:" in line:
                        for j in range(i + 1, min(i + 5, len(lines))):
                            if lines[j].strip():
                                study_lead = lines[j].strip()
                                break
                        break

            # Researchers: h2#researchers-title section followed by ul/li
            h2 = soup.find("h2", {"id": "researchers-title"})
            if h2:
                grandparent = h2.parent.parent if h2.parent else None
                if grandparent:
                    for sibling in grandparent.find_next_siblings():
                        ul = sibling.find("ul")
                        if ul:
                            for li in ul.find_all("li"):
                                name = li.get_text(strip=True)
                                if name:
                                    researchers.append(name)
                            break

            # Discover jobs.opensafely.org URL, then workspace info
            jobs_url = None
            for link in soup.find_all("a", href=True):
                if "jobs.opensafely.org" in link["href"]:
                    jobs_url = link["href"]
                    break

            workspaces: List[Dict[str, str]] = []
            if jobs_url:
                workspaces = await fetch_workspace_details(session, jobs_url)

            return OpenSafelyProject(
                project_id=project_id,
                title=title,
                url=project_item.url,
                organisation=project_item.organisation,
                project_type=project_item.project_type,
                date=project_item.date,
                tags=project_item.tags,
                description=description,
                full_content=full_content[:CONTENT_LIMIT],
                study_lead=study_lead,
                researchers=researchers,
                workspaces=workspaces,
            )

    except Exception as exc:  # noqa: BLE001 — log-and-continue for scraper resilience
        print(f"Error fetching project {project_item.url}: {exc}")
        return None


# =============================================================================
# MCP tools — project scraping
# =============================================================================

@mcp.tool(annotations={"readOnlyHint": True})
async def scrape_opensafely_projects(
    max_pages: int = MAX_PAGES_DEFAULT,
    delay_between_requests: float = REQUEST_DELAY,
) -> str:
    """Scrape all OpenSAFELY projects from https://www.opensafely.org/projects/.

    Extracts project details from paginated pages (1-8 by default). Each
    project includes ID, title, URL, organisation, type, date, tags,
    description, full content, study lead, researchers, and workspace info
    with GitHub repositories.

    Args:
        max_pages: Max pages to scrape (default 8). Each page lists many projects.
        delay_between_requests: Delay in seconds between requests (default 1.0),
            to stay respectful of the server.

    Returns:
        JSON string containing project data including workspace GitHub repo details.
    """
    all_projects: List[OpenSafelyProject] = []
    all_project_urls = set()

    connector = aiohttp.TCPConnector(limit=5)
    timeout = aiohttp.ClientTimeout(total=max(API_TIMEOUT, 60))

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Collect all project URLs from list pages first
        for page in range(1, max_pages + 1):
            print(f"Fetching projects list page {page}...")
            urls = await fetch_projects_list_page(session, page)
            new_urls = [u for u in urls if u.url not in all_project_urls]
            all_project_urls.update(u.url for u in new_urls)

            if new_urls:
                print(f"  Found {len(new_urls)} new project URLs (total: {len(all_project_urls)})")

            if page < max_pages:
                await asyncio.sleep(delay_between_requests)

        # Fetch full details per project URL
        print(f"Fetching details for {len(all_project_urls)} projects...")
        detail_items = [
            ProjectListItem(url=u, title="", organisation="",
                            project_type="", date="", tags=[])
            for u in sorted(all_project_urls)
        ]
        for i, item in enumerate(detail_items):
            print(f"  [{i + 1}/{len(detail_items)}] {item.url}")
            project = await fetch_project_details(session, item)
            if project:
                all_projects.append(project)
            await asyncio.sleep(delay_between_requests)

    projects_data = [asdict(p) for p in all_projects]

    return json.dumps({
        "total_projects": len(projects_data),
        "pages_scraped": max_pages,
        "projects": projects_data,
    }, indent=2)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_opensafely_project_details(project_url: str) -> str:
    """Get detailed info for a specific OpenSAFELY project, including workspaces with GitHub repos.

    Discovers the associated jobs.opensafely.org page and extracts workspace
    GitHub repository names, branches, and creation dates.

    Args:
        project_url: Project URL (e.g. 'https://www.opensafely.org/project/pos-2026-3018/').

    Returns:
        JSON string with complete project details including workspaces.
    """
    project_item = ProjectListItem(
        url=project_url, title="", organisation="",
        project_type="", date="", tags=[],
    )

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=API_TIMEOUT)) as session:
            project = await fetch_project_details(session, project_item)
            if project:
                return json.dumps(asdict(project), indent=2)
            return json.dumps({"error": "Failed to fetch project details"})

    except Exception as exc:  # noqa: BLE001 — tool boundary; string errors are MCP-visible
        return json.dumps({"error": str(exc)})


# =============================================================================
# Health check (custom route, separate from the MCP path)
# =============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    """Health check endpoint for hosting platforms (Render)."""
    return JSONResponse({
        "status": "healthy",
        "service": "OpenSafely-Rag-Retrieve-MCP",
        "mcp_endpoint": "/mcp",
    })


# =============================================================================
# Main entry point — streamable HTTP transport
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    host = os.environ.get("HOST", "0.0.0.0")
    # Set before run() — settings are consumed when the server binds, and
    # run_streamable_http_async reads host/port from mcp.settings at serve time.
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
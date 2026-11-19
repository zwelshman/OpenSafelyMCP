#!/usr/bin/env python3
"""
OpenSafely MCP Server - Refactored for Best Practices

This server provides Model Context Protocol (MCP) tools for accessing
OpenSAFELY documentation and project information via a Langflow-powered
RAG system and web scraping capabilities.
"""

import os
import sys
import json
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

# Force line buffering for immediate log output in cloud environments
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Third-party imports
import uvicorn
import aiohttp
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# Local imports (if any would go here)


# =============================================================================
# DATA MODELS
# =============================================================================

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
    workspaces: List[Dict[str, str]]  # name, github_repo, branch, created_at, workspace_url


@dataclass
class WorkspaceInfo:
    """Workspace information from jobs.opensafely.org."""
    name: str
    github_repo: str
    branch: str
    created_at: str
    workspace_url: str


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
class DocChunk:
    """A documentation chunk extracted from HTML/Markdown."""
    heading: str
    content: str
    code_blocks: List[str]
    metadata: Dict[str, str]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def chunk_documentation(html_or_markdown: str, source_url: str = "") -> List[DocChunk]:
    """
    Chunk an OpenSAFELY documentation page into heading-based sections.
    
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
    
    # Detect whether the input looks like HTML.
    stripped = html_or_markdown.lstrip()
    is_html = stripped.startswith("<") or "<html" in stripped[:200].lower()

    if is_html:
        soup = BeautifulSoup(html_or_markdown, "html.parser")
        
        # Remove script/style elements that would pollute text content.
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        
        # Collect heading elements in document order.
        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        
        for idx, heading in enumerate(headings):
            heading_text = heading.get_text(strip=True)
            level = int(heading.name[1])
            
            # Gather content until the next heading of the same or higher level.
            content_parts: List[str] = []
            code_blocks: List[str] = []
            
            for sibling in heading.next_siblings:
                if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                    sibling_level = int(sibling.name[1])
                    if sibling_level <= level:
                        break
                if getattr(sibling, "get_text", None):
                    text = sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                # Capture code blocks within this section.
                if getattr(sibling, "find_all", None):
                    for code in sibling.find_all(["code", "pre"]):
                        code_text = code.get_text(strip=True)
                        if code_text and code_text not in code_blocks:
                            code_blocks.append(code_text)
            
            content = "\n".join(content_parts)
            chunks.append(
                DocChunk(
                    heading=heading_text,
                    content=content,
                    code_blocks=code_blocks,
                    metadata={"source_url": source_url, "level": str(level)},
                )
            )
    else:
        # Markdown: split on ATX headings (# ...).
        lines = html_or_markdown.splitlines()
        current_heading = ""
        current_level = 0
        current_content: List[str] = []
        current_code: List[str] = []
        in_code_block = False
        code_fence = ""
        code_buffer: List[str] = []
        
        def flush() -> None:
            nonlocal current_heading, current_content, current_code
            if current_heading or current_content:
                chunks.append(
                    DocChunk(
                        heading=current_heading,
                        content="\n".join(current_content).strip(),
                        code_blocks=current_code,
                        metadata={"source_url": source_url, "level": str(current_level)},
                    )
                )
            current_content = []
            current_code = []
        
        for line in lines:
            if line.startswith("```") or line.startswith("~~~"):
                if not in_code_block:
                    in_code_block = True
                    code_fence = line[:3]
                    code_buffer = []
                else:
                    in_code_block = False
                    code_fence = ""
                    block_text = "\n".join(code_buffer).strip()
                    if block_text and block_text not in current_code:
                        current_code.append(block_text)
                continue
            if in_code_block:
                code_buffer.append(line)
                continue
            
            heading_match = None
            for marker in ("# ", "## ", "### ", "#### ", "##### ", "###### "):
                if line.startswith(marker):
                    heading_match = marker
                    break
            
            if heading_match is not None:
                level = len(heading_match) - 1
                # Flush the previous heading's content before starting a new one.
                if current_heading:
                    flush()
                current_heading = line[len(heading_match):].strip()
                current_level = level
            else:
                current_content.append(line)
        
        flush()
    
    return chunks


# =============================================================================
# MCP SERVER INITIALIZATION
# =============================================================================

# Initialize FastMCP with transport security configured for cloud hosting
mcp = FastMCP(
    "OpenSafely-Rag-Retrieve",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"]
    )
)


# =============================================================================
# MCP TOOLS - KNOWLEDGE BASE
# =============================================================================

@mcp.tool()
def query_knowledge_base(question: str) -> str:
    """
    Search and retrieve answers from the Astra DB Vector Store RAG knowledge base using OpenRouter.
    
    Use this tool for general questions about OpenSAFELY, ehrQL, study design, codelists, 
    dummy data generation, and other OpenSAFELY documentation topics. The tool uses semantic 
    search to find relevant documentation chunks and generates answers using an LLM.
    
    Args:
        question: Natural language question about OpenSAFELY (e.g., "How do I define a dataset 
                  in ehrQL?", "What are the required steps in project.yaml?", "How do I use 
                  SNOMED codes in ehrQL?")
    
    Returns:
        String answer from the RAG system based on the OpenSAFELY documentation knowledge base.
    """
    try:
        from langflow.load import run_flow_from_json
        
        # Workaround for MCP Context progress reporting issue
        try:
            from mcp.server.fastmcp import Context
            orig_report_progress = Context.report_progress
            
            def safe_report_progress(self, *args, **kwargs):
                # Handle the case where 'current' is passed instead of 'progress'
                if 'current' in kwargs and 'progress' not in kwargs:
                    kwargs['progress'] = kwargs.pop('current')
                try:
                    return orig_report_progress(self, *args, **kwargs)
                except Exception:
                    # Fail silently to prevent execution crashes
                    pass
            
            Context.report_progress = safe_report_progress
        except Exception as patch_err:
            print(f"WARN: Could not patch MCP Context: {patch_err}")
        
        # Check for required flow configuration
        if not os.path.exists("flow.json"):
            return "Error: flow.json layout configuration file is missing from the server root directory."
        
        # Configure Langflow components with environment variables
        tweaks = {
            "ext:openrouter:OpenRouterComponent@official-Lbbp3": {
                "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
                "load_from_db": False 
            },
            "ext:datastax:AstraDBVectorStoreComponent@official-zF58p": {
                "token": os.environ.get("ASTRA_DB_APPLICATION_TOKEN", ""),
                "api_endpoint": os.environ.get("ASTRA_DB_API_ENDPOINT", ""),
                "load_from_db": False 
            }
        }
        
        print(f"INFO: Executing Langflow flow for question: {question}")
        result = run_flow_from_json(
            flow="flow.json",
            input_value=question,
            tweaks=tweaks
        )
        
        # Safely extract result from Langflow output
        if result and isinstance(result, list) and len(result) > 0:
            flow_output = result[0]
            if hasattr(flow_output, "outputs") and flow_output.outputs:
                for output in flow_output.outputs:
                    if hasattr(output, "results") and "message" in output.results:
                        return output.results["message"].text
        
        return "No response generated by the Langflow pipeline."
    
    except Exception as e:
        print(f"ERROR: Runtime execution failure: {e}", file=sys.stderr)
        return f"Error executing Langflow graph: {str(e)}"


@mcp.tool()
def search_docs_by_filename(filename: str) -> str:
    """
    Search the Astra DB knowledge base specifically for chunks belonging to a target filename 
    or directory path. Use this when standard questions fail to pull the direct file contents.
    
    This tool is optimized for retrieving the full text content of specific documentation files
    from the OpenSAFELY ehrQL repository documentation.
    
    Args:
        filename: The filename or path to search for (e.g., 'ethnicity.md', 'how-to/ethnicity', 
                  'dataset-definition.md', 'codelists.md')
    
    Returns:
        String containing the full documentation text from the specified file.
    """
    # Craft an exact-intent question to bypass top-level structures in Langflow
    target_question = f"Show me the full documentation text inside the file {filename}"
    print(f"INFO: Querying Vector Store for explicit file content: {filename}")
    return query_knowledge_base(target_question)


@mcp.tool()
def get_doc_section_content(topic: str, section_header: str = None) -> str:
    """
    Fetch a comprehensive block of documentation text from Astra DB for a specific topic, 
    optionally refined by an explicit section header.
    
    Use this tool when you need detailed documentation on a specific topic (e.g., 'ethnicity 
    definition', 'dataset definition', 'codelist usage') and want to focus on a particular 
    section of the documentation.
    
    Args:
        topic: The topic to search for (e.g., 'ethnicity definition', 'dataset definition', 
               'codelist usage', 'dummy data generation')
        section_header: Optional specific section header to focus on (e.g., 'Creating 
                        variables', 'Filtering patients', 'Importing codelists')
    
    Returns:
        String containing detailed documentation text for the specified topic and section.
    """
    refined_query = f"Provide all detailed documentation regarding {topic}"
    if section_header:
        refined_query += f" specifically focusing on the section: {section_header}"
    
    print(f"INFO: Fetching deep topic content for: {refined_query}")
    return query_knowledge_base(refined_query)


# =============================================================================
# MCP TOOLS - TEMPLATES
# =============================================================================

# Dynamically locate the actual absolute templates directory path
TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))

@mcp.resource("codebase://templates/{script_name}.py")
def get_any_template(script_name: str) -> str:
    """Fetches a specific reference script from the codebase templates directory."""
    
    # Build the target path appending the script name cleanly
    target_path = os.path.abspath(os.path.join(TEMPLATES_DIR, f"{script_name}.py"))
    
    # Security check to prevent directory traversal attacks
    if not target_path.startswith(TEMPLATES_DIR + os.sep) and target_path != TEMPLATES_DIR:
        return "Access denied: Invalid template location."
    
    # Read and return the file if it exists
    if os.path.exists(target_path):
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read()
    
    return f"Template '{script_name}' not found."


# =============================================================================
# MCP TOOLS - OPENSAFELY PROJECTS
# =============================================================================

async def fetch_workspace_details(session: aiohttp.ClientSession, jobs_url: str) -> List[Dict[str, str]]:
    """Fetch workspace details from jobs.opensafely.org project page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    workspaces = []
    
    try:
        async with session.get(jobs_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return workspaces
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find the Workspaces section
            workspaces_header = soup.find('h2', string=lambda text: text and 'Workspaces' in text)
            if not workspaces_header:
                return workspaces
            
            # Find the ul list after the Workspaces header
            workspaces_list = workspaces_header.find_next('ul', role='list')
            if not workspaces_list:
                return workspaces
            
            # Parse each workspace li element
            for li in workspaces_list.find_all('li', recursive=False):
                workspace_info = {}
                
                # Extract workspace name and URL
                workspace_link = li.find('a', href=True)
                if workspace_link:
                    workspace_info['name'] = workspace_link.get_text(strip=True)
                    workspace_info['workspace_url'] = 'https://jobs.opensafely.org' + workspace_link['href']
                
                # Extract GitHub repository, branch, and created date
                # These are in dd elements with sr-only dt labels
                for dd in li.find_all('dd'):
                    dt = dd.find_previous('dt')
                    if dt:
                        label = dt.get_text(strip=True)
                        value = dd.get_text(strip=True)
                        
                        if 'GitHub repository' in label:
                            workspace_info['github_repo'] = value
                        elif 'Git branch' in label:
                            workspace_info['branch'] = value
                        elif 'Created at' in label:
                            workspace_info['created_at'] = value
                
                if workspace_info:
                    workspaces.append(workspace_info)
            
            return workspaces
    
    except Exception as e:
        print(f"Error fetching workspace details from {jobs_url}: {e}")
        return workspaces


async def fetch_projects_list_page(session: aiohttp.ClientSession, page: int) -> List[ProjectListItem]:
    """Fetch a single page of the projects list and return project info."""
    if page == 1:
        url = "https://www.opensafely.org/projects/"
    else:
        url = f"https://www.opensafely.org/projects/page/{page}/"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return []
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            projects = []
            
            # Find all project list items (li elements containing project links)
            for link in soup.find_all('a', href=True):
                href = link['href']
                if href.startswith('https://www.opensafely.org/project/') and href.endswith('/'):
                    # Get the parent li container
                    container = link.find_parent('li')
                    if container:
                        text = container.get_text(strip=True)
                        # Normalize whitespace for regex matching
                        normalized_text = ' '.join(text.split())
                        
                        # Extract title from link
                        title = link.get_text(strip=True)
                        
                        # Extract organisation and project type
                        organisation = ""
                        project_type = ""
                        import re
                        
                        # Pattern: "Research project run by University of Bristol."
                        org_match = re.search(r'(Research project|Service evaluation project|Short data report project)\s+run by\s+([^.]+)\.', normalized_text)
                        if org_match:
                            project_type = org_match.group(1)
                            organisation = org_match.group(2).strip()
                        
                        # Extract date
                        date = ""
                        date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}', normalized_text)
                        if date_match:
                            date = date_match.group(0)
                        
                        # Extract tags
                        tags = []
                        if 'COVID-19' in normalized_text:
                            tags.append('COVID-19')
                        
                        projects.append(ProjectListItem(
                            url=href,
                            title=title,
                            organisation=organisation,
                            project_type=project_type,
                            date=date,
                            tags=tags
                        ))
            
            return projects
    
    except Exception as e:
        print(f"Error fetching projects page {page}: {e}")
        return []


async def fetch_project_details(session: aiohttp.ClientSession, project_item: ProjectListItem) -> Optional[OpenSafelyProject]:
    """Fetch detailed information for a single project from its detail page."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        async with session.get(project_item.url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status != 200:
                return None
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract project ID from URL
            project_id = project_item.url.rstrip('/').split('/')[-1]
            
            # Extract title from meta tags or use list page title
            title = project_item.title
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content']
            else:
                h1 = soup.find('h1')
                if h1:
                    title = h1.get_text(strip=True)
            
            # Extract description from meta tags
            description = ""
            og_desc = soup.find('meta', property='og:description')
            if og_desc and og_desc.get('content'):
                description = og_desc['content']
            else:
                meta_desc = soup.find('meta', attrs={'name': 'description'})
                if meta_desc and meta_desc.get('content'):
                    description = meta_desc['content']
            
            # Extract full content from main/article
            full_content = ""
            main = soup.find('main')
            if main:
                full_content = main.get_text(strip=True)
            else:
                article = soup.find('article')
                if article:
                    full_content = article.get_text(strip=True)
            
            # Extract study lead(s) from full content
            study_lead = ""
            researchers = []
            import re
            # Pattern: "Study lead:Name" or "Study leads:Name1,Name2" followed by Organisation/Project type/Start date
            # Handles both singular and plural forms
            study_lead_match = re.search(r'Study leads?:\s*(.+?)(?:Organisation:|Project type:|Start date:|Topic area:|Date of approval:|$)', full_content)
            if study_lead_match:
                study_lead = study_lead_match.group(1).strip()
            else:
                # Fallback: try line-based approach
                lines = full_content.split('\n')
                for i, line in enumerate(lines):
                    if 'Study lead:' in line or 'Study leads:' in line:
                        for j in range(i+1, min(i+5, len(lines))):
                            if lines[j].strip():
                                study_lead = lines[j].strip()
                                break
                        break
            
            # Extract researchers from jobs.opensafely.org pages
            # Look for the Researchers section with h2#researchers-title followed by ul/li
            h2 = soup.find('h2', {'id': 'researchers-title'})
            if h2:
                grandparent = h2.parent.parent if h2.parent else None
                if grandparent:
                    for sibling in grandparent.find_next_siblings():
                        ul = sibling.find('ul')
                        if ul:
                            for li in ul.find_all('li'):
                                researcher_name = li.get_text(strip=True)
                                if researcher_name:
                                    researchers.append(researcher_name)
                            break
            
            # Find the jobs.opensafely.org URL from the project page
            jobs_url = None
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'jobs.opensafely.org' in href:
                    jobs_url = href
                    break
            
            # Fetch workspace information from jobs.opensafely.org
            workspaces = []
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
                full_content=full_content[:10000],  # Limit content size
                study_lead=study_lead,
                researchers=researchers,
                workspaces=workspaces
            )
    
    except Exception as e:
        print(f"Error fetching project {project_item.url}: {e}")
        return None


@mcp.tool()
async def scrape_opensafely_projects(
    max_pages: int = 8,
    delay_between_requests: float = 1.0
) -> str:
    """
    Scrape all OpenSAFELY projects from https://www.opensafely.org/projects/
    
    This extracts project details from all paginated pages (1-8 by default).
    Each project includes: ID, title, URL, organisation, type, date, tags, description, 
    full content, study lead, researchers, and workspace information with GitHub repositories.
    
    Use this tool when you need a comprehensive list of all OpenSAFELY projects, or when
    you want to discover projects by organisation, topic, or date range.
    
    Args:
        max_pages: Maximum number of pages to scrape (default 8, which is the last page).
                   Each page contains multiple projects.
        delay_between_requests: Delay in seconds between requests to be respectful to the 
                                server (default 1.0).
    
    Returns:
        JSON string with list of all projects including workspace information with GitHub 
        repository details (name, github_repo, branch, created_at, workspace_url).
    """
    all_projects = []
    all_project_urls = set()
    
    # Configure HTTP client with connection limits and timeout
    connector = aiohttp.TCPConnector(limit=5)
    timeout = aiohttp.ClientTimeout(total=60)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # First, collect all project URLs from all pages
        for page in range(1, max_pages + 1):
            print(f"Fetching projects list page {page}...")
            urls = await fetch_projects_list_page(session, page)
            new_urls = [u for u in urls if u not in all_project_urls]
            all_project_urls.update(new_urls)
            print(f"  Found {len(new_urls)} new project URLs (total: {len(all_project_urls)})")
            
            if page < max_pages:
                await asyncio.sleep(delay_between_requests)
        
        # Now fetch details for each project
        print(f"Fetching details for {len(all_project_urls)} projects...")
        for i, url in enumerate(sorted(all_project_urls)):
            print(f"  [{i+1}/{len(all_project_urls)}] {url}")
            project = await fetch_project_details(session, url)
            if project:
                all_projects.append(project)
            await asyncio.sleep(delay_between_requests)
    
    # Convert to JSON-serializable format
    projects_data = []
    for project in all_projects:
        projects_data.append(asdict(project))
    
    return json.dumps({
        "total_projects": len(projects_data),
        "pages_scraped": max_pages,
        "projects": projects_data
    }, indent=2)


@mcp.tool()
async def get_opensafely_project_details(project_url: str) -> str:
    """
    Get detailed information for a specific OpenSAFELY project including workspace and 
    GitHub repository information.
    
    This tool fetches comprehensive project details from the OpenSAFELY website and 
    automatically discovers the associated jobs.opensafely.org page to extract workspace 
    information including GitHub repository names, branches, and creation dates.
    
    Use this tool when you have a specific project URL and need:
    - Project metadata (title, organisation, type, date, tags)
    - Study lead and researchers
    - Full project description
    - **Workspace information with GitHub repositories** (name, github_repo, branch, 
      created_at, workspace_url) - this is the key feature for finding code repositories
    
    Args:
        project_url: The project URL from opensafely.org 
                     (e.g., 'https://www.opensafely.org/project/pos-2026-3018/' or 
                      'https://www.opensafely.org/project/pos-2026-3008/')
    
    Returns:
        JSON string with complete project details including workspaces array containing
        GitHub repository information for each workspace.
    """
    # Create a minimal ProjectListItem from the URL
    project_item = ProjectListItem(
        url=project_url,
        title="",
        organisation="",
        project_type="",
        date="",
        tags=[]
    )
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            project = await fetch_project_details(session, project_item)
            if project:
                return json.dumps(asdict(project), indent=2)
            else:
                return json.dumps({"error": "Failed to fetch project details"})
    
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# FASTAPI APPLICATION SETUP
# =============================================================================

# Create standard FastAPI application
app = FastAPI(
    title="OpenSafely Rag MCP Server",
    description="Model Context Protocol (MCP) server delivering Astra DB RAG capabilities via Langflow."
)

# Attach production middleware (Proxy headers for SSL/Host resolution & CORS)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Platform health check endpoint
@app.get("/")
async def health_check():
    return {
        "status": "healthy",
        "service": "OpenSafely-Rag-Retrieve-MCP",
        "mcp_endpoint": "/mcp"
    }

# Mount the FastMCP StreamableHTTP application under /mcp namespace
app.mount("/mcp", mcp.streamable_http_app())


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, timeout_keep_alive=300)

"""
tests/test_harness.py

A simple pytest evaluation harness for the OpenSafelyMCP server.

WHAT IS A HARNESS EVAL?
-----------------------
A "harness eval" is just a collection of automated tests that check whether
your system behaves correctly. Instead of testing one function in isolation,
a harness tests the whole pipeline end-to-end:

    Input  -->  [your code]  -->  Output  -->  [assert it's correct]

This file has 4 components, each testing a different layer:

  1. ehrQL AST Validator        -- does ehrQL code use valid, non-deprecated syntax?
  2. MCP Tool Contract Tests    -- are the 5 MCP tools registered and well-formed?
  3. Scraper Stability Tests    -- does the doc chunker extract headings/code correctly?
  4. Canary Live Probes         -- live network checks (skipped by default)

Run everything except the live probes:

    pytest tests/test_harness.py

Run only the ehrQL validator tests:

    pytest tests/test_harness.py -k "TestEhrQL"

Run the live probes (requires network + API keys):

    pytest tests/test_harness.py -m canary --run-canary
"""

from __future__ import annotations

import ast
import json
import os
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ===========================================================================
# COMPONENT 1: ehrQL AST Validator
# ===========================================================================
#
# GOAL: Catch ehrQL snippets that use deprecated cohortextractor constructs
#       (StudyDefinition, patients.with_these_clinical_events, etc.) instead
#       of modern ehrql patterns (create_dataset, clinical_events, etc.).
#
# HOW IT WORKS:
#   1. Parse the snippet with ast.parse() -- if it fails, it's a syntax error.
#   2. Walk the AST with a NodeVisitor looking for deprecated imports/names/calls.
#   3. If any deprecated construct is found, the snippet is "invalid".

# Deprecated cohortextractor constructs we want to flag.
DEPRECATED_IMPORTS = {"cohortextractor"}
DEPRECATED_NAMES = {"StudyDefinition"}
DEPRECATED_ATTRIBUTE_CALLS = {
    "patients.with_these_clinical_events",
    "patients.with_these_medications",
    "patients.with_diagnoses",
    "patients.with_registrations",
    "patients.with_ethnicity_from_sus",
    "patients.with_gp_registrations",
    "patients.with_hospital_admissions",
    "patients.with_outpatient_appointments",
    "patients.with_emergency_department_attendances",
    "patients.with_death_recorded",
    "patients.with_covid_vaccination",
    "patients.with_covid_test",
}

# Valid ehrql imports that should pass.
VALID_IMPORTS = {
    "ehrql": {"create_dataset", "clinical_events", "codelist", "measure"},
    "ehrql.codelist": {"codelist_from_csv"},
}


class EhrQLASTVisitor(ast.NodeVisitor):
    """Walk an ehrQL snippet's AST and flag deprecated cohortextractor usage."""

    def __init__(self) -> None:
        self.deprecated_imports: List[str] = []
        self.deprecated_names: List[str] = []
        self.deprecated_attribute_calls: List[str] = []
        self.valid_imports: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in DEPRECATED_IMPORTS:
                self.deprecated_imports.append(alias.name)
            elif top in VALID_IMPORTS:
                self.valid_imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        top = module.split(".")[0]
        if top in DEPRECATED_IMPORTS:
            self.deprecated_imports.append(module)
        elif module in VALID_IMPORTS:
            for alias in node.names:
                self.valid_imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in DEPRECATED_NAMES:
            self.deprecated_names.append(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Build the full dotted path, e.g. patients.with_these_clinical_events.
        parts: List[str] = []
        cur: ast.AST = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value  # type: ignore[assignment]
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        path = ".".join(reversed(parts))
        if path in DEPRECATED_ATTRIBUTE_CALLS:
            self.deprecated_attribute_calls.append(path)
        self.generic_visit(node)


def validate_ehrql_ast(source: str) -> Dict[str, Any]:
    """
    Validate an ehrQL snippet using Python's ast module.

    Returns a dict:
        valid        -- bool, parsed cleanly AND no deprecated constructs
        errors       -- list of syntax/parse errors
        warnings     -- list of deprecation warning strings
        deprecated   -- list of deprecated constructs found
        valid_imports-- list of valid ehrql imports found
    """
    result: Dict[str, Any] = {
        "valid": False,
        "errors": [],
        "warnings": [],
        "deprecated": [],
        "valid_imports": [],
    }

    # Step 1: Try to parse. If it fails, we're done.
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        result["errors"].append(f"SyntaxError: {exc.msg} (line {exc.lineno})")
        return result

    # Step 2: Walk the AST looking for deprecated constructs.
    visitor = EhrQLASTVisitor()
    visitor.visit(tree)

    deprecated: List[str] = []
    deprecated.extend(visitor.deprecated_imports)
    deprecated.extend(visitor.deprecated_names)
    deprecated.extend(visitor.deprecated_attribute_calls)

    result["deprecated"] = deprecated
    result["valid_imports"] = visitor.valid_imports
    result["warnings"] = [f"Deprecated construct: {d}" for d in deprecated]
    result["valid"] = len(deprecated) == 0

    return result


class TestEhrQLValidator:
    """Unit tests for the ehrQL AST validator.

    Each test checks ONE thing:
      - valid snippets pass
      - deprecated snippets fail
      - syntax errors are caught
    """

    def test_valid_create_dataset(self) -> None:
        """A simple, valid ehrQL snippet should pass."""
        source = "from ehrql import create_dataset\ndataset = create_dataset()\n"
        result = validate_ehrql_ast(source)
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["deprecated"] == []

    def test_valid_codelist_from_csv(self) -> None:
        """Importing codelist_from_csv from ehrql.codelist is valid."""
        source = "from ehrql.codelist import codelist_from_csv\n"
        result = validate_ehrql_ast(source)
        assert result["valid"] is True
        assert "ehrql.codelist.codelist_from_csv" in result["valid_imports"]

    def test_syntax_error_is_caught(self) -> None:
        """Broken Python should produce an error, not crash."""
        source = "from ehrql import create_dataset\ndataset = create_dataset(\n"
        result = validate_ehrql_ast(source)
        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "SyntaxError" in result["errors"][0]

    def test_deprecated_study_definition(self) -> None:
        """StudyDefinition from cohortextractor is deprecated."""
        source = "from cohortextractor import StudyDefinition\nstudy = StudyDefinition()\n"
        result = validate_ehrql_ast(source)
        assert result["valid"] is False
        assert "StudyDefinition" in result["deprecated"]
        assert "cohortextractor" in result["deprecated"]

    def test_deprecated_patients_with_these_clinical_events(self) -> None:
        """patients.with_these_clinical_events is a deprecated cohortextractor call."""
        source = "events = patients.with_these_clinical_events('codes')\n"
        result = validate_ehrql_ast(source)
        assert result["valid"] is False
        assert "patients.with_these_clinical_events" in result["deprecated"]

    def test_mixed_valid_and_deprecated(self) -> None:
        """If a snippet has both valid and deprecated parts, it fails."""
        source = (
            "from ehrql import create_dataset\n"
            "from cohortextractor import StudyDefinition\n"
            "study = StudyDefinition()\n"
        )
        result = validate_ehrql_ast(source)
        assert result["valid"] is False
        assert "ehrql.create_dataset" in result["valid_imports"]
        assert "StudyDefinition" in result["deprecated"]

    def test_empty_source_is_valid(self) -> None:
        """An empty snippet has nothing wrong with it."""
        result = validate_ehrql_ast("")
        assert result["valid"] is True
        assert result["errors"] == []
        assert result["deprecated"] == []


# ===========================================================================
# COMPONENT 2: MCP Tool Contract Tests
# ===========================================================================
#
# GOAL: Verify the FastMCP server registers all 5 expected tools and that
#       each tool has a valid JSON input schema (so an LLM can call it).
#
# HOW IT WORKS:
#   - Import the mcp instance from main.py
#   - Call mcp.list_tools() to see what's registered
#   - Assert each expected tool name is present
#   - Assert each tool's inputSchema has properties with types

EXPECTED_TOOLS = {
    "query_knowledge_base": ["question"],
    "search_docs_by_filename": ["filename"],
    "get_doc_section_content": ["topic", "section_header"],
    "scrape_opensafely_projects": ["max_pages", "delay_between_requests"],
    "get_opensafely_project_details": ["project_url"],
}


class TestMCPToolContracts:
    """Contract tests: the MCP server must expose the right tools with
    valid schemas. No network is used -- we just inspect the server object."""

    def _get_registered_tool_names(self) -> List[str]:
        """Return the list of tool names registered on the MCP server."""
        from main import mcp

        tools = mcp.list_tools()
        import inspect

        if inspect.iscoroutine(tools):
            import asyncio

            tools = asyncio.run(tools)
        if isinstance(tools, dict):
            return list(tools.keys())
        # FastMCP returns a list of Tool objects with a .name attribute.
        return [getattr(t, "name", "") for t in tools]

    def test_all_expected_tools_are_registered(self) -> None:
        """Every tool in EXPECTED_TOOLS must exist on the server."""
        names = self._get_registered_tool_names()
        for tool_name in EXPECTED_TOOLS:
            assert tool_name in names, (
                f"Tool '{tool_name}' is missing from the MCP server"
            )

    def test_each_tool_has_input_schema(self) -> None:
        """Each tool must declare an inputSchema so LLMs know what to pass."""
        from main import mcp

        tools = mcp.list_tools()
        import inspect

        if inspect.iscoroutine(tools):
            import asyncio

            tools = asyncio.run(tools)

        tool_map = {}
        if isinstance(tools, dict):
            tool_map = tools
        else:
            for t in tools:
                tool_map[getattr(t, "name", "")] = t

        for tool_name in EXPECTED_TOOLS:
            tool = tool_map.get(tool_name)
            assert tool is not None, f"Tool '{tool_name}' not found"
            schema = getattr(tool, "inputSchema", None) or getattr(
                tool, "input_schema", None
            )
            assert schema is not None, f"Tool '{tool_name}' has no input schema"
            assert "properties" in schema, (
                f"Tool '{tool_name}' schema missing 'properties'"
            )

    def test_each_tool_param_has_type(self) -> None:
        """Every parameter in the schema must declare a type (string, integer, etc.)."""
        from main import mcp

        tools = mcp.list_tools()
        import inspect

        if inspect.iscoroutine(tools):
            import asyncio

            tools = asyncio.run(tools)

        tool_map = {}
        if isinstance(tools, dict):
            tool_map = tools
        else:
            for t in tools:
                tool_map[getattr(t, "name", "")] = t

        for tool_name, expected_params in EXPECTED_TOOLS.items():
            tool = tool_map.get(tool_name)
            assert tool is not None, f"Tool '{tool_name}' not found"
            schema = getattr(tool, "inputSchema", None) or getattr(
                tool, "input_schema", None
            )
            properties = schema.get("properties", {})
            for param in expected_params:
                assert param in properties, (
                    f"Tool '{tool_name}' missing parameter '{param}'"
                )
                param_schema = properties[param]
                # Accept {"type": ...} or modern Optional[...] form
                # {"anyOf": [{"type": ...}, {"type": "null"}]}
                has_type = "type" in param_schema or (
                    isinstance(param_schema.get("anyOf"), list)
                    and any("type" in sub for sub in param_schema["anyOf"])
                )
                assert has_type, (
                    f"Tool '{tool_name}' param '{param}' has no type"
                )


# ===========================================================================
# COMPONENT 3: Scraper Stability Tests
# ===========================================================================
#
# GOAL: Verify the documentation chunker (chunk_documentation in main.py)
#       correctly extracts headings, preserves code blocks, and tags metadata
#       from local HTML/Markdown fixture files.
#
# HOW IT WORKS:
#   - Read a local fixture file (no network).
#   - Pass it to chunk_documentation().
#   - Assert the expected headings, code blocks, and metadata appear.

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


class TestScraperStability:
    """Tests for the documentation chunker against local fixtures."""

    def test_html_heading_extraction(self) -> None:
        """HTML fixtures should yield one chunk per heading (h1-h6)."""
        from main import chunk_documentation

        html = _read_fixture("sample_ethnicity.html")
        chunks = chunk_documentation(html, source_url="https://example.com/ethnicity")

        headings = [c.heading for c in chunks]
        assert "Ethnicity definition" in headings
        assert "Creating variables" in headings
        assert "Filtering patients" in headings

    def test_html_code_block_preservation(self) -> None:
        """Code blocks inside HTML <pre><code> should be captured."""
        from main import chunk_documentation

        html = _read_fixture("sample_ethnicity.html")
        chunks = chunk_documentation(html)

        creating_vars = next(c for c in chunks if c.heading == "Creating variables")
        assert len(creating_vars.code_blocks) > 0
        assert any("codelist_from_csv" in cb for cb in creating_vars.code_blocks)

    def test_html_metadata_tagging(self) -> None:
        """Each chunk should carry source_url and heading level metadata."""
        from main import chunk_documentation

        html = _read_fixture("sample_ethnicity.html")
        chunks = chunk_documentation(html, source_url="https://example.com/ethnicity")

        for chunk in chunks:
            assert chunk.metadata["source_url"] == "https://example.com/ethnicity"
            assert "level" in chunk.metadata

    def test_markdown_heading_extraction(self) -> None:
        """Markdown fixtures should yield one chunk per # heading."""
        from main import chunk_documentation

        md = _read_fixture("sample_dataset.md")
        chunks = chunk_documentation(md)

        headings = [c.heading for c in chunks]
        assert "Dataset definition" in headings
        assert "Creating variables" in headings
        assert "Filtering patients" in headings

    def test_markdown_code_block_preservation(self) -> None:
        """Markdown fenced code blocks (```python) should be captured."""
        from main import chunk_documentation

        md = _read_fixture("sample_dataset.md")
        chunks = chunk_documentation(md)

        creating_vars = next(c for c in chunks if c.heading == "Creating variables")
        assert len(creating_vars.code_blocks) > 0
        assert any("create_dataset" in cb for cb in creating_vars.code_blocks)

    def test_empty_input_returns_no_chunks(self) -> None:
        """Empty input should produce an empty list, not crash."""
        from main import chunk_documentation

        assert chunk_documentation("") == []

    def test_no_headings_returns_no_chunks(self) -> None:
        """A page with no headings produces no chunks."""
        from main import chunk_documentation

        assert chunk_documentation("<p>Just a paragraph.</p>") == []


# ===========================================================================
# COMPONENT 4: Canary Live Probes (skipped by default)
# ===========================================================================
#
# GOAL: Verify live dependencies (AstraDB, upstream OpenSAFELY website) are
#       reachable and returning sensible data.
#
# These are marked with @pytest.mark.canary and skipped unless you pass
# --run-canary. They require network access and API keys, so they are NOT
# part of the default test run.

CANARY_QUERIES = [
    ("How do I define a dataset in ehrQL?", ["create_dataset", "dataset"]),
    ("How do I use codelists in ehrQL?", ["codelist", "codelist_from_csv"]),
]

CANARY_URLS = [
    "https://www.opensafely.org/",
    "https://www.opensafely.org/projects/",
]


@pytest.mark.canary
class TestCanaryLiveProbes:
    """Live integration probes -- skipped by default."""

    @pytest.fixture(autouse=True)
    def skip_unless_enabled(self, request: pytest.FixtureRequest) -> None:
        if not request.config.getoption("--run-canary", default=False):
            pytest.skip("Canary probe skipped; use --run-canary to enable")

    @pytest.mark.parametrize("query,expected_terms", CANARY_QUERIES)
    def test_knowledge_base_returns_relevant_answer(
        self, query: str, expected_terms: List[str]
    ) -> None:
        """AstraDB should return an answer containing expected ehrQL terms."""
        from main import query_knowledge_base

        result = query_knowledge_base(query)
        assert isinstance(result, str)
        assert len(result) > 0
        lowered = result.lower()
        assert any(term.lower() in lowered for term in expected_terms)

    @pytest.mark.parametrize("url", CANARY_URLS)
    def test_upstream_doc_is_reachable(self, url: str) -> None:
        """OpenSAFELY documentation URLs should return HTTP 200."""
        import aiohttp

        async def _fetch() -> int:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "OpenSafelyMCP-canary/1.0"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    return response.status

        status = asyncio.run(_fetch())
        assert status == 200, f"{url} returned HTTP {status}"


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--run-canary",
        action="store_true",
        default=False,
        help="Run canary / live integration probes",
    )

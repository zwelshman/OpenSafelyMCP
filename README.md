# OpenSafelyMCP

[![Stars](https://img.shields.io/github/stars/zwelshman/OpenSafelyMCP?style=flat-square&logo=github&color=blue)](https://github.com/zwelshman/OpenSafelyMCP/stargazers)
[![Forks](https://img.shields.io/github/forks/zwelshman/OpenSafelyMCP?style=flat-square&logo=git&color=orange)](https://github.com/zwelshman/OpenSafelyMCP/network/members)
[![Issues](https://img.shields.io/github/issues/zwelshman/OpenSafelyMCP?style=flat-square&logo=issues&color=critical)](https://github.com/zwelshman/OpenSafelyMCP/issues)
[![Repo Size](https://img.shields.io/github/repo-size/zwelshman/OpenSafelyMCP?style=flat-square&logo=codeforces&color=success)](https://github.com/zwelshman/OpenSafelyMCP)

⚠️ **Disclaimer:** This project is independent and not affiliated with the official OpenSafely project.

An open-source Model Context Protocol (MCP) server that provides access to OpenSAFELY documentation and project information. It allows you to seamlessly integrate OpenSAFELY's ehrQL documentation and project metadata directly into your AI assistant of choice (such as Cursor, VS Code, or Claude Desktop).

## 🛠️ Tech Stack
*   **MCP Server:** FastMCP (Python)
*   **Documentation Source:** OpenSAFELY ehrQL Repository (via AstraDB Vector Store)
*   **Project Data:** Live scraping from opensafely.org and jobs.opensafely.org
*   **Hosting Platform:** Render

## 📊 Data Sources
*   **Documentation:** OpenSAFELY ehrQL documentation - AST-Python chunked, embedded via Nvidia EmbedQA, stored in AstraDB vector database for RAG
*   **Projects:** Live data from https://www.opensafely.org/projects/ and https://jobs.opensafely.org/

## 🚀 Supported MCP Tools

### Documentation RAG Tools
Your AI assistant will automatically discover and utilize the following targeted vector-store capabilities:

*   **`query_knowledge_base(question)`** – Search and retrieve conceptual answers from the Astra DB Vector Store RAG knowledge base using natural language. Best for general questions about OpenSAFELY, ehrQL, study design, codelists, dummy data generation, and other documentation topics.

*   **`search_docs_by_filename(filename)`** – Queries the vector knowledge base specifically for chunks belonging to a targeted filename or path (e.g., `ethnicity.md` or `how-to/ethnicity`). Use this when general queries fail to pull the full text content of a specific file.

*   **`get_doc_section_content(topic, section_header)`** – Fetches a comprehensive block of documentation text from Astra DB for a specific topic (e.g., `ethnicity definition`) and optionally refines the context extraction via a structural header.

### Project Discovery Tools
*   **`scrape_opensafely_projects(max_pages, delay_between_requests)`** – Scrape all OpenSAFELY projects from the projects listing page. Returns comprehensive project data including workspace information with GitHub repository details.

*   **`get_opensafely_project_details(project_url)`** – Get detailed information for a specific OpenSAFELY project including workspace and GitHub repository information. **This is the key tool for finding GitHub repositories for a project's code.**

## ⚙️ Deployment & Integration

*   **Hosted MCP Server (SSE Endpoint):** `https://opensafelymcp.onrender.com/mcp/sse`

### VS Code / Cursor Configuration
Add the following snippet to your MCP settings file (e.g., `mcpServers.json` or through your IDE settings panel) to connect your assistant:

```json
{
  "mcpServers": {
    "OpenSafelyMCP": {
      "type": "sse",
      "url": "https://opensafelymcp.onrender.com/mcp/sse"
    }
  }
}
```

*(Note: Depending on your client implementation, your AI assistant will intelligently switch between semantic question-answering and explicit file-path targeting tools depending on your prompt context).*

## 🎯 Common Use Cases

See [use_cases.md](use_cases.md) for detailed examples of how to use each tool effectively.

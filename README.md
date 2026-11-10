# OpenSafelyMCP

[![Stars](https://img.shields.io/github/stars/zwelshman/OpenSafelyMCP?style=flat-square&logo=github&color=blue)](https://github.com/zwelshman/OpenSafelyMCP/stargazers)
[![Forks](https://img.shields.io/github/forks/zwelshman/OpenSafelyMCP?style=flat-square&logo=git&color=orange)](https://github.com/zwelshman/OpenSafelyMCP/network/members)
[![Issues](https://img.shields.io/github/issues/zwelshman/OpenSafelyMCP?style=flat-square&logo=issues&color=critical)](https://github.com/zwelshman/OpenSafelyMCP/issues)
[![Repo Size](https://img.shields.io/github/repo-size/zwelshman/OpenSafelyMCP?style=flat-square&logo=codeforces&color=success)](https://github.com/zwelshman/OpenSafelyMCP)

⚠️ **Disclaimer:** This project is independent and not affiliated with the official OpenSafely project.

An open-source Langflow workflow that exposes a hosted Model Context Protocol (MCP) server pulled directly from the `OpenSafely ehrql` Repository.. It allows you to seamlessly integrate OpenSafely's `ehrql` repository directly into your AI assistant of choice (such as Cursor, VS Code, or Claude Desktop).

## 🛠️ Tech Stack
*   **Workflow Orchestration:** Langflow
*   **Data Ingestion:** GitExtractor
*   **Vector Database:** AstraDB
*   **Hosting Platform:** Render

## 📊 Data Pipeline
*   **Source:** Documentation pulled directly from the OpenSafely `ehrql` Repository.
*   **Processing:** The documentation is AST-Python chunked, embedded via Nvidia EmbedQA, and stored in an AstraDB vector database for highly relevant Retrieval-Augmented Generation (RAG).

## 🚀 Supported MCP Tools

Your AI assistant will automatically discover and utilize the following targeted vector-store capabilities:

*   `query_knowledge_base(question)` – Search and retrieve conceptual answers from the Astra DB Vector Store RAG knowledge base using natural language.
*   `search_docs_by_filename(filename)` – Queries the vector knowledge base specifically for chunks belonging to a targeted filename or path (e.g., `ethnicity.md` or `how-to/ethnicity`). Use this when general queries fail to pull the full text content of a specific file.
*   `get_doc_section_content(topic, section_header)` – Fetches a comprehensive block of documentation text from Astra DB for a specific topic (e.g., `ethnicity definition`) and optionally refines the context extraction via a structural header.

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

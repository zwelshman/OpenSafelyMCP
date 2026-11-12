# OpenSAFELY MCP Use Cases

This document provides comprehensive examples for using each MCP tool effectively.

---

## 📚 Documentation RAG Tools

### 1. `query_knowledge_base(question)`
**Best for:** General questions about OpenSAFELY, ehrQL, study design, codelists, dummy data generation, and other documentation topics.

**When to use:** You have a conceptual question and want an answer synthesized from the documentation.

**Example Prompts:**
- "How do I define a dataset in ehrQL that extracts the most recent HbA1c lab result between two dates?"
- "What are the required steps in a project.yaml file for a cohort study?"
- "How do I use SNOMED codes in ehrQL where() filtering functions?"
- "Explain the OpenSAFELY action-based workflow for data extraction, cleaning, and analysis"
- "How does dummy data generation work in OpenSAFELY and how do I specify custom prevalence rates?"
- "What Python packages are commonly used for survival analysis in OpenSAFELY studies?"
- "How do I handle missing data in ehrQL dataset definitions?"
- "What's the difference between a Research project and a Service evaluation project in OpenSAFELY?"

---

### 2. `search_docs_by_filename(filename)`
**Best for:** Retrieving the full text content of a specific documentation file when you know the filename.

**When to use:** You need the complete content of a specific file and general queries aren't returning it.

**Example Prompts:**
- "Show me the full content of ethnicity.md"
- "Get the complete documentation for how-to/ethnicity"
- "Retrieve the dataset-definition.md file"
- "Show me the codelists.md documentation"
- "Get the full text of dummy-data.md"
- "Fetch the project-yaml.md reference guide"

---

### 3. `get_doc_section_content(topic, section_header)`
**Best for:** Getting detailed documentation on a specific topic, optionally focused on a particular section.

**When to use:** You want comprehensive documentation on a topic and optionally want to focus on a specific section.

**Example Prompts:**
- "Get detailed documentation on ethnicity definition"
- "Fetch all documentation about dataset definition, focusing on the 'Creating variables' section"
- "Get comprehensive docs on codelist usage, specifically the 'Importing codelists' section"
- "Show me documentation on dummy data generation, focusing on 'Custom distributions'"
- "Get all docs about project.yaml structure, specifically the 'Actions' section"

---

## 🔍 Project Discovery Tools

### 4. `scrape_opensafely_projects(max_pages, delay_between_requests)`
**Best for:** Getting a comprehensive list of all OpenSAFELY projects with full metadata including GitHub workspace information.

**When to use:** You want to discover projects, filter by organisation/topic/date, or get an overview of all projects.

**Example Prompts:**
- "Scrape all OpenSAFELY projects"
- "Get all projects from the last 3 pages"
- "Fetch all projects with a 2-second delay between requests"

**Returns:** JSON with all projects including:
- Project ID, title, URL, organisation, type, date, tags
- Description, full content, study lead, researchers
- **Workspaces array** with GitHub repo info (name, github_repo, branch, created_at, workspace_url)

---

### 5. `get_opensafely_project_details(project_url)`
**Best for:** Getting detailed information for a specific project **including GitHub repository information for workspaces**.

**When to use:** You have a specific project URL and need to find the GitHub repositories for the project's code.

**Example Prompts:**
- "Get details for https://www.opensafely.org/project/pos-2026-3018/"
- "Find the GitHub repos for project pos-2026-3008"
- "Get project details for https://www.opensafely.org/project/pos-2026-3019/"

**Returns:** JSON with complete project details including:
- All project metadata
- **Workspaces array** with GitHub repository information:
  - `name`: Workspace name (e.g., "reduce-wp1")
  - `github_repo`: GitHub repository name (e.g., "reduce-wp1")
  - `branch`: Git branch (e.g., "main")
  - `created_at`: Creation date (e.g., "04 Nov 2026")
  - `workspace_url`: URL to the workspace on jobs.opensafely.org

---

## 🎯 Practical Workflows

### Finding GitHub Repositories for a Project
```
User: "I need to find the GitHub repositories for the REDUCE-HF heart failure study (pos-2026-3018)"

Assistant: Uses get_opensafely_project_details with URL "https://www.opensafely.org/project/pos-2026-3018/"
Returns: Project details with workspaces array containing github_repo names
```

### Discovering Projects by Organisation
```
User: "Show me all OpenSAFELY projects from University of Bristol"

Assistant: Uses scrape_opensafely_projects, then filters for organisation="University of Bristol"
```

### Learning ehrQL Syntax
```
User: "How do I create a variable for the most recent blood pressure reading in ehrQL?"

Assistant: Uses query_knowledge_base with the question
Returns: Synthesized answer from documentation with code examples
```

### Getting Full Documentation for a Specific File
```
User: "I need the complete ethnicity.md documentation file"

Assistant: Uses search_docs_by_filename with "ethnicity.md"
Returns: Full text content of the ethnicity.md file
```

### Deep Dive on a Specific Topic
```
User: "Give me comprehensive documentation on codelist usage, especially how to import them"

Assistant: Uses get_doc_section_content with topic="codelist usage" and section_header="Importing codelists"
Returns: Focused documentation on that specific section
```

---

## 💡 Tips for Effective Use

1. **Start with `get_opensafely_project_details`** when you have a project URL and need GitHub repos
2. **Use `scrape_opensafely_projects`** when you want to explore/discover projects
3. **Use `query_knowledge_base`** for general "how-to" questions
4. **Use `search_docs_by_filename`** when you know the exact file you need
5. **Use `get_doc_section_content`** for deep dives on specific topics with section focus
6. **Combine tools**: Scrape projects → Get details for specific project → Query knowledge base for implementation details

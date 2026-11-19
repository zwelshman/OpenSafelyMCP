# Extracted MCP Skills from Claude Plugins Official

This directory contains extracted skills and references from the [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) repository, specifically from the `mcp-server-dev` plugin.

## Contents

### build-mcp-server Skill
- `build-mcp-server.skill.md` - Main skill file
- `references/` - Supporting reference documents:
  - auth.md
  - deploy-cloudflare-workers.md
  - elicitation.md
  - remote-http-scaffold.md
  - resources-and-prompts.md
  - server-capabilities.md
  - tool-design.md
  - versions.md

### build-mcp-app Skill
- `build-mcp-app/SKILL.md` - Main skill file
- `build-mcp-app/references/` - Supporting references:
  - abuse-protection.md
  - apps-sdk-messages.md
  - directory-checklist.md
  - iframe-sandbox.md
  - payload-budgeting.md
  - widget-templates.md

## How to Use These Skills in VS Code

These skills were designed for Claude Code's skill system, but you can use them as reference materials in VS Code:

### 1. As Documentation
Open any `.md` file in VS Code to read the guidance and best practices for MCP server development.

### 2. For Manual MCP Development
Follow the guidance in these skills to build MCP servers manually:

#### Basic MCP Server Setup (TypeScript)
```bash
# In your VS Code integrated terminal:
npm init -y
npm install @modelcontextprotocol/sdk
npm install -D typescript ts-node @types/node

# Create tsconfig.json
npx tsc --init

# Create your MCP server (index.ts)
```

#### Example MCP Server Structure
```typescript
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const server = new McpServer({
  name: "your-mcp-server",
  version "1.0.0"
});

// Add tools based on guidance from build-mcp-server skill
server.tool("your-tool-name", {
  // parameters schema
}, async (args) => {
  // tool implementation
});

const transport = new StdioServerTransport();
await server.connect(transport);
```

### 3. Key Guidance from the Skills

From **build-mcp-server.skill.md**:

**Phase 1 - Use Case Discovery:**
1. What does it connect to? (Determines deployment model)
2. Who will use it? (Affects accessibility choices)
3. How many distinct actions? (Determines tool design pattern)
4. Does it need mid-call user input? (Elicitation vs MCP app widgets)
5. What auth does the upstream service use?

**Deployment Models:**
- **Remote HTTP**: Publicly accessible (recommended for sharing)
- **MCPB**: Local but shareable with authentication
- **Local stdio**: Easiest for prototyping (machine-only access)

**Tool Design Patterns:**
- **<15 actions**: One tool per action
- **Many actions**: Search + execute pattern
- **Resource-oriented**: For data access patterns

### 4. MCP Development Resources

For actual MCP server development in VS Code, consider:

- **Official MCP Documentation**: https://modelcontextprotocol.io
- **MCP TypeScript SDK**: https://www.npmjs.com/package/@modelcontextprotocol/sdk
- **VS Code Extensions**: Search "MCP" in VS Code marketplace for debugging tools
- **Community Examples**: Look for MCP servers on GitHub for reference implementations

## Important Notes

⚠️ These skills are **reference materials only**. They won't automatically configure VS Code or provide Claude Code-like functionality.

To use them as intended (with automatic skill loading and Claude Code integration), you would need to:
1. Install Claude Code: `npm install -g @anthropic-ai/claude-code`
2. Use the `/skill load` command within Claude Code sessions

For VS Code-only MCP development, treat these as documentation and follow the manual setup approaches outlined above.

## License

See the original repository for licensing information: https://github.com/anthropics/claude-plugins-official/blob/main/LICENSE

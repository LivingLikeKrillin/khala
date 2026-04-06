#!/usr/bin/env node

/**
 * Probe MCP 서버
 *
 * Probe의 분석 엔진을 MCP(Model Context Protocol) 서버로 노출한다.
 * Claude Code에서 자연어 대화 중에 도구로 호출할 수 있다.
 *
 * 실행: node dist/mcp/server.js
 * 등록: .claude/settings.json → mcpServers.probe
 *
 * 규정 문서: docs/probe-v0.3-scope.md § 2
 */

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { registerTools } from './tools.js';
import { registerResources } from './resources.js';
import { registerPrompts } from './prompts.js';

const server = new McpServer({
  name: 'probe',
  version: '0.4.0',
});

// 도구 등록 (6개)
registerTools(server);

// 리소스 등록 (3개)
registerResources(server);

// 프롬프트 등록 (2개)
registerPrompts(server);

// stdio transport로 실행
const transport = new StdioServerTransport();
await server.connect(transport);

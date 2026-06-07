import { describe, it, expect } from 'vitest';
import { registerTools } from '../src/mcp/tools.js';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';

/** registerTools가 등록하는 도구 이름을 수집하는 최소 스파이 서버.
 *  registerTools는 server.tool(name, desc, schema, handler)만 호출하므로
 *  tool 메서드만 있으면 충분하다 (핸들러는 등록 시 호출되지 않음). */
function collectToolNames(): string[] {
  const names: string[] = [];
  const fakeServer = {
    tool: (name: string) => {
      names.push(name);
    },
  } as unknown as McpServer;
  registerTools(fakeServer);
  return names;
}

describe('MCP 도구 등록', () => {
  it('probe.groundReview를 포함해 8개 도구가 등록된다', () => {
    const names = collectToolNames();
    expect(names).toContain('probe.groundReview');
    expect(names).toContain('probe.groundTroubleshooting');
    expect(names.length).toBe(8);
  });
});

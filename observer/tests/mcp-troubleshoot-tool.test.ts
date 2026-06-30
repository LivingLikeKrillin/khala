import { describe, it, expect } from 'vitest';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { registerTools } from '../src/mcp/tools.js';

describe('observer.groundTroubleshooting 등록', () => {
  it('registerTools가 groundTroubleshooting 도구를 등록한다', () => {
    const names: string[] = [];
    const fake = {
      tool: (name: string) => {
        names.push(name);
      },
    };
    registerTools(fake as unknown as McpServer);
    expect(names).toContain('observer.groundTroubleshooting');
  });
});

/**
 * MCP 리소스 핸들러
 *
 * Claude에게 참조 데이터를 제공한다.
 * 3개 리소스: profiles, config, guidelines
 *
 * 규정 문서: docs/probe-v0.3-scope.md § 4
 */

import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { ResourceTemplate } from '@modelcontextprotocol/sdk/server/mcp.js';
import { springBootProfile } from '../profiles/spring-boot.js';
import { nextjsProfile } from '../profiles/nextjs.js';
import { reactSpaProfile } from '../profiles/react-spa.js';
import { loadConfigAsync } from '../core/config-loader.js';
import type { PlatformProfile } from '../profiles/types.js';

const PROFILES: Record<string, PlatformProfile> = {
  'spring-boot': springBootProfile,
  'nextjs': nextjsProfile,
  'react-spa': reactSpaProfile,
};

const GUIDELINE_FILES: Record<string, string> = {
  'api-contract': 'docs/guidelines/api-contract-guidelines.md',
  'state-matrix': 'docs/guidelines/state-matrix-guidelines.md',
  'ui-change': 'docs/guidelines/ui-change-guidelines-v2.md',
};

/**
 * MCP 서버에 리소스를 등록한다.
 */
export function registerResources(server: McpServer): void {
  // ─── probe://profiles/{platform} ───
  server.resource(
    'profiles',
    new ResourceTemplate('probe://profiles/{platform}', { list: undefined }),
    async (uri, { platform }) => {
      const platformName = Array.isArray(platform) ? platform[0] : platform;
      const profile = platformName ? PROFILES[platformName] : undefined;

      if (!profile) {
        return {
          contents: [{
            uri: uri.href,
            mimeType: 'application/json',
            text: JSON.stringify({ error: `알 수 없는 플랫폼: ${platformName}` }),
          }],
        };
      }

      return {
        contents: [{
          uri: uri.href,
          mimeType: 'application/json',
          text: JSON.stringify(profile, null, 2),
        }],
      };
    },
  );

  // ─── probe://config ───
  server.resource(
    'config',
    'probe://config',
    async (uri) => {
      const config = await loadConfigAsync();

      return {
        contents: [{
          uri: uri.href,
          mimeType: 'application/json',
          text: JSON.stringify(config, null, 2),
        }],
      };
    },
  );

  // ─── probe://guidelines/{name} ───
  server.resource(
    'guidelines',
    new ResourceTemplate('probe://guidelines/{name}', { list: undefined }),
    async (uri, { name }) => {
      const guideName = Array.isArray(name) ? name[0] : name;
      const filePath = guideName ? GUIDELINE_FILES[guideName] : undefined;

      if (!filePath) {
        return {
          contents: [{
            uri: uri.href,
            mimeType: 'text/plain',
            text: `알 수 없는 규정: ${guideName}\n사용 가능: ${Object.keys(GUIDELINE_FILES).join(', ')}`,
          }],
        };
      }

      const fullPath = join(process.cwd(), filePath);

      if (!existsSync(fullPath)) {
        return {
          contents: [{
            uri: uri.href,
            mimeType: 'text/plain',
            text: `규정 파일을 찾을 수 없습니다: ${filePath}`,
          }],
        };
      }

      const content = readFileSync(fullPath, 'utf-8');

      return {
        contents: [{
          uri: uri.href,
          mimeType: 'text/markdown',
          text: content,
        }],
      };
    },
  );
}

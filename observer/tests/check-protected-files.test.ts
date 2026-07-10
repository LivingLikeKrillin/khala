/**
 * PreToolUse 훅 — 자동 생성 파일의 수작업 편집 차단.
 *
 * 이 훅은 그동안 **한 번도 동작한 적이 없다.** settings.json 이 `node ./scripts/*.sh` 로
 * 불렀고, node 는 `.sh` 를 못 읽어 매번 죽었으며, `|| true` 가 그 실패를 삼켰다.
 * 그래서 아무것도 막지 못했고, 아무도 몰랐다.
 *
 * 되살리기 전에 실제로 밟아 본다. 특히 **오탐**: 훅이 페이로드 JSON 전체를 grep 하면,
 * 보호 경로를 *언급*하기만 하는 무해한 문서 편집까지 막는다.
 */

import { execFileSync } from 'node:child_process';
import { describe, expect, it } from 'vitest';

const SCRIPT = 'scripts/check-protected-files.sh';

/** 훅을 실제로 실행하고 exit code 를 돌려준다. 2 = block. */
function runHook(payload: unknown): number {
  try {
    execFileSync('bash', [SCRIPT], {
      input: JSON.stringify(payload),
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return 0;
  } catch (e: any) {
    return e.status ?? -1;
  }
}

describe('check-protected-files', () => {
  it('blocks an edit to a generated file', () => {
    expect(runHook({ tool_input: { file_path: 'src/api/types.ts' } })).toBe(2);
  });

  it('blocks a generated file reached through a longer path', () => {
    expect(runHook({ tool_input: { file_path: 'observer/api/openapi.json' } })).toBe(2);
  });

  it('allows an ordinary file', () => {
    expect(runHook({ tool_input: { file_path: 'src/App.tsx' } })).toBe(0);
  });

  it('does not block a file that merely mentions a protected path in its content', () => {
    // 이전 구현은 페이로드 전체를 grep 해서, 이 편집을 막았다. 문서를 못 쓰게 만드는 가드다.
    expect(
      runHook({
        tool_input: {
          file_path: 'docs/guide.md',
          content: 'api/openapi.json 은 자동 생성되므로 손대지 마세요.',
        },
      }),
    ).toBe(0);
  });

  it('does not block when a protected name appears only as a substring of another file', () => {
    expect(runHook({ tool_input: { file_path: 'src/api/types.ts.bak' } })).toBe(0);
  });

  it('allows a payload with no file_path at all', () => {
    expect(runHook({ tool_input: {} })).toBe(0);
  });

  it('does not hang when given neither an argument nor stdin', () => {
    // `TOOL_INPUT="${1:-$(cat)}"` 는 stdin 이 tty 면 매달린다. /dev/null 이면 즉시 끝나야 한다.
    const out = execFileSync('bash', [SCRIPT], { input: '', stdio: ['pipe', 'pipe', 'pipe'] });
    expect(out.toString()).toBe('');
  });
});

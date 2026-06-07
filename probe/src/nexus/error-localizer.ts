/**
 * 에러/스택트레이스 → 의심 지점(Suspect) 국소화
 *
 * 순수 로컬(Nexus 호출 없음). 스택트레이스 프레임·파일 경로·사용자 지정에서
 * service/entity 후보를 추출해 confidence 내림차순으로 반환한다.
 *
 * 주의(스펙 §4.2 seam): Archon 코드 심볼 인덱스가 생기면 그쪽을 결정론적 1순위로,
 * 본 휴리스틱은 fallback이 된다. 따라서 과투자하지 않는다 (스펙 Q2).
 *
 * 규정 문서: docs/superpowers/specs/2026-06-06-troubleshooting-grounding-design.md §1, §3.3
 */

import type { TroubleshootInput, Suspect } from './types.js';

/** Java/Kotlin 프레임: at a.b.c.ClassName.method(File.java:88) */
const JAVA_FRAME = /\bat\s+(?:[\w$]+\.)*([A-Z][\w$]+)\.[\w$<>]+\(/g;
/** 파일 경로 프레임: src/order/order-service.ts:88 또는 (order-service.ts:88) */
const PATH_FRAME = /([\w-]+)(?:\.(?:ts|tsx|js|jsx|java|kt|py))\b/g;
/** service 후보로 보는 흔한 접미사 (제거 대상 — Service는 kebab으로 보존) */
const ROLE_SUFFIX = /(Controller|Repository|Handler|Manager|UseCase|Component)$/;

/** PascalCase/대문자 클래스명을 kebab service명으로 정규화 */
function toServiceName(symbol: string): string {
  const stripped = symbol.replace(ROLE_SUFFIX, '');
  return stripped
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[_\s]+/g, '-')
    .toLowerCase();
}

/**
 * 에러 신호에서 의심 지점을 국소화한다.
 *
 * @param input 트러블슈팅 입력
 * @returns confidence 내림차순 Suspect 배열 (없으면 빈 배열)
 */
export function localizeError(input: TroubleshootInput): Suspect[] {
  const byName = new Map<string, Suspect>();

  const add = (
    entityName: string,
    ev: Suspect['evidence'][number],
    score: number,
  ): void => {
    if (!entityName) return;
    const existing = byName.get(entityName);
    if (existing) {
      existing.evidence.push(ev);
      existing.confidence = Math.min(1, existing.confidence + 0.15);
    } else {
      byName.set(entityName, { entityName, evidence: [ev], confidence: score });
    }
  };

  // 1) 사용자 지정 — 최상위
  for (const svc of input.suspectServices ?? []) {
    add(svc, { kind: 'user', raw: svc }, 1);
  }

  // 2) Java/Kotlin 프레임
  for (const m of input.signal.matchAll(JAVA_FRAME)) {
    const cls = m[1]!;
    add(toServiceName(cls), { kind: 'frame', raw: m[0]!.trim() }, 0.6);
  }

  // 3) 파일 경로 프레임
  for (const m of input.signal.matchAll(PATH_FRAME)) {
    const file = m[1]!;
    add(toServiceName(file), { kind: 'path', raw: m[0]! }, 0.45);
  }

  return [...byName.values()].sort((a, b) => b.confidence - a.confidence);
}

/**
 * kind 힌트가 없을 때 신호 본문으로 종류를 추론한다.
 */
export function inferKind(signal: string): NonNullable<TroubleshootInput['kind']> {
  if (/\bat\s+[\w$.]+\(|\n\s+at\s/.test(signal)) return 'stacktrace';
  if (/\b(FAIL|AssertionError|expected .* to|✗|✕)\b/.test(signal)) return 'test-failure';
  if (/\b(Error|Exception|errno|stack)\b/i.test(signal)) return 'error';
  return 'incident';
}

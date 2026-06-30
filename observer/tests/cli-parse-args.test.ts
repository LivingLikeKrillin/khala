import { describe, it, expect } from 'vitest';
import { parseArgs, parseTroubleshootArgs, parseReviewGroundArgs } from '../src/cli/parse-args.js';

describe('parseArgs', () => {
  it('인자 없으면 기본값을 반환한다', () => {
    const result = parseArgs([]);

    expect(result.base).toBe('origin/main');
    expect(result.format).toBe('markdown');
    expect(result.silent).toBe(false);
    expect(result.spec).toBe('');
  });

  it('--base 옵션을 파싱한다', () => {
    const result = parseArgs(['--base', 'origin/develop']);

    expect(result.base).toBe('origin/develop');
  });

  it('--format json을 파싱한다', () => {
    const result = parseArgs(['--format', 'json']);

    expect(result.format).toBe('json');
  });

  it('--format brief를 파싱한다', () => {
    const result = parseArgs(['--format', 'brief']);

    expect(result.format).toBe('brief');
  });

  it('유효하지 않은 format은 기본값 markdown을 유지한다', () => {
    const result = parseArgs(['--format', 'invalid']);

    expect(result.format).toBe('markdown');
  });

  it('--silent 플래그를 파싱한다', () => {
    const result = parseArgs(['--silent']);

    expect(result.silent).toBe(true);
  });

  it('--spec 옵션을 파싱한다', () => {
    const result = parseArgs(['--spec', 'api/v2/openapi.yaml']);

    expect(result.spec).toBe('api/v2/openapi.yaml');
  });

  it('위치 인자(positional)를 spec으로 처리한다', () => {
    const result = parseArgs(['api/openapi.json']);

    expect(result.spec).toBe('api/openapi.json');
  });

  it('--spec이 위치 인자보다 우선한다', () => {
    const result = parseArgs(['--spec', 'explicit.json', 'positional.json']);

    expect(result.spec).toBe('explicit.json');
  });

  it('여러 옵션을 동시에 파싱한다', () => {
    const result = parseArgs(['--base', 'origin/release', '--format', 'brief', '--silent', '--spec', 'api/spec.json']);

    expect(result.base).toBe('origin/release');
    expect(result.format).toBe('brief');
    expect(result.silent).toBe(true);
    expect(result.spec).toBe('api/spec.json');
  });
});

describe('parseTroubleshootArgs', () => {
  it('인자 신호와 플래그를 파싱한다', () => {
    const o = parseTroubleshootArgs([
      'NPE at X',
      '--kind',
      'stacktrace',
      '--suspect',
      'order-service',
      '--format',
      'json',
    ]);
    expect(o.signal).toBe('NPE at X');
    expect(o.kind).toBe('stacktrace');
    expect(o.suspectServices).toContain('order-service');
    expect(o.format).toBe('json');
  });
  it('--diff-base를 받는다', () => {
    const o = parseTroubleshootArgs(['err', '--diff-base', 'origin/main']);
    expect(o.diffBase).toBe('origin/main');
  });
});

it('parseReviewGroundArgs는 --base/--format을 파싱한다', () => {
  const o = parseReviewGroundArgs(['--base', 'main', '--format', 'json']);
  expect(o.base).toBe('main');
  expect(o.format).toBe('json');
});
it('기본 format은 markdown, base는 undefined', () => {
  const o = parseReviewGroundArgs([]);
  expect(o.format).toBe('markdown');
  expect(o.base).toBeUndefined();
});

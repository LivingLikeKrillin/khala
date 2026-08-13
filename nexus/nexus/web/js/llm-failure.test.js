import { describe, it, expect } from 'vitest';
import { failureNotice, isTransient } from './llm-failure.js';

describe('failureNotice', () => {
  it('says nothing when the answer succeeded', () => {
    expect(failureNotice({ llm_failed: false })).toBeNull();
    expect(failureNotice({})).toBeNull();
    expect(failureNotice(undefined)).toBeNull();
  });

  it('tells the user to fetch a human when credits ran out — not to wait', () => {
    // 이 파일이 있는 이유. "잠시 후 다시" 라고 말하면 아무도 결제하지 않는다.
    const m = failureNotice({ llm_failed: true, llm_failure_reason: 'quota' });
    expect(m).toContain('크레딧');
    expect(m).toContain('운영자');
    expect(m).not.toContain('잠시 후');
  });

  it('tells the user to wait only when waiting actually helps', () => {
    for (const reason of ['rate_limit', 'unavailable']) {
      expect(failureNotice({ llm_failed: true, llm_failure_reason: reason })).toContain('잠시 후');
    }
  });

  it('falls back without claiming the failure is temporary', () => {
    // 모르는 사유(그리고 사유를 안 보내는 옛 서버)에 "기다리면 된다" 라고 하면,
    // 영원히 실패하는 것에 대해 기다리라고 말하게 된다.
    for (const done of [{ llm_failed: true, llm_failure_reason: 'other' },
                        { llm_failed: true, llm_failure_reason: undefined }]) {
      const m = failureNotice(done);
      expect(m).toBeTruthy();
      expect(m).not.toContain('잠시 후');
    }
  });

  it('never leaks a provider string into the UI', () => {
    for (const reason of ['quota', 'auth', 'rate_limit', 'unavailable', 'other', undefined]) {
      const m = failureNotice({ llm_failed: true, llm_failure_reason: reason });
      expect(m).not.toMatch(/Anthropic|credit balance|invalid_request_error/);
    }
  });
});

describe('isTransient', () => {
  it('is the same axis the server uses', () => {
    expect(isTransient('rate_limit')).toBe(true);
    expect(isTransient('unavailable')).toBe(true);
    expect(isTransient('quota')).toBe(false);
    expect(isTransient('auth')).toBe(false);
    expect(isTransient('other')).toBe(false);
    expect(isTransient(undefined)).toBe(false);
  });
});

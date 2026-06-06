import { describe, it, expect } from 'vitest';
import { localizeError } from '../src/khala/error-localizer.js';

describe('localizeError — Java 스택트레이스', () => {
  it('클래스명을 kebab service로 정규화한다', () => {
    const signal = 'java.lang.NullPointerException\n\tat com.shop.order.OrderService.checkout(OrderService.java:88)';
    const suspects = localizeError({ signal, kind: 'stacktrace' });
    expect(suspects[0]!.entityName).toBe('order-service');
    expect(suspects[0]!.confidence).toBeGreaterThan(0.3);
    expect(suspects[0]!.evidence.some((e) => e.kind === 'frame')).toBe(true);
  });

  it('Service/Controller/Repository 접미사를 제거한다', () => {
    const signal = '\tat com.shop.PaymentController.pay(PaymentController.java:12)';
    const suspects = localizeError({ signal, kind: 'stacktrace' });
    expect(suspects[0]!.entityName).toBe('payment');
  });

  it('suspectServices 사용자 지정을 최상위 confidence로 포함한다', () => {
    const suspects = localizeError({ signal: '에러 발생', suspectServices: ['inventory-service'] });
    expect(suspects[0]!.entityName).toBe('inventory-service');
    expect(suspects[0]!.evidence[0]!.kind).toBe('user');
    expect(suspects[0]!.confidence).toBe(1);
  });

  it('의심 지점이 없으면 빈 배열을 반환한다', () => {
    expect(localizeError({ signal: '그냥 텍스트' })).toEqual([]);
  });
});

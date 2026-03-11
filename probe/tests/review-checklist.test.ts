import { describe, it, expect } from 'vitest';
import { detectPrType } from '../src/review/pr-type-detector.js';
import { generateChecklist } from '../src/review/checklist-generator.js';

describe('PR 타입 추론', () => {
  it('entity + service + controller + dto → domain-crud', () => {
    const roles = ['entity', 'service', 'controller', 'dto', 'test'];
    expect(detectPrType(roles)).toBe('domain-crud');
  });

  it('entity + service → domain-crud', () => {
    const roles = ['entity', 'service'];
    expect(detectPrType(roles)).toBe('domain-crud');
  });

  it('controller + dto + openapi 변경 → api-change', () => {
    const roles = ['controller', 'dto', 'test'];
    expect(detectPrType(roles, true)).toBe('api-change');
  });

  it('page + component + hook → ui-feature', () => {
    const roles = ['page', 'component', 'hook'];
    expect(detectPrType(roles)).toBe('ui-feature');
  });

  it('component + story + test → ui-component', () => {
    const roles = ['component', 'story', 'test'];
    expect(detectPrType(roles)).toBe('ui-component');
  });

  it('config만 → config-change', () => {
    const roles = ['config'];
    expect(detectPrType(roles)).toBe('config-change');
  });

  it('migration만 → db-migration', () => {
    const roles = ['migration'];
    expect(detectPrType(roles)).toBe('db-migration');
  });

  it('test만 → test-only', () => {
    const roles = ['test', 'test', 'test'];
    expect(detectPrType(roles)).toBe('test-only');
  });

  it('token → design-system', () => {
    const roles = ['token', 'component'];
    expect(detectPrType(roles)).toBe('design-system');
  });

  it('빈 역할 목록 → general', () => {
    expect(detectPrType([])).toBe('general');
  });
});

describe('체크리스트 생성', () => {
  it('domain-crud 타입에 필수 항목이 포함된다', () => {
    const checklist = generateChecklist('domain-crud');

    expect(checklist.prType).toBe('domain-crud');
    expect(checklist.items.length).toBeGreaterThan(0);

    // 필수 항목 확인
    const required = checklist.items.filter((i) => i.priority === 'required');
    expect(required.length).toBeGreaterThan(0);

    // nullable/required 확인 항목이 있는지
    expect(checklist.items.some((i) => i.id === 'dc-nullable-spec')).toBe(true);
  });

  it('api-change 타입에 breaking 관련 항목이 포함된다', () => {
    const checklist = generateChecklist('api-change');

    expect(checklist.items.some((i) => i.id === 'ac-breaking-agreement')).toBe(true);
    expect(checklist.items.some((i) => i.id === 'ac-migration-guide')).toBe(true);
  });

  it('ui-feature 타입에 State Matrix 항목이 포함된다', () => {
    const checklist = generateChecklist('ui-feature');

    expect(checklist.items.some((i) => i.id === 'uf-state-matrix')).toBe(true);
    expect(checklist.items.some((i) => i.description.includes('loading'))).toBe(true);
  });

  it('커스텀 항목 추가가 반영된다', () => {
    const checklist = generateChecklist('domain-crud', {
      customItems: {
        'domain-crud': [
          { id: 'custom-audit', description: '감사 로그가 기록되는지 확인' },
        ],
      },
    });

    expect(checklist.items.some((i) => i.id === 'custom-audit')).toBe(true);
  });

  it('disableChecklists로 비활성화하면 빈 체크리스트를 반환한다', () => {
    const checklist = generateChecklist('domain-crud', {
      disableChecklists: ['domain-crud'],
    });

    expect(checklist.items.length).toBe(0);
  });

  it('테스트 파일이 있으면 자동 검증이 통과한다', () => {
    const checklist = generateChecklist('domain-crud', {
      changedFiles: [
        'src/main/kotlin/service/UserService.kt',
        'src/test/kotlin/service/UserServiceTest.kt',
      ],
    });

    const testVerified = checklist.autoVerified.find((v) => v.id === 'dc-service-test');
    expect(testVerified?.passed).toBe(true);
  });

  it('테스트 파일이 없으면 자동 검증이 실패한다', () => {
    const checklist = generateChecklist('domain-crud', {
      changedFiles: [
        'src/main/kotlin/service/UserService.kt',
      ],
    });

    const testVerified = checklist.autoVerified.find((v) => v.id === 'dc-service-test');
    expect(testVerified?.passed).toBe(false);
  });

  it('스토리 파일이 있으면 자동 검증이 통과한다 (ui-component)', () => {
    const checklist = generateChecklist('ui-component', {
      changedFiles: [
        'components/Button/Button.tsx',
        'components/Button/Button.stories.tsx',
      ],
    });

    const storyVerified = checklist.autoVerified.find((v) => v.id === 'uc-story');
    expect(storyVerified?.passed).toBe(true);
  });
});

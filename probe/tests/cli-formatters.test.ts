import { describe, it, expect } from 'vitest';
import {
  formatScopeMarkdown,
  formatScopeBrief,
  formatLintMarkdown,
  formatDiffMarkdown,
  formatReviewMarkdown,
} from '../src/cli/formatters.js';
import type { ScopeAnalysisResult } from '../src/core/scope-analyzer.js';
import type { ApiLintResult, ApiDiffResult } from '../src/api/types.js';
import type { ReviewChecklist } from '../src/review/types.js';

// ─── 테스트 데이터 팩토리 ───

function makeOkScopeResult(overrides?: Partial<ScopeAnalysisResult>): ScopeAnalysisResult {
  return {
    severity: 'ok',
    groups: [
      {
        groupName: 'domain-crud',
        cohesionKeyValue: 'User',
        files: [
          { path: 'src/entity/User.kt', role: 'entity' },
          { path: 'src/service/UserService.kt', role: 'service' },
        ],
      },
    ],
    mixedConcerns: [],
    totalFiles: 2,
    totalDiffLines: 50,
    ...overrides,
  };
}

function makeWarnScopeResult(): ScopeAnalysisResult {
  return {
    severity: 'warn',
    groups: [
      {
        groupName: 'domain-crud',
        cohesionKeyValue: 'User',
        files: [
          { path: 'src/entity/User.kt', role: 'entity' },
          { path: 'src/service/UserService.kt', role: 'service' },
        ],
      },
      {
        groupName: 'config-change',
        cohesionKeyValue: 'configGroup',
        files: [
          { path: 'src/config/AppConfig.kt', role: 'config' },
        ],
      },
      {
        groupName: 'migration',
        cohesionKeyValue: 'migrationGroup',
        files: [
          { path: 'db/V1__init.sql', role: 'migration' },
        ],
      },
    ],
    mixedConcerns: [
      { roles: ['migration', 'controller'], reason: '마이그레이션과 컨트롤러는 분리 필수' },
    ],
    totalFiles: 4,
    totalDiffLines: 200,
    splitSuggestion: {
      proposedPrs: [
        { description: 'migration — migrationGroup (1개 파일)', files: ['db/V1__init.sql'], order: 1 },
        { description: 'config-change — configGroup (1개 파일)', files: ['src/config/AppConfig.kt'], order: 2 },
        { description: 'domain-crud — User (2개 파일)', files: ['src/entity/User.kt', 'src/service/UserService.kt'], order: 3 },
      ],
    },
  };
}

// ─── formatScopeMarkdown ───

describe('formatScopeMarkdown', () => {
  it('정상 결과에서 Probe 헤더와 그룹 요약을 포함한다', () => {
    const result = makeOkScopeResult();
    const output = formatScopeMarkdown(result);

    expect(output).toContain('Probe');
    expect(output).toContain('정상 범위');
    expect(output).toContain('domain-crud (User)');
    expect(output).toContain('2개 파일');
    expect(output).toContain('+50줄');
  });

  it('정상 결과에서 그룹이 없으면 "분석 완료"를 표시한다', () => {
    const result = makeOkScopeResult({ groups: [], totalFiles: 0, totalDiffLines: 0 });
    const output = formatScopeMarkdown(result);

    expect(output).toContain('분석 완료');
  });

  it('경고 결과에서 그룹 목록과 파일을 나열한다', () => {
    const result = makeWarnScopeResult();
    const output = formatScopeMarkdown(result);

    expect(output).toContain('3개의 서로 다른 관심사');
    expect(output).toContain('그룹 1:');
    expect(output).toContain('그룹 2:');
    expect(output).toContain('그룹 3:');
    expect(output).toContain('src/entity/User.kt');
  });

  it('경고 결과에서 mixedConcerns 경고를 포함한다', () => {
    const result = makeWarnScopeResult();
    const output = formatScopeMarkdown(result);

    expect(output).toContain('관심사 혼재 경고');
    expect(output).toContain('마이그레이션과 컨트롤러는 분리 필수');
  });

  it('경고 결과에서 분할 제안을 포함한다', () => {
    const result = makeWarnScopeResult();
    const output = formatScopeMarkdown(result);

    expect(output).toContain('제안하는 분할');
    expect(output).toContain('PR 1:');
    expect(output).toContain('PR 2:');
    expect(output).toContain('PR 3:');
  });

  it('체크리스트가 있으면 리뷰 체크리스트를 추가한다', () => {
    const result = makeOkScopeResult();
    const checklist: ReviewChecklist = {
      prType: 'domain-crud',
      items: [
        { description: '서비스 테스트 존재', category: 'test', priority: 'required' },
      ],
      autoVerified: [
        { description: '서비스 테스트 존재', passed: true },
      ],
      manualRequired: [
        { description: 'Entity 필드 매핑 확인', priority: 'required' },
      ],
    };
    const output = formatScopeMarkdown(result, checklist);

    expect(output).toContain('리뷰 체크리스트 (domain-crud)');
    expect(output).toContain('서비스 테스트 존재');
  });

  it('체크리스트 items가 비어있으면 체크리스트를 추가하지 않는다', () => {
    const result = makeOkScopeResult();
    const checklist: ReviewChecklist = {
      prType: 'general',
      items: [],
      autoVerified: [],
      manualRequired: [],
    };
    const output = formatScopeMarkdown(result, checklist);

    expect(output).not.toContain('리뷰 체크리스트');
  });
});

// ─── formatScopeBrief ───

describe('formatScopeBrief', () => {
  it('한 줄 요약을 반환한다', () => {
    const result = makeOkScopeResult();
    const output = formatScopeBrief(result);

    expect(output).toContain('정상 범위');
    expect(output).toContain('2개 파일');
    expect(output).toContain('1개 그룹');
    expect(output).toContain('0개 혼재 경고');
  });

  it('경고 시 severity label이 바뀐다', () => {
    const result = makeWarnScopeResult();
    const output = formatScopeBrief(result);

    expect(output).toContain('PR 범위 경고');
  });
});

// ─── formatLintMarkdown ───

describe('formatLintMarkdown', () => {
  it('에러/경고 0건이면 통과 메시지를 반환한다', () => {
    const result: ApiLintResult = {
      violations: [],
      summary: { errors: 0, warnings: 0, total: 0 },
    };
    const output = formatLintMarkdown(result);

    expect(output).toContain('0개 에러, 0개 경고');
  });

  it('위반사항이 있으면 상세 내용을 나열한다', () => {
    const result: ApiLintResult = {
      violations: [
        {
          ruleId: 'probe/nullable',
          severity: 'error',
          path: '#/paths/~1users/get/responses/200',
          message: 'nullable 필드가 명시되지 않았습니다',
          fix: 'nullable: true 추가',
        },
      ],
      summary: { errors: 1, warnings: 0, total: 1 },
    };
    const output = formatLintMarkdown(result);

    expect(output).toContain('1개 에러');
    expect(output).toContain('probe/nullable');
    expect(output).toContain('nullable 필드가 명시되지 않았습니다');
    expect(output).toContain('수정:');
  });
});

// ─── formatDiffMarkdown ───

describe('formatDiffMarkdown', () => {
  it('변경 없으면 "변경 없음"을 반환한다', () => {
    const result: ApiDiffResult = {
      changes: [],
      summary: { added: 0, modified: 0, removed: 0, deprecated: 0, hasBreaking: false },
    };
    const output = formatDiffMarkdown(result);

    expect(output).toContain('변경 없음');
  });

  it('breaking 변경이 있으면 경고 라벨을 포함한다', () => {
    const result: ApiDiffResult = {
      changes: [
        {
          endpoint: 'DELETE /users/{id}',
          type: 'removed',
          breaking: true,
          details: ['엔드포인트 삭제됨'],
        },
      ],
      summary: { added: 0, modified: 0, removed: 1, deprecated: 0, hasBreaking: true },
      suggestedLabel: 'breaking-change',
    };
    const output = formatDiffMarkdown(result);

    expect(output).toContain('breaking 변경 포함');
    expect(output).toContain('DELETE /users/{id}');
    expect(output).toContain('권장 PR 라벨: breaking-change');
  });

  it('호환 변경이면 "호환 변경" 라벨을 사용한다', () => {
    const result: ApiDiffResult = {
      changes: [
        {
          endpoint: 'POST /users',
          type: 'added',
          breaking: false,
          details: ['새 엔드포인트'],
        },
      ],
      summary: { added: 1, modified: 0, removed: 0, deprecated: 0, hasBreaking: false },
    };
    const output = formatDiffMarkdown(result);

    expect(output).toContain('호환 변경');
    expect(output).toContain('1개 추가');
  });
});

// ─── formatReviewMarkdown ───

describe('formatReviewMarkdown', () => {
  it('PR 타입과 체크리스트를 마크다운으로 포맷한다', () => {
    const checklist: ReviewChecklist = {
      prType: 'api-change',
      items: [
        { description: 'API 스펙 린트 통과', category: 'api', priority: 'required' },
        { description: '하위 호환성 확인', category: 'api', priority: 'required' },
        { description: '문서 업데이트', category: 'docs', priority: 'recommended' },
      ],
      autoVerified: [
        { description: 'API 스펙 린트 통과', passed: true, detail: '0개 에러' },
      ],
      manualRequired: [
        { description: '하위 호환성 확인', priority: 'required', guidelineRef: '규정 ② 2.1' },
        { description: '문서 업데이트', priority: 'recommended' },
      ],
    };
    const output = formatReviewMarkdown(checklist);

    expect(output).toContain('리뷰 체크리스트 (api-change)');
    expect(output).toContain('자동 검증 결과');
    expect(output).toContain('API 스펙 린트 통과');
    expect(output).toContain('## 필수');
    expect(output).toContain('하위 호환성 확인');
    expect(output).toContain('규정 ② 2.1');
    expect(output).toContain('## 권장');
    expect(output).toContain('문서 업데이트');
  });

  it('자동 검증이 없으면 해당 섹션을 생략한다', () => {
    const checklist: ReviewChecklist = {
      prType: 'general',
      items: [
        { description: '테스트 확인', category: 'test', priority: 'required' },
      ],
      autoVerified: [],
      manualRequired: [
        { description: '테스트 확인', priority: 'required' },
      ],
    };
    const output = formatReviewMarkdown(checklist);

    expect(output).not.toContain('자동 검증 결과');
    expect(output).toContain('## 필수');
  });
});

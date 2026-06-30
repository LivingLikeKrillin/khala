import { describe, it, expect } from 'vitest';
import { globMatch } from '../src/utils/glob-match.js';

describe('glob-match', () => {
  it('** 패턴은 디렉토리 깊이를 넘어 매칭한다', () => {
    expect(globMatch('src/main/kotlin/entity/User.kt', '**/entity/**')).toBe(true);
    expect(globMatch('a/b/c/entity/Foo.kt', '**/entity/**')).toBe(true);
  });

  it('* 패턴은 단일 세그먼트만 매칭한다', () => {
    expect(globMatch('app/dashboard/page.tsx', 'app/*/page.tsx')).toBe(true);
    expect(globMatch('app/a/b/page.tsx', 'app/*/page.tsx')).toBe(false);
  });

  it('**/ 패턴은 0개 이상 디렉토리에 매칭한다', () => {
    expect(globMatch('middleware.ts', '**/middleware.*')).toBe(true);
    expect(globMatch('src/middleware.ts', '**/middleware.*')).toBe(true);
  });

  it('확장자 패턴이 정확히 매칭한다', () => {
    expect(globMatch('src/components/Card.stories.tsx', '**/*.stories.*')).toBe(true);
    expect(globMatch('src/components/Card.tsx', '**/*.stories.*')).toBe(false);
  });

  it('app/**/page.tsx 패턴', () => {
    expect(globMatch('app/dashboard/page.tsx', 'app/**/page.tsx')).toBe(true);
    expect(globMatch('app/settings/profile/page.tsx', 'app/**/page.tsx')).toBe(true);
  });

  it('백슬래시 경로도 정규화하여 매칭한다', () => {
    expect(globMatch('src\\main\\entity\\User.kt', '**/entity/**')).toBe(true);
  });
});

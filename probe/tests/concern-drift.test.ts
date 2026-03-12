import { describe, it, expect } from 'vitest';
import { detectConcernDrift } from '../src/core/concern-drift.js';
import { springBootProfile } from '../src/profiles/spring-boot.js';
import { nextjsProfile } from '../src/profiles/nextjs.js';

describe('detectConcernDrift', () => {
  // ─── 드리프트 없음 ───

  it('변경 파일이 1개면 드리프트 없음', () => {
    const result = detectConcernDrift(
      ['src/main/kotlin/service/UserService.kt'],
      'src/main/kotlin/service/UserService.kt',
      springBootProfile,
    );

    expect(result.drifted).toBe(false);
  });

  it('같은 도메인 CRUD 내 파일 추가는 드리프트 없음', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
    ];

    const result = detectConcernDrift(
      files,
      'src/main/kotlin/controller/UserController.kt',
      springBootProfile,
    );

    expect(result.drifted).toBe(false);
  });

  it('Next.js 같은 페이지 내 컴포넌트 추가는 드리프트 없음', () => {
    const files = [
      'app/dashboard/page.tsx',
      'app/dashboard/loading.tsx',
      'components/dashboard/StatsCard.tsx',
    ];

    const result = detectConcernDrift(
      files,
      'components/dashboard/StatsCard.tsx',
      nextjsProfile,
    );

    expect(result.drifted).toBe(false);
  });

  // ─── 드리프트 감지 ───

  it('User CRUD 작업 중 config 파일 편집 시 드리프트 감지 (spring-boot)', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/resources/application.yml',
    ];

    const result = detectConcernDrift(
      files,
      'src/main/resources/application.yml',
      springBootProfile,
    );

    expect(result.drifted).toBe(true);
    expect(result.primaryGroup).toContain('User');
    expect(result.message).toContain('다른 관심사');
    expect(result.message).toContain('분리');
  });

  it('User CRUD 작업 중 마이그레이션 파일 추가 시 드리프트 감지 (spring-boot)', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/resources/db/migration/V3__add_user_table.sql',
    ];

    const result = detectConcernDrift(
      files,
      'src/main/resources/db/migration/V3__add_user_table.sql',
      springBootProfile,
    );

    expect(result.drifted).toBe(true);
    expect(result.message).not.toBeNull();
  });

  it('dashboard 페이지 작업 중 middleware 편집 시 드리프트 감지 (nextjs)', () => {
    const files = [
      'app/dashboard/page.tsx',
      'app/dashboard/loading.tsx',
      'middleware.ts',
    ];

    const result = detectConcernDrift(
      files,
      'middleware.ts',
      nextjsProfile,
    );

    expect(result.drifted).toBe(true);
    expect(result.message).toContain('다른 관심사');
  });

  it('dashboard 페이지 작업 중 api route 추가 시 드리프트 감지 (nextjs)', () => {
    const files = [
      'app/dashboard/page.tsx',
      'app/dashboard/loading.tsx',
      'components/dashboard/Chart.tsx',
      'app/api/users/route.ts',
    ];

    const result = detectConcernDrift(
      files,
      'app/api/users/route.ts',
      nextjsProfile,
    );

    expect(result.drifted).toBe(true);
  });

  // ─── 메시지 형식 ───

  it('드리프트 메시지에 주된 관심사와 새 관심사가 모두 포함된다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/resources/application.yml',
    ];

    const result = detectConcernDrift(
      files,
      'src/main/resources/application.yml',
      springBootProfile,
    );

    expect(result.drifted).toBe(true);
    expect(result.primaryGroup).not.toBeNull();
    expect(result.editedFileGroup).not.toBeNull();
    expect(result.primaryGroup).not.toBe(result.editedFileGroup);
  });

  it('드리프트 없을 때 message는 null', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
    ];

    const result = detectConcernDrift(
      files,
      'src/main/kotlin/service/UserService.kt',
      springBootProfile,
    );

    expect(result.message).toBeNull();
  });
});

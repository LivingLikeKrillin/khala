import { describe, it, expect } from 'vitest';
import { analyzeScope } from '../src/core/scope-analyzer.js';
import { springBootProfile } from '../src/profiles/spring-boot.js';
import { nextjsProfile } from '../src/profiles/nextjs.js';
import { reactSpaProfile } from '../src/profiles/react-spa.js';

describe('scope-analyzer', () => {
  // ─── Spring Boot ───

  it('단일 도메인 CRUD는 정상 범위로 판단한다 (spring-boot)', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/repository/UserRepository.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/kotlin/dto/UserRequest.kt',
      'src/main/kotlin/dto/UserResponse.kt',
      'src/test/kotlin/service/UserServiceTest.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 280);

    expect(result.severity).toBe('ok');
    expect(result.totalFiles).toBe(7);
    expect(result.groups.length).toBeLessThanOrEqual(2);
    expect(result.splitSuggestion).toBeUndefined();
  });

  it('서로 다른 도메인이 섞이면 경고한다 (spring-boot)', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/service/OrderService.kt',
      'src/main/kotlin/controller/OrderController.kt',
      'src/main/kotlin/config/SecurityConfig.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 400);

    // 3개 그룹: User domain, Order domain, config
    expect(result.severity).not.toBe('ok');
    expect(result.groups.length).toBeGreaterThanOrEqual(3);
  });

  it('migration + controller 조합은 분리를 제안한다 (spring-boot)', () => {
    const files = [
      'src/main/resources/db/migration/V3__add_user_table.sql',
      'src/main/resources/db/migration/V4__add_user_index.sql',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/kotlin/entity/User.kt',
    ];

    const result = analyzeScope(files, springBootProfile);

    expect(result.mixedConcerns.length).toBeGreaterThan(0);
    expect(result.mixedConcerns.some((mc) => mc.roles.includes('migration') && mc.roles.includes('controller'))).toBe(true);
  });

  // ─── Next.js ───

  it('페이지 단위 기능은 정상 범위로 판단한다 (nextjs)', () => {
    const files = [
      'app/dashboard/page.tsx',
      'app/dashboard/layout.tsx',
      'app/dashboard/loading.tsx',
      'components/dashboard/StatsCard.tsx',
      'components/dashboard/Chart.tsx',
    ];

    const result = analyzeScope(files, nextjsProfile, 200);

    expect(result.severity).toBe('ok');
    expect(result.totalFiles).toBe(5);
  });

  it('api route + page 조합은 분리를 권장한다 (nextjs)', () => {
    const files = [
      'app/dashboard/page.tsx',
      'app/dashboard/layout.tsx',
      'app/api/dashboard/route.ts',
      'components/dashboard/StatsCard.tsx',
    ];

    const result = analyzeScope(files, nextjsProfile);

    expect(result.mixedConcerns.some((mc) => mc.roles.includes('api-route') && mc.roles.includes('page'))).toBe(true);
  });

  it('middleware + component 조합은 분리를 제안한다 (nextjs)', () => {
    const files = [
      'middleware.ts',
      'lib/auth/session.ts',
      'components/dashboard/StatsCard.tsx',
    ];

    const result = analyzeScope(files, nextjsProfile);

    expect(result.mixedConcerns.some((mc) => mc.roles.includes('middleware') && mc.roles.includes('component'))).toBe(true);
  });

  // ─── React SPA ───

  it('기능 단위 변경은 정상 범위로 판단한다 (react-spa)', () => {
    const files = [
      'src/pages/dashboard/index.tsx',
      'src/components/dashboard/StatsCard.tsx',
      'src/hooks/useDashboard.ts',
      'src/components/dashboard/StatsCard.test.tsx',
    ];

    const result = analyzeScope(files, reactSpaProfile, 150);

    expect(result.severity).toBe('ok');
  });

  it('token + page 조합은 분리를 권장한다 (react-spa)', () => {
    const files = [
      'src/design-tokens/colors.ts',
      'src/pages/dashboard/index.tsx',
      'src/components/dashboard/StatsCard.tsx',
    ];

    const result = analyzeScope(files, reactSpaProfile);

    expect(result.mixedConcerns.some((mc) => mc.roles.includes('token') && mc.roles.includes('page'))).toBe(true);
  });

  // ─── 공통 로직 ───

  it('파일 수 임계치 초과 시 경고한다', () => {
    // spring-boot maxFilesPerPr = 20, 21개 파일 생성
    const files = Array.from({ length: 21 }, (_, i) =>
      `src/main/kotlin/service/Service${i}.kt`,
    );

    const result = analyzeScope(files, springBootProfile);

    expect(result.severity).toBe('warn');
  });

  it('diff 라인 수 임계치 초과 시 경고한다', () => {
    const files = [
      'src/main/kotlin/service/UserService.kt',
    ];

    // spring-boot maxDiffLinesPerPr = 800
    const result = analyzeScope(files, springBootProfile, 1000);

    expect(result.severity).not.toBe('ok');
  });

  it('3개 이상 그룹이면 강력 경고한다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/service/OrderService.kt',
      'src/main/kotlin/config/SecurityConfig.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 400);

    expect(result.severity).toBe('warn');
    expect(result.groups.length).toBeGreaterThanOrEqual(3);
  });

  it('정상 범위에서는 severity가 ok이다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 100);

    expect(result.severity).toBe('ok');
  });

  it('분할 제안에 머지 순서가 포함된다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/controller/UserController.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/service/OrderService.kt',
      'src/main/kotlin/controller/OrderController.kt',
      'src/main/kotlin/config/SecurityConfig.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 400);

    expect(result.splitSuggestion).toBeDefined();
    if (result.splitSuggestion) {
      for (const pr of result.splitSuggestion.proposedPrs) {
        expect(pr.order).toBeGreaterThan(0);
        expect(pr.files.length).toBeGreaterThan(0);
        expect(pr.description).toBeTruthy();
      }
      // 순서가 정렬되어 있는지 확인
      const orders = result.splitSuggestion.proposedPrs.map((pr) => pr.order);
      expect(orders).toEqual([...orders].sort((a, b) => a - b));
    }
  });

  it('빈 파일 목록이면 ok를 반환한다', () => {
    const result = analyzeScope([], springBootProfile);

    expect(result.severity).toBe('ok');
    expect(result.totalFiles).toBe(0);
    expect(result.groups).toEqual([]);
  });

  // ─── maxCohesionGroups 임계치 검증 ───

  it('maxCohesionGroups 초과 시 warn이다', () => {
    // spring-boot maxCohesionGroups = 2, 3개 도메인 → 3 그룹
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/entity/Product.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 100);

    expect(result.severity).toBe('warn');
    expect(result.groups.length).toBeGreaterThan(2);
  });

  it('maxCohesionGroups 이내이면 ok이다', () => {
    // spring-boot maxCohesionGroups = 2, 2개 도메인 → 2 그룹
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/service/OrderService.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 100);

    // 2개 그룹이지만 mixedConcerns 없으므로 ok
    expect(result.severity).toBe('ok');
  });

  // ─── exception 역할 처리 ───

  it('exception 파일은 domain-crud 그룹에 포함된다 (spring-boot)', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/service/UserService.kt',
      'src/main/kotlin/exception/UserException.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 100);

    expect(result.severity).toBe('ok');
    // exception 파일이 domain-crud에 포함되어야 함
    const domainGroup = result.groups.find((g) => g.groupName === 'domain-crud');
    expect(domainGroup).toBeDefined();
    expect(domainGroup!.files.some((f) => f.role === 'exception')).toBe(true);
  });

  // ─── config 그룹핑 ───

  it('여러 config 파일이 하나의 config-change 그룹으로 묶인다 (spring-boot)', () => {
    const files = [
      'src/main/kotlin/config/SecurityConfig.kt',
      'src/main/kotlin/config/JwtConfig.kt',
      'src/main/kotlin/config/CorsConfig.kt',
    ];

    const result = analyzeScope(files, springBootProfile, 50);

    // 모든 config가 하나의 그룹으로 묶여야 함
    const configGroups = result.groups.filter((g) => g.groupName === 'config-change');
    expect(configGroups.length).toBe(1);
    expect(configGroups[0]!.files.length).toBe(3);
  });

  // ─── error 레벨 ───

  it('4개 이상 그룹 + diff 라인 초과 시 error이다', () => {
    const files = [
      'src/main/kotlin/entity/User.kt',
      'src/main/kotlin/entity/Order.kt',
      'src/main/kotlin/entity/Product.kt',
      'src/main/kotlin/entity/Payment.kt',
    ];

    // spring-boot: maxCohesionGroups=2, 2*2=4 그룹 이상 + diff 초과
    const result = analyzeScope(files, springBootProfile, 1000);

    expect(result.severity).toBe('error');
  });
});

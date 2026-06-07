# 모노레포 통합 + 공통 규약 + Khala→Nexus 개명 — 설계 문서 (하위 프로젝트 B)

- 작성일: 2026-06-07
- 상태: 설계 승인 → spec 리뷰
- 범위: 상위 비전("5개 도구를 하나의 생태계로")의 분해 중 **B**. A(정체성+docs)는 완료·머지.

---

## 0. 맥락

상위 분해(2026-06-07): A(정체성+docs, **완료**) → **B(모노레포+규약+개명)** → C(통합 설치) → D(Khala 버스 배선). B/C/D는 각자 spec→plan→구현 사이클.

A에서 확정된 정체성: **Khala = 생태계**, **Nexus = 지식베이스 본체(구 khala 컴포넌트)**. A docs는 Nexus를 진실원천으로 쓰되 "개명 진행 중" 콜아웃을 달아둠 → **B가 코드를 docs에 맞춘다.**

**탐색으로 드러난 사실(2026-06-07):**
- 리모트: `khala`·`probe`·`specledger` = GitHub 보유 / `khala-docs`·`mutqa` = 로컬.
- `khala`는 현재 **`spec/domain-invariant-governance` 브랜치(Archon, master 미머지, 42 tests green)**.
- 개명 blast radius: probe에 "khala" 참조 ~240(공개 CLI `probe khala:search/impact/status`, env `KHALA_BASE_URL`, `src/khala/` 클라이언트 9파일), specledger 53(`KhalaSink`/`KhalaHttpSink`/config), khala 자체(패키지 `khala/`·pyproject `name`·CLI `khala`). MCP 도구는 `archon_*`(개명 무관).
- 코드의 모든 "khala"는 **지식베이스 의미** → 코드 repo에선 blanket khala→nexus 안전. 생태계 의미 "Khala"는 **A의 docs에만** 존재(의도적, 유지).
- 라이선스: probe=MIT, khala=LICENSE 보유(내용 확인 필요), specledger·mutqa·docs=없음.

---

## 1. 목표 / 비목표

### 목표
- 5개 repo를 **이력 보존하며 단일 모노레포로 통합**.
- **Khala→Nexus 전체 코드 개명**(공개 API breaking 포함, 감수).
- **공통 규약** 수립: 정체·네이밍·로고·라이선스 / 버전 정책 / 공유 lint·format·editorconfig / 루트 메타 태스크·CI.

### 비목표
- 도구 **기능** 변경/추가(이동·개명·규약만).
- C(통합 설치)·D(버스 배선). C·D의 "배포단위 vs 내러티브단위" 가치 재검증은 B 범위 밖(구조만 준비).

---

## 2. 확정 결정

| 항목 | 결정 |
|---|---|
| 실행 순서 | **1안: Archon 머지 → 이력보존 통합 → 모노레포 내 원자적 개명 → 규약 → push.** 개명을 단일 repo에서 해 교차참조(probe→nexus, specledger sink) 일관성·동시 테스트 보장. |
| 통합 방식 | **이력 보존 병합**(`git filter-repo`, 각 repo→서브디렉토리, 전체 커밋 이력 보존). |
| 모노레포 이름/리모트 | 새 GitHub repo **`khala`**(생태계). 옛 `khala`(컴포넌트) repo는 **`nexus-legacy` 등으로 rename + archive**(read-only, 롤백 안전). probe·specledger 옛 리모트도 archive. (GitHub 작업 = owner=사용자) |
| 라이선스 | **루트 MIT 통일**(specledger·mutqa·docs에 추가; khala 기존 LICENSE 내용 확인 후 정렬). |
| 버전 정책 | **도구별 독립 semver** + 하위별 CHANGELOG. 모노레포 lockstep 없음. |
| 모노레포 툴 | 폴리글랏 **평면 디렉토리 모노레포** — 각 하위 자기 툴체인 유지(Nx/Turbo 같은 JS중심 빌드툴 미도입). |

---

## 3. 타깃 레이아웃

```
khala/                  # 모노레포 루트 = 생태계
  README.md             # 생태계 소개 + 도구 맵 + 링크
  LICENSE               # MIT
  .editorconfig
  CONVENTIONS.md        # 네이밍·버전·기여 관례
  Taskfile.yml          # 루트 메타(각 하위 빌드·테스트 위임)
  .github/workflows/ci.yml  # 하위별 테스트 실행
  assets/logo.svg       # A의 공용 SVG 로고
  nexus/                # 구 khala 컴포넌트(개명)
  probe/
  specledger/
  mutqa/
  docs/                 # 구 khala-docs 사이트
```
- 물리 구축: 소스 원본 보존을 위해 **새 디렉토리에 클론 기반으로 구축**(filter-repo는 파괴적).
- 각 하위는 기존 빌드/테스트 그대로(nexus: pytest·docker, probe: pnpm/vitest, specledger: pytest, mutqa: pytest, docs: astro build+linkcheck).

---

## 4. 실행 단계 (플랜의 청크 경계)

### P0 — 준비
- `khala` repo에서 **Archon 브랜치(`spec/domain-invariant-governance`) → master 머지**, 42 tests green 확인. (Archon은 생태계의 한 도구 → 통합에 포착돼야 함.)
- 5개 repo를 **작업 클론**으로 복제(원본 불변).

### P1 — 이력 보존 통합
- 각 클론에 `git filter-repo --to-subdirectory-filter <name>` 적용(khala→nexus, probe, specledger, mutqa, khala-docs→docs).
- 새 `khala` 모노레포에 각 클론을 머지(`git remote add` + `git merge --allow-unrelated-histories`, 또는 filter-repo 권장 워크플로).
- **검증:** 각 하위 기존 테스트가 새 위치에서 통과. `git log --follow`로 샘플 파일 이력 보존 확인.

### P2 — Khala→Nexus 개명 (모노레포 내 원자적, sense-aware)
- **코드 repo**(nexus/probe/specledger/mutqa): `khala`(=지식베이스) 전부 `nexus`로.
  - nexus: 패키지 `khala/`→`nexus/`, pyproject `name`·`[project.scripts]` `khala`→`nexus`(`nexus.cli:app`), 내부 import·문자열. MCP `archon_*` 유지.
  - probe: `src/khala/`→`src/nexus/`, CLI `khala:search/impact/status`→`nexus:*`, env `KHALA_BASE_URL`→`NEXUS_BASE_URL`, config `khala.baseUrl`→`nexus.baseUrl`, UI 문자열("칼라 서버/지식베이스"→"Nexus").
  - specledger: `KhalaSink`/`KhalaHttpSink`→`NexusSink`/`NexusHttpSink`, config `khala`→`nexus`, `publish.py`.
- **docs**(생태계 의미 보존): 생태계 "Khala"는 **유지**, Nexus 페이지의 "개명 진행 중" 콜아웃 제거, 설치 경로 `khala`→`nexus` 갱신, Archon 페이지의 repo 경로 갱신.
- **breaking 변경**(probe CLI·env, specledger config) → 각 도구 CHANGELOG에 기재.
- **검증:** 전 하위 테스트 green. `grep -ri khala`로 잔여가 **docs의 생태계-의미만** 남는지 확인(코드엔 0).

### P3 — 공통 규약
- 루트 **README**(생태계 맵+도구 링크), **LICENSE**(MIT; specledger·mutqa·docs 추가, khala 기존 정렬), **.editorconfig**, **CONVENTIONS.md**(네이밍·독립 semver·기여 흐름).
- **공유 lint/format**: 루트 ruff 설정(Python 하위 공유), 루트 eslint+prettier(probe/docs 공유) — 각 하위 extends, 기존 통과 유지.
- **버전 정책**: 하위별 `CHANGELOG.md`(개명 breaking 기재).
- **루트 메타**: `Taskfile.yml`(또는 Makefile) — 각 하위 build/test 위임. **CI**: `.github/workflows/ci.yml` — 하위별 테스트(push 시 활성, owner=사용자 영역). *YAGNI 주의: CI는 push 전엔 비활성 — 설정만 둔다.*

### P4 — 발행 (owner=사용자)
- 새 GitHub `khala` 모노레포 remote push.
- 옛 `khala`→`nexus-legacy` rename + archive, probe·specledger remote archive(read-only).
- docs Cloudflare Pages를 새 모노레포 경로로 재연결.

---

## 5. 검증 전략
1. **하위별 테스트**(통합 후·개명 후 2회): nexus pytest / probe vitest / specledger pytest / mutqa pytest / docs `npm run build`+`linkcheck`.
2. **이력 보존**: `git log --follow` 샘플 파일.
3. **개명 완전성**: 코드에 `khala` 잔여 0, docs는 생태계-의미만.
4. **breaking 기재**: probe·specledger CHANGELOG.

---

## 6. 위험 / 롤백
- `git filter-repo`는 파괴적 → **원본 repo 불변, 클론에서만 작업**.
- 옛 remote는 **삭제 아닌 archive**(롤백 경로 유지).
- 개명 sense 혼동 → 코드는 blanket 안전(전부 지식베이스 의미), docs만 수작업 sense-aware.
- Archon 머지 회귀 → P0에서 42 tests green 확인 게이트.
- Windows 환경: `git filter-repo` 설치 필요(`pip install git-filter-repo`). nexus 통합테스트는 Docker/Postgres 의존(owner=사용자 검증 가능).

---

## 7. 미해결 / 후속
- khala 기존 LICENSE 내용(MIT 여부) — P3에서 확인 후 정렬.
- GitHub repo 생성·rename·archive·Cloudflare 재연결 = **owner=사용자**(인증 필요).
- C·D 착수 여부 및 "배포단위 vs 내러티브단위" 가치 재검증 — B 완료 후 별도.
- 모노레포 물리 경로(Labs 내 위치) — 구현 시 확정(새 디렉토리).

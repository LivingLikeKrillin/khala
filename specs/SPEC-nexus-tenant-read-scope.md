---
id: SPEC-nexus-tenant-read-scope
type: spec
title: 'One token, more than one corpus to read — the mechanism only'
status: draft
linked_adrs:
- ADR-0002
- ADR-0006
- ADR-0008
tags:
- nexus
- auth
- governance
---
# One token, more than one corpus to read — the mechanism only

## 0. 무엇을 여는가 — 그리고 무엇을 안 여는가

**읽기 범위 목록이라는 기제만 넣는다.** U1 이 끝나도 **원소가 둘 이상인 목록은 기동이 거부된다**
(§3.1). 기제는 단위 검사로만 증명하고, 실제로 두 코퍼스를 여는 것은 컷오버 SPEC 이다.

⛔ **범위 밖 (`SPEC-nexus-design-corpus-cutover`)**: 사본 제거 · 목록 부착 · 그 둘의 원자성 ·
교차 테넌트 중복 억제 · 조각별 clearance · 로그 스키마 · 사본 참조 고아 처리.

## 0.1 Backstop (ADR-0008)

```yaml
backstop:
- row: adr-0008-retrieval-stack
  reread: 2026-08-31 — 새 검색 채널·인덱스 백엔드·토크나이저/임베딩·커넥터 없음.
    U1 이 바꾸는 것은 `auth/scope.py` 한 함수와 그 값을 받는 **검색 읽기 경로의 tenant 술어
    12곳**(§1.2)이며, 원소 둘 이상은 기동이 막으므로 모든 술어가 원소 하나짜리 배열을 받는다.
  clause: none
  ruling: pending-director
```

⛔ **이 판정이 채워지기 전에는 구현하지 않는다** (§5 P-1). 초판은 내가 `does-not-fire` 를 직접
적었고 그것이 자기 승인이었다(1R I-013). 2판은 `pending` 으로 두었으나 **그것을 막는 조건이
없었다**(3R I-007) — 이제 완료 조건의 선행 행으로 박는다.

## 1. 실측 (재현 명령 포함)

### 1.1 사본 — **상한이다, 측정값이 아니다**

```sql
SELECT CASE
  WHEN d.source_uri LIKE '%ext-notion%' THEN 'notion'
  WHEN EXISTS (SELECT 1 FROM documents e WHERE e.tenant='design_docs' AND e.title=d.title)
       THEN 'design-copy' ELSE 'other' END AS kind,
  count(DISTINCT d.rid), count(c.rid)
FROM documents d LEFT JOIN chunks c ON c.doc_rid = d.rid
WHERE d.tenant='default' GROUP BY 1;
--  design-copy 122문서 1,582청크 · notion 112/340 · other 14/267
```

⚠ **두 번 틀렸다.** 초판의 `1,849` 는 `NOT LIKE '%ext-notion%'` 로 세어 자기 문서·ops-map 까지
포함한 상한이었다(2R I-006). **`1,582` 도 상한이다**(3R I-011) — 제목이 같다고 사본이 아니고,
이름이 바뀐 사본은 빠지며, 이 질의는 `status='active'` 를 안 건다. **사본을 식별하는 술어는
컷오버 SPEC 이 정한다.** 여기서는 규모의 자릿수로만 쓴다.

### 1.2 바꿔야 할 술어 — 세어서 적는다

```bash
grep -rn "AND tenant" --include=*.py nexus/nexus/ | grep -v test | wc -l          # 32 (전체)
grep -rn "tenant" --include=*.py nexus/nexus/search/ | grep -E "= \$|ANY" | grep -v test   # 12
```

⚠ **초판의 `130곳` 은 틀렸다** — 패턴 셋(`WHERE`·`AND tenant`·`tenant =`)을 합쳐 센 값이다.
실제는 **전체 32곳**, 그중 **검색 읽기 경로 12곳**(`hybrid.py` 2 · `corpus_scope.py` 3 ·
`anchor_status.py` 2 · `pairs.py` 1 · `doc_debt.py` 1 · `query_retention.py` 3).

⛔ **초판이 "U1 이 바꾸는 곳은 둘" 이라고 쓴 것도 틀렸다**(3R I-004). 목록을 반환하는 함수 하나가
바뀌면 그 값을 받는 **12곳이 전부** 바뀌어야 한다 — 하나라도 스칼라로 남으면 조용히
`tenants[0]` 으로 강제되거나 타입에서 깨진다.

### 1.3 왜 (동기 — 컷오버 SPEC 이 닫는다)

생애주기 미추종(A24, 소유자 요구사항) · 짝 확장이 사본에서 **아예 안 돎**(A23) · 같은 사실 두 벌.

⛔ **컷오버 순서**: 서명된 설계 라벨 셋(C-2·D-1·D-2)의 근거 문서가 **전부 사본에 있다**(실측).
사본을 먼저 내리면 그 라벨은 근거를 잃고, 목록을 먼저 붙이면 정본·사본이 함께 오는 창이 생긴다
(ADR-0006 엔트로피 1위). **둘은 한 단위여야 하고 원자적이어야 한다.**

⚠ 그리고 **교차 테넌트 supersession 은 오늘의 프리미티브로 표현이 불가능하다**(3R I-008):
`supersede(old_rid, new_rid, tenant)` 는 두 문서가 같은 테넌트에 있어야 하고, 컨테인먼트 필터도
문서별 `status` 다. **컷오버 SPEC 은 ADR-0006 개정이나 새 교차 테넌트 식별자를 필요로 한다** —
있는 것으로 되는 일이 아니다.

## 2. 지금 규칙과 무엇이 바뀌는가 (3R I-009)

오늘 `effective_scope` 는 요청의 tenant 를 **무시**한다. ⛔ **이 SPEC 은 그 성질을 없앤다.**
초판은 *"없애지 않는다"* 고 썼는데 거짓이었다 — §3.2 가 요청 tenant 를 **좁히는 데 쓰기**
때문이다. 남는 보장은 더 약한 것 하나다:

> **요청은 좁힐 수만 있고 넓힐 수 없다.**

격리 논증은 그 위에서 다시 세운다: 범위의 상한은 **설정**이 정하고 요청은 그 안에서만 움직인다.
⚠ 부작용 하나를 적어 둔다 — 오늘 임의의/낡은 `tenant` 값을 보내도 무해하던 호출부는, 목록이
생기는 순간 **결과가 조용히 좁아진다.**

## 3. 제안 (U1 만)

### 3.1 설정과 부팅 검사

```yaml
principals:
  - name: "example"
    tenant: "default"
    read_tenants: ["default"]     # 선택. 없으면 [tenant]. U1 에서는 원소 1개만 허용
```

기동 거부 조건:

| # | 조건 | 왜 |
|---|---|---|
| B-1 | `tenant ∉ read_tenants` | 설정이 범위를 넓히는 것을 막는다 (1R I-001) |
| B-2 | 빈 원소 · 중복 원소 | 오설정 (2R I-015) |
| B-3 | **`len(read_tenants) > 1`** | ⛔ **U1 의 안전장치다** (3R I-002). 조각별 clearance 없이 두 코퍼스를 열면 한 테넌트 어휘의 `INTERNAL` 이 다른 테넌트 기준으로 해석된다. 컷오버 SPEC 이 그 불변식을 갖추면 이 검사를 뗀다 |

⚠ **실재 테넌트인지 검사하지 않는다**(3R I-003 수용). 기동을 DB **내용**에 의존시키면 비어 있는
신규 테넌트나 재적재 중 재시작이 서비스를 죽인다. 오타는 §3.2 의 기록으로 잡는다.

### 3.2 요청 계약

요청은 지금처럼 **단일 `tenant` 하나**를 보낸다. 목록을 받는 API 는 만들지 않는다.

| 요청 | 결과 범위 | 응답 |
|---|---|---|
| 안 준다 | `read_tenants` 전체 | 해소된 범위를 함께 낸다 |
| 목록 안에 있다 | 그 하나로 좁힌다 | 해소된 범위를 함께 낸다 |
| 목록 밖이다 | 기본 `tenant` 하나 | **해소된 범위를 함께 낸다** + 서버측 기록 |

⛔ **응답이 해소된 범위를 들고 나간다** (3R I-010). 그게 없으면 호출자는 코퍼스 X 를 물어
코퍼스 Y 로 답을 받고 **아무 신호도 못 받는다** — 에이전트 소비자에겐 오류보다 나쁘다.
서버측 기록은 운영자를 돕지 호출자를 돕지 않는다.

**기록의 자리** (3R I-006): 새 표를 만들지 않는다. **애플리케이션 로그 한 줄 + 계수기**이고
필드는 `principal · requested · resolved` 다. 요청값은 호출자 입력이므로 **원문을 저장하지
않는다** — 목록 밖이라는 사실과 이름만 남긴다. `search_log`·`a2a_audit` 스키마는 안 건드린다.

### 3.3 U1 이 바꾸는 곳

`effective_scope` 반환형 + §1.2 의 **검색 읽기 경로 12곳**. 그 밖(쓰기·수명주기·수집·관리
표면·claims·otel)은 **스칼라 그대로** 두고, 목록에서 값을 뽑아 쓰지 않는다.

## 4. 불변식

| # | 불변식 | 왜 |
|---|---|---|
| I-1 | 요청은 좁힐 수만 있다 | §2 의 남은 보장 |
| I-2 | 목록 밖 요청은 오류가 아니다 | 존재 누출 금지 |
| I-3 | 목록 미설정 principal 의 **결과 집합 동일** | 회귀 없음 |
| I-4 | 목록 미설정 principal 의 **상위 k 순서 동일** | 순서 변화도 회귀다 (2R I-016) |
| I-5 | **쓰기는 `principal.tenant` 로 해소된다 — 목록 원소로 절대 아니다** | 목록이 생기면 `tenants[0]` 로 리팩터하는 것이 자연스럽고, 그게 잘못된 테넌트에 적재한다 (3R I-001) |
| I-6 | 부팅 검사 B-1~B-3 를 어기면 기동 거부 | §3.1 |
| I-7 | 범위 밖 요청이 서버측에 기록되고 **응답에 해소된 범위가 실린다** | 조용한 대체 금지 |

## 5. 완료 조건

| # | 무엇 |
|---|---|
| **P-1** | ⛔ **선행**: §0.1 의 backstop `ruling` 이 director 서명으로 채워졌다. 비면 구현하지 않는다 |
| C-1 | 목록 미설정 principal 의 결과 집합·상위 k 순서가 교체 전후 동일. **타이브레이크를 `ORDER BY score DESC, chunk_rid` 로 고정**하고, 기준선은 라벨 18개 질의로 CI 에서 뜬다 (3R I-005) |
| C-2 | 부팅 검사 B-1·B-2·B-3 가 각각 거부한다 |
| C-3 | 목록 밖 tenant 요청이 오류 없이 응답하고, 응답에 해소된 범위가 있고, 로그 한 줄이 남는다 |
| C-4 | **`effective_scope` 단위 검사**로 원소 둘 목록의 해소를 확인한다 — 설정으로는 못 만든다(B-3). 초판은 합성 principal 을 띄우자고 했는데 그것이 바로 §0 이 안 만든다고 한 상태다 (3R I-013) |
| C-5 | 원소 하나 배열의 **질의 계획이 스칼라 때와 같거나** p95 가 기준선 안이다 (3R I-012) |

## 6. 열어 둔 것

- **컷오버** — `SPEC-nexus-design-corpus-cutover`. ADR-0006 개정 또는 교차 테넌트 식별자가 선행
- **테넌트별 등급 어휘** — 전역 enum → 정수 순서 + 테넌트별 이름표. B-3 를 떼는 조건
- **랭킹의 테넌트 인식** — 컷오버 후 근거 점유율 분포를 보고

---
id: SPEC-nexus-embedding-provenance-grain
type: spec
title: 'The generation label is on the wrong grain: one row, two vectors, one lie'
status: approved
date: '2026-08-14T13:00:00Z'
linked_adrs:
- ADR-0008
- ADR-0009
tags:
- nexus
- index
- embedding
- integrity
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-14T13:30:28Z'
content_hash: sha256:528fc438cb7c6ee3ed5ec684643286d712bbeb3263064e1a21f0ea7cf2fce7fe
---
# The generation label is on the wrong grain: one row, two vectors, one lie

## Backstop record

```yaml
backstop:
- row: adr-0008-retrieval-stack
  reread: performed 2026-08-14 — ADR-0008 §5 and its resume-condition table were read.
    §5 의 목록("a new retrieval channel, a second index backend, a tokenizer or
    embedding-model change, or connector work")은 **예시**이고 조항 본문은 "any work that
    would materially expand Nexus's retrieval stack" 이다. 이 작업은 임베딩 **컬럼을 만지되
    모델을 바꾸지 않는다** — 라벨의 알갱이를 고친다. material 인지는 판단이다.
  clause: none-claimed
  ruling: does-not-fire
  declared_by: LivingLikeKrillin
  declared_at: '2026-08-14'
  reason: >-
    §5 가 지키려는 것은 검색 스택을 실질적으로 넓히는 일이다 — 새 검색 채널, 두 번째 인덱스
    백엔드, 토크나이저·임베딩 모델 교체, 커넥터 확장. 이 작업은 그중 어느 것도 아니다.
    벡터도 모델도 검색 경로도 그대로이고, "어느 벡터를 무엇이 만들었나" 를 정확히 적을
    뿐이다. 표 하나와 쓰기 경로 둘이 느는 것은 스택의 확장이 아니라 기존 스택에 대한
    기록이다. 오히려 §5 가 재독을 요구하는 상황(모델 교체·컷오버)에서 판단 근거를 준다.
    판정은 세션에서 디렉터가 내렸고 이 필드가 그것을 보고한다 — 그 이상을 증명하지 않는다.
```

**ADR-0009 승계 — 이 SPEC 이 걸린 방아쇠 둘.**

1. *"The next SPEC that links ADR-0008"* — 감지기가 이제 실제로 감지한다
   (`tests/test_backstop_record.py`, 2026-08-14). 여섯 건이 기록 없이 지나간 뒤 만든 것이고,
   그 여섯은 `specs/backstop-debt.yaml` 에 세어져 있다.
2. *"A rollback guard for the post-flip NULL gap — before any rollback, or **the next SPEC
   touching the embedding columns**"* — **이 SPEC 이 그것이다.** §8 에서 다룬다.

⚠ 감지기의 한계를 여기 적어 둔다: 그 검사는 **필드의 존재**를 보지 서명의 진위를 보지 않는다.
위 `(서명 대기)` 도 형식 검사는 통과한다. 서명을 강제하는 것은 arbiter 의 승인 단계다.

**순서 제약**: `ruling` 이 비어 있는 동안 **U1~U3 의 코드는 쓰지 않는다** (2026-08-14 채워짐). ADR-0009 §3(ii) 가
게이트-이후-SPEC 을 일회성 예외로 기록하며 *"Nothing currently prevents recurrence"* 라고
적었는데, 이 SPEC 이 그 재발의 첫 기회다. 여기서 순서를 문장으로 박아 둔다 — 강제는 arbiter
게이트가 한다.

## 1. 무엇이 관측됐나

### 1.1 라벨 하나가 벡터 둘을 설명하려 한다

`chunks.embed_model` 은 **행당 하나**다. 그런데 벡터는 **컬럼 둘**(`embedding` 768 ·
`embedding_1024`)에 산다. 쓰기 경로가 그 둘을 구별하지 않는다:

```sql
-- nexus/index/embed.py:94, 그리고 reembed.py:174 도 같은 모양
UPDATE chunks SET {col} = $1::vector, embed_model = $2, updated_at = now() WHERE rid = $3
```

`{col}` 은 실행마다 다른데 `embed_model` 은 **같은 한 칸**이다. 즉 라벨은
**마지막에 쓴 컬럼의 것**이고, 다른 컬럼에 대해서는 거짓이다.

### 1.2 실측 (2026-08-14, 개발 DB) — **정책 필터를 걸고**

```sql
SELECT embed_model, count(*) AS 행, count(embedding) AS v768, count(embedding_1024) AS v1024
  FROM chunks
 WHERE tenant='default' AND status='active' AND is_quarantined=false
 GROUP BY embed_model;
```
```
KURE-v1           198행 · v768 148 · v1024 198
nomic-embed-text  111행 · v768 111 · v1024 111   ← 전부 1024 를 갖고 있다
```

`nomic-embed-text` 는 **768차원**이다. 그 라벨을 단 111행이 1024 벡터를 갖고 있다 — 그 벡터를
만든 것은 nomic 이 **아니다**(만들 수 없다). 검색이 읽는 모집단 309행 중 **111행의 1024 벡터가
잘못 라벨돼 있다.**

⚠ **첫 판은 필터 없이 셌고, 그것이 비평을 오도했다.** 필터 없는 수(403행 / 1024벡터 346)를
근거로 비평이 *"57행이 선언 세대의 벡터를 못 가져 벡터 다리에 안 보인다"* 는 결함을 지적했다.
다시 재니 **309/309, 구멍 0** 이다 — 그 57행은 애초에 검색이 안 읽는 행(inactive·격리)이었다.
비평의 추론은 옳았고 **내가 준 숫자가 틀렸다.** 정책 필터 없는 카운트를 근거로 쓰지 말 것
(`base_filter` 는 모든 조회에 붙는다는 것이 이 리포의 규칙이다).

⚠ **"768 재임베딩이 나중에 돌면서 덮었다" 는 추론이지 기록이 아니다.** 컬럼별 쓰기 시각이
없어서 순서를 알 수 없고, 그것이 바로 §3.1 이 추가하려는 것이다. §2·§3.3 이 "그 행들의 출처는
모른다" 고 말하는 것과 앞뒤를 맞춘다 — **모른다.**

### 1.3 그래서 혼합세대 경고가 거짓이다

`fetch_embed_generations(column)` 은 `{col} IS NOT NULL` 로 거르고 **행 라벨로 group by** 한다
(`nexus/index/embed_health.py`). `embedding_1024` 를 물으면 `{KURE-v1: 230, nomic: 116}` 이
나오고 `mixed=True` 가 된다 — **그 컬럼은 아마 균일한데도.**

`SPEC-nexus-index-completeness` §8 이 이것을 "지금 거짓" 이라 적고 **지우지 않은 채** 남겼다.
지우지 않은 판단은 옳았다(경고를 지우면 진짜 드리프트도 같이 안 보인다). 고칠 차례다.

### 1.4 웨이버도 같은 병이다

```sql
CREATE TABLE embed_waivers (chunk_rid TEXT PRIMARY KEY, model TEXT NOT NULL, ...)
```

웨이버는 *"이 청크를 **이 모델로** 임베딩하는 것을 포기한다"* 는 서명인데, PK 가 `chunk_rid`
하나라 **청크당 한 줄**이다. 모델을 바꾼 뒤 같은 청크를 다시 포기할 수 없고, nomic 으로 포기한
청크가 KURE 에서도 포기된 것처럼 보인다. `model` 칸은 있지만 **키가 아니라서 아무것도 막지
못한다.**

### 1.5 올바른 알갱이는 **이미 리포에 있다**

```
index_generation_events(tenant, column_name, model, declared_at, declared_by, reason)

default        | embedding_1024 | KURE-v1
ko_eval_packa  | embedding_1024 | KURE-v1
```

`SPEC-nexus-generation-of-record` 가 만든 이 표는 **(테넌트, 컬럼) → 모델** 을 append-only 로
선언한다. 알갱이가 맞다. 다만 그것은 *"무엇이 있어야 하는가"* 이지 *"각 행에 실제로 무엇이
들어 있는가"* 가 아니다 — 그래서 이 SPEC 이 필요하다.

## 2. 비목표

- **임베딩 모델을 바꾸지 않는다.** 라벨의 알갱이만 고친다.
- **혼합세대 경고를 끄지 않는다.** 거짓 경보를 지우는 가장 쉬운 방법은 감지기를 끄는 것이고,
  그러면 진짜 드리프트도 같이 안 보인다.
- **기존 라벨을 소급 추정하지 않는다** (§3.3). 116행이 어느 모델로 만들어졌는지 **모른다** —
  그럴듯한 추론은 있지만 기록이 아니다.
- **검색 경로를 바꾸지 않는다.**

## 3. 설계

### 3.1 벡터 출처는 컬럼별로 적는다

`chunks` 에 컬럼별 출처를 둔다. 두 후보:

| | 무엇 | 얻는 것 | 잃는 것 |
|---|---|---|---|
| **A. 컬럼마다 라벨** | `embed_model_768` · `embed_model_1024` | 조회가 단순, 마이그레이션 짧음 | 컬럼이 늘 때마다 스키마가 는다 |
| **B. 정규화 표** | `chunk_vector_provenance(chunk_rid, column_name, model, written_at)` | 컬럼 수에 안 묶임, `written_at` 이 공짜 | 조인 하나, 쓰기 경로가 두 곳 |

**권고: B — 근거는 하나뿐이다.** `SPEC-nexus-generation-of-record` 가 이미 "컬럼은 왔다 간다"
를 전제로 서 있고(선언 표의 키가 `column_name` 이다), A 는 세 번째 컬럼이 생기는 날 같은
개정을 다시 부른다.

⚠ 초안은 여기에 *"B 만이 `written_at` 을 준다 — 그것이 §3.2 를 가능하게 한다"* 를 결정적
근거로 적었다. **양쪽 다 거짓이다**: A 도 `embed_model_768_at` 을 가질 수 있고, §3.2 의 새
정의는 `written_at` 을 **쓰지 않는다**(컬럼별 distinct model 과 선언 대조만 쓴다). 권고는
컬럼 증식 이유로 유지하되, 없는 근거를 세워 두지 않는다.

### 3.2 "혼합" 의 정의를 고친다

지금: *한 컬럼에 대해 행 라벨이 둘 이상* → 거짓 경보의 원천.

바꿈: **한 컬럼에 대해 `chunk_vector_provenance.model` 이 둘 이상**. 그리고 **선언과의 불일치**를
따로 센다 — `index_generation_events` 의 최신 선언과 다른 모델로 쓰인 벡터가 몇 개인가.
후자가 실제로 위험한 신호다(선언된 세대가 아닌 벡터가 검색에 섞여 있다).

### 3.3 옛 행은 **모른다고 적는다**

마이그레이션은 기존 `embed_model` 을 **한 컬럼으로만** 옮길 수 없다 — 그 값이 어느 컬럼의
것인지 알 방법이 없기 때문이다. 그래서:

- **`model = NULL`(=미상) 로 채운다.** 추정해서 채우면 §1.2 의 거짓말을 새 표에 복사하는 것이다.
- 미상 행 수는 `nexus status` 에 **보인다**. 숨기면 "모른다" 와 "괜찮다" 가 같아 보인다.
- 미상은 **혼합 판정에 넣지 않는다** — 모르는 것을 위반으로 세면 경보가 다시 상시화된다.
- 재임베딩이 그 행을 다시 쓰면 그때 실제 모델이 기록되고 미상이 줄어든다. **다만 그것을
  일으키는 것이 이 SPEC 에 없다** — 초안은 "저절로 낫는다" 고 썼는데, 다시 임베딩되지 않는
  청크는 **영원히 미상**이다. §7 이 인정한 맹점이 일시적이 아니라 무기한이라는 뜻이다.
  전량 재임베딩을 여기 넣지 않는 이유는 비용이고(코퍼스 전체 + KURE CPU 분당 9청크 실측),
  그러므로 **미상 비율에 상한을 두지 않는다는 것을 결정으로 적는다** — 대신 그 수를 항상
  보이게 두고(§3.3), 상한이 필요하다고 판단되면 그때 재본 수로 정한다.

### 3.4 웨이버 키를 고친다

`embed_waivers` PK 를 `(chunk_rid, model)` 로. 기존 행은 자기 `model` 값을 그대로 쓰므로
**소급 추정이 없다** — §3.3 과 달리 여기는 이미 모델이 기록돼 있다.

**그러나 증상은 읽기 쪽에 산다.** PK 만 바꾸면 nomic 시절 웨이버가 KURE 아래에서도 여전히
면제로 잡힌다 — 커버리지·면제 판정이 **활성 모델로 거르지 않기** 때문이다. 그래서 U3 는
스키마와 **읽기 경로를 같이** 고친다: 면제 조회는 `(chunk_rid, 선언된 모델)` 로 찾는다.
I5 는 "두 행이 공존한다" 는 스키마 성질이라 이 행동을 덮지 못하므로 §4 에 I7 을 세운다.

## 4. 불변식

- **I1 — 한 컬럼의 출처는 그 컬럼만 말한다.** 검사: 768 을 쓰고 1024 를 쓴 뒤, 두 출처 행이
  각각 자기 모델을 갖는다(하나가 다른 하나를 덮지 않는다).
- **I2 — 쓰기 경로가 출처를 남긴다.** `embed.py` 와 `reembed.py` **둘 다**. 검사: 각 경로를
  실행하고 출처 행이 생기는지 본다 — 한쪽만 고치면 재임베딩이 조용히 미상을 만든다.
- **I3 — 미상은 위반이 아니다.** 검사: `model IS NULL` 만 있는 컬럼은 `mixed=False`.
- **I4 — 소급 추정 없음.** 검사: 마이그레이션 후 미상 행 수 == 마이그레이션 전 행 수.
- **I5 — 웨이버는 모델별이다.** 검사: 같은 청크를 두 모델로 포기하면 행이 둘이다.
- **I6 — 검색 무변경.** `hybrid_search` 가 받는 인자 값이 같다. ⚠ 인자 동일성은 U1 이 청크마다
  더하는 쓰기의 **지연**이나 적재 중 출처 쓰기 실패를 덮지 못한다 — 그 둘은 §7 에 한계로 적는다.
- **I7 — 면제는 활성 모델에 대해서만.** 검사: nomic 으로 포기한 청크가 KURE 선언 아래에서
  **면제로 잡히지 않는다.** I5(행이 둘 생긴다)는 스키마 성질이고, 증상은 읽기 쪽에 있었다.
- **I8 — 커버리지 모집단이 변하지 않는다.** U3 는 면제 집합을 양방향으로 바꿀 수 있다.
  검사: 마이그레이션 전후로 `nexus status` 의 테넌트별 커버리지 수와 **종료코드**가 같다.

## 5. 어떻게 고쳐진 것을 아는가

**대조군이 있어야 한다.** 지금 `default` 는 거짓 혼합을 낸다 — 그것이 음성 대조군이다.

| 팔 | 준비 | 기대 |
|---|---|---|
| **거짓 경보(현재)** | `default` 의 `embedding_1024`, 옛 정의 | `mixed=True` (거짓) |
| **양성 대조군** | 한 컬럼에 서로 다른 모델로 벡터 둘을 **실제로** 쓴다 | `mixed=True` — 진짜 드리프트는 여전히 잡힌다 |
| **음성 대조군** | 한 컬럼에 같은 모델로만 쓴다 | `mixed=False` |
| **기록 정확성** | 768 을 A 로, 1024 를 B 로 쓴 뒤 **두 출처 행을 각각 읽는다** | `(768→A, 1024→B)` — 값까지 맞아야 한다 |

⚠ 초안의 판정 팔은 *"마이그레이션 후 `default` 가 `mixed=False`"* 였다. **공허하다** — 백필이
전부 미상이므로 그 결과는 I3(미상은 안 센다) 하나에서 따라 나오고, **컬럼별 기록이 완전히
틀려도 통과한다.** 그래서 위 넷째 팔이 필요하다: 실제로 쓴 값이 그 컬럼의 출처로 읽히는가.
그것이 이 SPEC 이 주장하는 것이고, 미상 통계는 그 주장을 검사하지 못한다.

## 6. 유닛

| 유닛 | 내용 | 위험 |
|---|---|---|
| U1 | `chunk_vector_provenance` + 쓰기 경로 둘(`embed`·`reembed`) + 미상 채우기 마이그레이션 | 중 — 쓰기 경로를 만진다 |
| U2 | 혼합 정의 교체 + `nexus status` 의 미상·불일치 노출 | 낮음 — 읽기 |
| U3 | `embed_waivers` PK → `(chunk_rid, model)` | 낮음 — 소급 추정 없음 |

## 7. 한계

- **116행이 어느 모델로 만들어졌는지는 영영 모른다.** 재임베딩해야 알게 되고, 그때는 새로
  만든 것이지 알아낸 것이 아니다.
- **미상이 많으면 혼합 감지의 감도가 낮다.** 미상을 세지 않기로 했으므로, 코퍼스가 전부
  미상이면 이 감지기는 아무것도 못 잡는다. 그래서 미상 수를 **보이는 곳에 둔다**(§3.3).
- **`written_at` 은 쓰기 시각이지 모델 배포 시각이 아니다.**
- **적재가 청크마다 쓰기를 하나 더 한다.** 지연과 실패 모드가 는다. 출처 쓰기가 실패하면
  벡터는 있고 출처는 없는 상태가 되는데, 그것은 미상과 구별되지 않는다 — U1 이 그 둘을
  가르려면 실패를 세야 한다.

## 8. 미해결

- **ADR-0009 승계 (2)**: *post-flip NULL gap 의 롤백 가드.* 이 SPEC 이 그 방아쇠였고
  **닫지 않는다.** 그런데 방아쇠를 쓰고 그냥 열어 두면 항목이 다시 **감지 불가 상태**로
  돌아간다 — ADR-0009 가 트리거를 사건에 건 이유가 바로 그것이다.
  **재고정한다**: 이 항목의 새 방아쇠는 **`backstop-debt.yaml` 과 같은 그물**이다 — 임베딩
  컬럼을 만지는 SPEC 은 이 항목을 명시적으로 처분(닫거나 다시 미룸)해야 하고, 그 강제는
  `tests/test_backstop_record.py` 를 넓히는 별도 유닛 몫이다(U4, 이 SPEC 범위 밖).
  **소유자는 그대로 디렉터다.** 이 문단이 그 재고정의 기록이다.
- **`chunks.embed_model` 을 언제 지우는가.** 출처 표가 서면 그 칸은 중복이고 **거짓인 채로
  질의 가능하게** 남는다. 지금 읽는 곳은 `nexus/index/embed_health.py`(혼합 판정) 하나이고
  쓰는 곳은 `embed.py`·`reembed.py` 둘이다(2026-08-14 전수). U2 가 읽기를 옮기면 남는 것은
  쓰기뿐이므로, 그 시점에 **컬럼에 "거짓" 을 명시하는 COMMENT 를 달거나** 별도 마이그레이션으로
  지운다. 어느 쪽인지 이 SPEC 은 정하지 않는다.
- **`model` 대신 `generation_id` 를 쓸 것인가.** 같은 이름의 모델이 재학습되면 이름만으로는
  못 가른다. 지금 그 사례가 없어 이름으로 둔다.

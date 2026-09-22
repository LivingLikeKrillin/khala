# 빈 것과 터진 것이 같은 값으로 나오는 자리 — 감사 (2026-09-22)

*계기: 설명 층이 자기 대장에서 같은 부류의 결함 셋을 찾아 보냈다. 그중 셋째가 이 모양이다 —
**빈 대장에 거짓을 돌려준다.** 그 처방을 이쪽에 걸어 봤다.*

---

## 0. 한 줄 — 후보 16, 결함 **셋**, 모범 **셋**. 셋 다 같은 모양이었다

이 리포에 있던 것은 *"빈 대장 → 거짓"* 이 아니라 **한 칸 옆**이다.

> **터진 것이 「채울 것이 없었다」와 같은 값으로 나온다.**

세 보강 패스가 전부 그랬다. 정책은 맞다 — 보강이 죽었다고 검색 결과까지 버리면 있던 답도
못 준다. 틀린 것은 그 뒤다: **그 다음부터 두 경우가 응답에도, 단계 기록에도, 부른 쪽에도
같은 값**이었다.

---

## 1. 무엇을 셌나

두 모양을 기계로 뽑았다.

```
빈 결과 → 확정 값을 돌려주는 자리        9
되읽기형 함수 (-> bool)                   7   (하나 겹침 ⇒ 15)
+ 읽다가 찾은 것                          1   ⇒ 16
이미 「측정 안 함 = None」 규약을 쓰는 자리 26
```

⛔ **셋째 결함(`corrections_for`)은 두 목록 어디에도 없었다.** `return` 이 아니라
`continue` 로 삼켜서 grep 에 안 걸렸다. **읽어서 찾았다** — 설명 층의 셋도 전부 그랬다.
⇒ **이 부류는 기계로 전수하지 못한다.** 기계가 하는 일은 읽을 목록을 유계로 만드는 것까지다.

---

## 2. 판정 — 16 자리

| 자리 | 빈 것 → 무엇 | 판정 |
|---|---|---|
| `cli.py:1507` 세대 이력 | "선언 없음" | ✅ 참 — 대장이 곧 선언이다 |
| `cli.py:1642` 보존 현황 | "보존 중인 테넌트 없음(기본값 명시)" | ✅ 참 |
| `cli.py:1005` `_do` | 명령 성공 여부 | ✅ |
| `db.py:92` `check_connection` | 예외 → False | ✅ 참 — 연결이 안 된 것이 맞다 |
| `feedback/store.py:175` `set_reason` | 가드에 걸림 → False | ✅ 값은 참(안 적었다). ⚠ **거절 사유 셋이 한 값으로 뭉친다** — 별건 |
| `index/bm25.py:309` `index_chunk_bm25` | 토큰 0 · 예외 → 둘 다 False | ✅ 값은 참(색인 안 됐다). ⚠ 이유가 뭉친다 — 부른 쪽이 수만 센다 |
| `index/reembed.py:244` `index_exists` | 카탈로그 0행 → False | ✅ 참 — 진짜 없다 |
| `ingest/pipeline.py:501·531` | 대상 0 → 0 | ✅ 참 |
| `sources/roots_store.py:60` `remove_root` | 0행 → False | ✅ 참 |
| `llm/budget.py:92` `measured_averages` | **None** | ⭐ **모범** — *"0 으로 채우지 않는다"* |
| `search/span_store.py:209` `explain_query` | **None** + `candidates_purged_at` | ⭐ **모범** — *"후보가 없었다"* 와 *"지웠다"* 를 가른다 |
| `search/span_store.py:72` `persist_spans` | 성공 True · 삼킨 실패 False | ⭐ **모범** — *"반환값이 곧 결과다"* |
| `search/hybrid.py` `_fill_sections` | 터짐 · 없음 → **둘 다 `[]`** | ⛔ **결함** |
| `search/pairs.py` `paired_chunks` | 터짐 · 없음 → **둘 다 `[]`** | ⛔ **결함** |
| `search/reconcile.py` `corrections_for` | 이름마다 터짐 → `continue` | ⛔ **결함** (grep 밖) |

---

## 3. ⭐ 이 리포는 같은 구분을 **이미 하고 있었다**

그래서 결함이 셋뿐이다. 같은 파일 안에 정답이 있었다.

- `_vector_leg` 머리말: *"**빈 결과와 죽은 경로를 구분해서** 돌려준다"* — 3-튜플을 돌려준다
- `add_section_fill(fired=…)` 주석: *"「이 단계는 켜져 있었는데 후보가 0 이었다」와 「이
  단계가 아예 꺼져 있었다」는 다른 사실이고, `fired` 가 그 둘을 가른다"*
- `nexus/CLAUDE.md`: *"Embedding 실패: 삼키지 말고 `record_refusal()` 로 거부를 행으로
  남긴다. 삼키면 그 청크는 벡터 경로에서 영구히 사라지고 아무도 모른다"*

⛔ **`section_fill` 단계는 셋 중 둘만 갈라 놓고 있었다.**

```
fired=False              아예 꺼져 있었다
fired=True  failed=False 켜졌고 채울 것이 없었다
fired=True  failed=True  켜졌고 터졌다      ← 이것만 빠져 있었다
```

세 경우 모두 후보 수가 0 이다. 그래서 `failed` 가 없으면 기록에서 셋째가 둘째로 읽힌다.

---

## 4. 고침

- `SearchResult.enrichment_failed: list[str]` — 터진 보강 패스의 이름
- ⛔ **`degraded` 에 안 넣는다.** 그 칸의 어휘는 `LEGS` 가 정본이고 **경로**만 담는다.
  보강은 순위 뒤에 붙는 덧붙임이라 죽어도 순위가 그대로다 — 다른 사실이면 다른 칸이다
- `_fill_sections` 가 `(절, 터졌는가)` 를 돌려준다 (`_vector_leg` 와 같은 모양)
- `corrections_for` · `paired_chunks` 는 `failed=` 목록에 자기 이름을 적는다.
  ⭐ **그 목록은 `result.enrichment_failed` 이고 `packet_for_answer` 가 넘긴다** —
  제외 목록을 인자로 안 받는 것과 같은 이유다(표면마다 받으면 하나가 잊는다)
- `section_fill` 단계 기록에 `detail.failed`
- 답변 표면 셋에 `enrichment_failed` 를 실어 보낸다

검사는 `tests/test_a_failed_enrichment_is_not_an_empty_one.py`. **셋을 일부러 깨뜨려**
각각 붉어지는 것을 확인했다.

---

## 5. ⛔ 이 감사가 못 하는 것

- **전수가 아니다.** 셋째가 grep 밖이었다는 것이 그 증거다. 센 것은 **두 모양**이고,
  삼키는 방법은 그 둘 말고도 있다(`continue` · 기본 인자 · `.get(default)` · 빈 `dict`)
- **「이 값을 읽고 행동하는 소비자가 있는가」를 자리마다 확인하지 않았다.** 고친 셋은 근거
  꾸러미로 흘러가므로 답변이 달라진다 — 거기까지가 확인한 범위다
- ⚠ **뭉친 것 둘을 남겨 뒀다**(`set_reason` 의 거절 사유 셋 · `index_chunk_bm25` 의 실패
  이유 둘). 값 자체는 참이라 이 부류가 아니고, 고치려면 부른 쪽이 그 구별을 **쓸 데가**
  있어야 한다. 지금은 없다

# Notion 소스 어댑터 (Khala 적재) — 설계 문서

> 작성일: 2026-06-06
> 상태: Draft
> 위치: Khala 확장 — 도메인 불변식·값 거버넌스(#17)의 **입력(적재) 절반**

---

## 0. 한 줄 요약

이미 Notion에 작성된 기획문서를 **증분 동기화**로 Khala에 적재해, 기획자가 개념·정의·정책을 자연어로 조회(grounding)할 수 있게 한다. **소스-무관 `DocumentSource` Protocol**로 짜서 Notion 먼저, Confluence는 같은 인터페이스로 잇는다.

---

## 1. 왜 / 무엇

- 값 조회 코어(#17 MVP)는 *코드 상수* 질문만 답한다. 그러나 기획자 질문 다수는 **Notion에 적힌 개념·정의·정책**에 관한 것 → 그 문서가 Khala에 있어야 grounding 답변 가능.
- 실제 사용·팀 트라이얼의 **필수 전제**: "Notion → Khala" 적재 파이프라인 + 편의 도구.
- Khala 로드맵의 "비개발자 문서 입력(향후 과제)" 빈칸을 메움.

## 2. 범위

| | 내용 |
|---|---|
| **이번** | `DocumentSource` Protocol + **NotionSource**(텍스트 우선 + 이미지 갭 표기) + 증분 폴링 + `khala notion-sync` → 기존 `run_ingest`. sync-lag 신선도 표기. |
| **근접 후속** | 이미지 **비전 강화**(이미지→Claude 비전→텍스트, confidence=medium). ConfluenceSource(같은 Protocol). |
| **미래(범위 밖)** | 문서→claim 추출 전처리(스펙 §9) → 그 위 **모순·모호 탐지**. |

## 3. 핵심 원칙 (계승)

1. **System decides, LLM narrates** — 변환/분류는 코드. (이미지 비전 강화는 후속이며 LLM-보조 티어로 confidence 표기.)
2. **캘리브레이션** — 못 살린 이미지는 "미캡처 N개" 정직 표기. Notion 스냅샷이므로 "마지막 동기화 N시간 전" 표기(sync-lag).
3. **복사 말고 가리킴** — 원문은 Notion(SoT), Khala는 인덱스. Notion URL을 인용으로 보존.
4. **소스-무관** — Confluence가 온다는 걸 알므로 Protocol 추상화 정당.

---

## 4. 아키텍처

```
DocumentSource (Protocol)
  .list_changed(since) -> [PageRef{id, url, last_edited}]
  .fetch(page_ref)     -> SourceDoc{id, title, url, last_edited, blocks}
  .to_markdown(doc)    -> ConvertedDoc{markdown, frontmatter, image_count}
     ├─ NotionSource     (notion-client SDK, last_edited_time 폴링)
     └─ ConfluenceSource (후속 — REST/storage-format, webhook 가능)
        │
        ▼ 공통 적재
  staging/<source>/<page_id>.md  (frontmatter 포함)
        ▼
  run_ingest(staging)  ← 기존 Khala 파이프라인 재사용
```

### 4.1 적재 흐름 (순서도)

```
[1] (사용자) Notion integration 생성 → NOTION_TOKEN; 기획 페이지/DB를 공유
[2] khala notion-sync
     │ NotionSource.list_changed(since=마지막동기화)  # last_edited_time 필터
[3]  │ 각 페이지 blocks.children.list (재귀·페이지네이션)
[4]  │ to_markdown: 블록→MD + frontmatter, 이미지 카운트
[5]  │ staging/notion/<page_id>.md 작성  (파일명=page_id → rid 안정)
[6]  ▼ run_ingest(staging)  # PII·분류·청킹·인덱싱·엔티티 (content_hash 증분)
[7] Khala DB
```

## 5. 변환 (블록 → Markdown)

- **충실 변환:** heading/paragraph/list/quote/callout/code/table/divider → Markdown.
- **이미지(이번 범위 한계):** `![](url)` 플레이스홀더만. **변환 시 `image_count`를 세어 frontmatter·답변에 "미캡처 이미지 N개" 표기**(캘리브레이션). 의미 복원은 후속 비전 강화.
- **best-effort:** embed/synced block/복잡 DB 뷰는 텍스트 위주로, 손실 가능 — 로그.

## 6. Frontmatter & 메타 매핑 (실제 파이프라인 제약 반영)

확인된 제약: `_save_document`는 `source_uri=canonical_uri`, `source_kind='git'`, `owner='indexer'`를 **하드코딩**. collector의 증분 dedup은 `source_uri = canonical_uri`로 조회 → **source_uri를 Notion URL로 바꾸면 dedup이 깨짐.**

→ 설계:
- **`source_uri` = canonical_uri 유지**(dedup 보존). 스테이징 파일명 = **Notion page_id** → `canonical_uri = {tenant}:notion/<page_id>.md` 안정 → `doc_rid` 안정.
- **Notion URL·last_edited는 chunk `metadata`(JSONB)에 저장** → 인용·sync신선도. (documents엔 metadata 컬럼 없음 → 청크에 보존.)
- frontmatter 키: `title`, `doc_type`(★ classifier 경로판정 무력화 보완 — 아래), `origin_url`(Notion URL), `origin_last_edited`, `source_kind: wiki`, `owner`, `classification`(config의 `notion.classification` 주입).
- **파이프라인 수정 = "값 오버라이드"가 아니라 *INSERT 컬럼 구조 변경*** (리뷰 교정). 기존 git 적재 불변(frontmatter 없으면 현행 기본값) 보장 + 회귀테스트 필수:
  - `_save_document`: `source_kind`/`owner` 하드코딩 리터럴(`'git'`/`'indexer'`) → 파라미터화(frontmatter 우선, 없으면 기존값). **ON CONFLICT DO UPDATE에도 `source_kind`/`owner` 추가**(재동기화 시 값 갱신 반영). `$`번호 시프트 주의.
  - `_save_chunks`: 현행 INSERT에 **`metadata` 컬럼·플레이스홀더가 없음** → `metadata` 컬럼 신규 추가 + `{origin_url, origin_last_edited, image_count}` 주입, `source_kind`/`owner` 파라미터화. (`chunks.metadata JSONB DEFAULT '{}'` 컬럼은 존재.)
- **classifier 경로판정 보완:** 스테이징 파일명=page_id → `relative_path=notion/<page_id>.md`라 classifier의 경로 기반 `doc_type` 키워드 매칭이 무의미. classifier는 **frontmatter `doc_type`을 최우선**으로 쓰므로, NotionSource가 frontmatter에 `doc_type`을 채워 해결.
- `source_kind='wiki'`는 Khala enum에 이미 존재 → enum 변경 불필요.

## 7. 증분 동기화 & 갱신

- **증분 풀:** `list_changed(since)` = Notion `last_edited_time > since`인 페이지만.
- **증분 인덱싱:** Khala `content_hash` 비교로 변경분만 재인덱싱(이중 증분).
- **실행:** `khala notion-sync`를 cron(매시/매일) 또는 수동. **"매번 수동" 아님.**
- **삭제/보관:** `live_ids()`는 roots를 **전체 열거**(증분 아님)해야 하므로 비용이 큼 → 매 동기화가 아니라 **`--full` 또는 별도 주기에서만** 수행. 현재 살아있는 page_id 집합 vs 인덱싱 집합 비교 → 사라진 문서 `status='soft_deleted'`. (collector dedup이 `status='active'`만 보므로, soft_deleted 문서가 Notion에 재등장하면 재인덱싱되는지 회귀 확인.)
- **상태 저장:** 마지막 동기화 시각을 어딘가 보존(config/별도 sync_state 파일 또는 테이블). MVP는 간단한 상태파일.
- **sync-lag 정직 표기:** 코드 값은 조회 시 재읽기(드리프트 0)지만 Notion은 스냅샷 → 답변에 `마지막 동기화: N시간 전`(chunk metadata.origin_last_edited 활용).
- **실시간 webhook:** Notion은 빈약 → MVP 폴링. (Confluence는 webhook 우수 → 후속에서 고려.)

## 8. CLI

```
khala notion-sync [--since auto|<ts>] [--full] [--staging ./staging/notion]
  → NotionSource로 변경분 수집·변환·스테이징 → run_ingest → 동기화 시각 갱신
```
인자 매핑: `--full` → `run_ingest(force=True)` + `live_ids()` 삭제감지 수행. `config.notion.tenant` → `run_ingest(tenant=...)`. `--since auto`는 저장된 마지막 동기화 시각 사용.
설정(config.yaml):
```yaml
notion:
  token_env: NOTION_TOKEN          # 비밀값은 환경변수 (config에 직접 X)
  roots: ["<database_id 또는 page_id>", ...]   # 대상 범위
  tenant: default
  classification: INTERNAL
```

## 9. 보안

- **토큰은 환경변수**(`NOTION_TOKEN`)로만. config/코드/로그에 평문 금지.
- 최소권한: integration에 공유된 페이지만 접근.
- Khala 기존 PII 스캐너·quarantine·classification 그대로 적용(적재 경로 동일).

## 10. 리스크 · 미해결

| 항목 | 대응 |
|---|---|
| 이미지 의미 손실 | MVP 텍스트우선+갭표기. 가치테스트 miss 분석으로 비전 강화 필요성 판단 |
| sync-lag로 인한 stale 답변 | "마지막 동기화" 표기 + cron 주기 단축 |
| 파이프라인 수정이 기존 git 적재 깨뜨림 | frontmatter 없으면 현행 동작 보장 + 회귀테스트 |
| Notion 변환 충실도(표·embed) | best-effort + 손실 로그 |
| 대량 페이지 rate limit | notion-client 페이지네이션 + 백오프 |

## 11. 명시적 범위 밖 (YAGNI)

이미지 비전 강화 · ConfluenceSource(단 Protocol 경계는 이번에 마련) · 문서→claim 추출 · 모순·모호 탐지 · 실시간 webhook · documents 테이블 스키마 확장(MVP는 chunk metadata로 충분).

---

## 부록 — DocumentSource Protocol (초안)

```python
from typing import Protocol
from dataclasses import dataclass

@dataclass
class PageRef:
    id: str; url: str; last_edited: str

@dataclass
class ConvertedDoc:
    page_id: str; markdown: str; frontmatter: dict; image_count: int

class DocumentSource(Protocol):
    def list_changed(self, since: str | None) -> list[PageRef]: ...
    def fetch_markdown(self, ref: PageRef) -> ConvertedDoc: ...
    def live_ids(self) -> set[str]: ...   # 삭제 감지용
```
NotionSource가 이 Protocol을 구현. ConfluenceSource는 후속에서 동일 구현.

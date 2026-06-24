# Design Spec — Notion Importer (S4)

- **Date:** 2026-06-25
- **Status:** Design (사용자 승인 — Path B 확정)
- **Author:** LivingLikeKrillin (with Claude)
- **상위:** [[org-doc-governance-initiative]] S1(PR #47)+S3(PR #48) 위. 사용자 원래 demand("노션 문서 가져오기").

## 1. Purpose / Scope

Notion 페이지를 khala로 가져온다. **Path B(사용자 확정):** Notion → CSF → **S3 타입-인지 intake(in-process 재사용)** → doc_type + provenance + external_spec label + 승격가능(`promote_external`). 검색·근거에 노출(S3).

**범위(짓는 것):** 전체 import(roots 하위 페이지 열거 → 적재). 반제품 `NotionSource` 완성(`live_ids`) + CSF 빌더 + importer 오케스트레이터 + CLI.

**비범위(defer):** 증분 동기화(`list_changed`/since) — 첫 import는 전체로 충분, 증분은 demand-pull 시. auto-classification(타입 추론) — 모든 페이지 기본 **NOTE**(default-memo; 사용자가 특정 문서를 이후 promote). 양방향 sync.

**라이브 caveat:** 실제 import는 `NOTION_TOKEN` + `notion-client` 의존 필요. 구현은 **주입 클라이언트로 단위 테스트까지 완성**하고, 라이브 실행은 사용자 단계(환경에 토큰 없음). `notion-client`는 lazy-import(기존 패턴) + optional 의존.

## 2. 레이어링 — 리팩터 대신 의존성 주입(DI)

외부-ingest 코어(`_default_external_ingest_fn`: CSF body→transient file→`run_ingest`→label+doc_type UPDATE→`ExternalIngestOutcome`)는 `nexus/a2a/server.py`에 산다. importer가 이를 직접 import하면 ingest→a2a 역방향 의존이 생긴다.

**해결(코드 이동 없음):** importer는 `ingest_fn`을 **주입**받는 순수 오케스트레이터로 둔다(a2a/ingest-core를 import하지 않음). 구체 와이어링은 **CLI(합성 루트)**가 한다 — CLI는 최상위 레이어라 `NotionSource`(ingest)와 `_default_external_ingest_fn`(a2a)을 모두 참조해도 무방. 이 의존성 역전이 추출 리팩터를 불필요하게 만든다(더 안전·더 작음). importer는 a2a에 무지하므로 단위 테스트가 가짜 ingest_fn으로 깔끔하다.

## 3. CSF 빌더 — Notion 페이지 → CSF

`NotionSource.fetch_markdown(ref) -> ConvertedDoc(markdown, frontmatter)` 출력을 CSF dict로 매핑(S3가 받는 형식). **순수 함수** — `hashlib.sha256` 직접 사용(a2a 무의존):

```
id:    ext-notion-<page_id>            # 결정적
kind:  NOTE                            # 기본(default-memo); auto-classify defer
title: ConvertedDoc.frontmatter["title"]
body:  ConvertedDoc.markdown
provenance:
  source_tool: notion
  source_id:   <page_id>
  source_url:  ConvertedDoc.frontmatter["origin_url"]
  source_hash: sha256(body)
```

importer가 CSF를 **신뢰 가능하게 직접 구성**하므로(id/hash 정합이 구성으로 보장됨) 서버측 `validate_external_spec`(신뢰 불가 외부 호출자 방어)는 importer 경로엔 불필요. build_csf는 그 불변식(id 형식, hash=sha256(body))을 자체적으로 만족시킨다.

## 4. NotionSource 열거 — `live_ids`

`roots`(config의 page/database id 목록) 하위에 도달 가능한 **페이지 id 집합**을 반환. 주입 클라이언트로:
- 각 root: `client.pages.retrieve` 또는 `blocks.children.list`로 객체 타입 분기.
- page → 포함 + 자식 `child_page` 재귀(`blocks.children.list`, 기존 `_all_blocks` 페이지네이션 재사용).
- database → `client.databases.query`로 행(page) 열거.

`PageRef`(id/url/last_edited)는 `client.pages.retrieve` 결과로 구성. 단위 테스트는 가짜 client로 페이지 트리/DB를 시뮬레이트.

(증분 `list_changed`는 이 위에 `last_edited > since` 필터로 후속 추가 — S4 비범위.)

## 5. Importer 오케스트레이터

```
async def import_notion(source, tenant, ingest_fn) -> ImportReport
  for page_id in source.live_ids():
      ref  = source.page_ref(page_id)          # id/url/last_edited
      conv = source.fetch_markdown(ref)         # markdown + frontmatter
      csf  = build_csf(conv, page_id)
      try:
          outcome = await ingest_fn(csf, tenant)   # 주입 — 프로덕션은 _default_external_ingest_fn
          report.record(page_id, outcome)
      except Exception as e:
          report.skip(page_id, str(e))          # 1건 실패가 전체 중단 금지(기존 ingest 규칙)
  return report
```

- `ingest_fn` **주입** → 단위 테스트는 가짜 ingest로 오케스트레이션만 검증(DB·a2a 불필요).
- `ImportReport`: 적재/스킵/멱등 카운트 + 페이지별 결과. per-page skip(한 페이지 실패가 나머지를 막지 않음).

## 6. CLI — `nexus ingest-notion`

`nexus/cli.py`에 Typer 명령 추가:
- 옵션: `--tenant`(기본 default), `--roots`(쉼표구분 또는 config), `--token-env`(기본 NOTION_TOKEN).
- `NotionSource`(라이브 client lazy-import) 구성 → `import_notion` 실행 → `ImportReport` 요약 출력.
- 토큰/notion-client 없으면 친절한 에러.

## 7. Units & 경계

| Unit | 책임 | 의존 | 독립 테스트 |
|---|---|---|---|
| `NotionSource.live_ids`/`page_ref` | roots 하위 page id 열거 + PageRef | 주입 client | 가짜 client 페이지트리/DB |
| `build_csf` | ConvertedDoc → CSF dict | hashlib(순수) | id/provenance/hash 정합 |
| `import_notion` | 열거→fetch→csf→ingest 오케스트레이션, per-page skip | 주입 source+ingest_fn | 가짜 source+ingest, skip/멱등 카운트 |
| CLI `ingest-notion`(합성 루트) | NotionSource(live) + `_default_external_ingest_fn` 와이어링 + 요약 | import_notion, NotionSource, a2a.server | (얇음 — smoke) |

## 8. Acceptance

1. `build_csf`: ConvertedDoc → 유효 CSF(id=`ext-notion-<id>`, source_hash==sha256(body), kind=NOTE, provenance 완비). 기존 서버측 `validate_external_spec`를 통과하는 형태(대칭 확인).
2. `NotionSource.live_ids`: 가짜 client로 root page+자식 child_page+DB 행 id 열거.
3. `import_notion`: 가짜 source+ingest_fn으로 N 페이지 적재, ingest 예외 페이지 skip(중단 없음), ImportReport 카운트 정확.
4. CLI `ingest-notion` 등록 + smoke(주입/mock); 토큰/notion-client 없을 때 친절한 에러.
5. 전체 회귀: nexus + 외부-spec E2E 그대로 통과(순수 추가, 기존 경로 불변).

## 9. 향후

증분 sync(`list_changed`/since) · auto-classification(Notion 속성/내용→타입) · 양방향 · 다른 source(Confluence 등, 동일 `ingest_external_csf` 재사용).

# Khala Ecosystem — Roadmap

> 최종 갱신: 2026-06-19

## 비전

팀/서비스 범주에 맞춤화된 근거 기반 지식 시스템을 구축하고,
개발 워크플로 검증 도구와 연동하여 사람은 판단에만 집중하게 한다.

### 핵심 관점

**전체 조직이 하나의 RAG를 공유하는 것은 비효율적이다.**
팀마다 문서 구조, 용어, 검색 패턴이 다르다.
단일 팀 또는 동일 범주 서비스로 묶인 조직을 위한 맞춤형 RAG가 정답이다.

이를 위해 Nexus는 tenant 기반 격리 위에 팀별 검색 프로파일을 얹어,
하나의 인스턴스에서 팀마다 다른 검색 경험을 제공하는 방향으로 진화한다.

---

## 에코시스템 구성

| 프로젝트 | 역할 | 기술 |
|---------|------|------|
| **Nexus** | 근거 기반 지식 검색 시스템 (RAG). ⚠ 예전 표기는 `RAG + GraphRAG` 였는데 **문서 엔티티 추출 GraphRAG 는 내리기로 확정**됐고 데이터도 사실상 없다(엔티티 5·엣지 1). 유지 대상은 **OTel 설계-관측 이중 그래프**이고 그것은 다른 것이다 | Python, FastAPI, PostgreSQL, mecab-ko |
| **Observer** | 플랫폼 인식 PR 분석 + API 검증 도구 | TypeScript, Node.js, MCP |

Observer는 Nexus 없이도 100% 동작한다. Nexus가 있으면 조직 맥락이 풍부해진다.

---

## Nexus 로드맵 — 테마 기반 페이즈

### 완료

| 항목 | 상태 |
|------|------|
| Hybrid Search (BM25 + Vector + Graph, RRF) | **Done** |
| 한국어 형태소 분석 (mecab-ko) | **Done** |
| OTel 트레이스 수집 + 설계-관측 Diff | **Done** |
| Default-Deny 보안 (PII 탐지, 격리, classification) | **Done** |
| CRM (Canonical Resource Model) | **Done** |
| FastAPI 11개 엔드포인트 | **Done** |
| Web UI (채팅/그래프/문서/Diff) | **Done** |
| Slack Bot (멘션/DM) | **Done** |
| MCP Server (AI Agent 도구 6개) | **Done** |
| CLI (개발자용) | **Done** |

### Phase 1 — 팀 맞춤형

> 같은 Nexus 인스턴스에서 팀마다 다른 검색 경험을 제공한다.

| 항목 | 설명 |
|------|------|
| **tenant별 검색 프로파일** | BM25/Vector/Graph 가중치를 tenant 설정으로 조정. 인프라팀은 Graph 비중↑, 프론트엔드팀은 BM25 비중↑ |
| **tenant별 문서 풀 격리** | 현재 tenant 필터를 확장하여, 팀별 독립된 문서 컬렉션 + 공유 문서 풀을 구분 |
| **역할별 결과 reranking** | 동일 쿼리에 대해 역할(개발자/QA/PM)에 따라 결과 순서를 다르게 반환 |
| **tenant 설정 관리** | config.yaml 또는 DB 기반으로 tenant별 프로파일을 정의하고 관리 |

### Phase 2 — 검색 지능화

> 모든 쿼리에 동일한 검색 깊이를 적용하는 것은 낭비다.

| 항목 | 설명 |
|------|------|
| **Adaptive 검색 깊이** | 쿼리 복잡도별 검색 경로 분기. simple(BM25 only) / standard(BM25+Vector) / deep(3-way+Graph 2-hop) |
| **router.py 확장** | 기존 규칙 기반 라우터를 확장하여 3단계 검색 깊이를 자동 판정 |
| **비용 최적화** | 단순 용어 조회에 Graph 2-hop을 돌리지 않음. 예상 비용 절감 30-40% |
| **Cross-Encoder Reranking** | Phase 1의 프로파일 기반 reranking에 더해, 의미적 재순위 적용 |

### Phase 3 — 거버넌스

> 팀 맞춤형 + 검색 지능화가 갖춰진 후, 운영 안정성을 확보한다.

| 항목 | 설명 |
|------|------|
| **JWT 인증/인가** | 사용자 인증 + tenant/clearance 자동 매핑 |
| **감사 추적** | 누가 언제 무엇을 검색했는지 기록. 컴플라이언스 대응 |
| **tenant 관리 UI** | 관리자가 tenant 프로파일을 웹에서 설정/변경 |

### 보류 (Phase 3 이후 재평가)

| 항목 | 보류 이유 |
|------|----------|
| **Context Engine 3계층** (Memory + Tool Retrieval) | 방향성은 맞지만, Phase 1-2 완료 후 Agent 사용 패턴을 관찰한 뒤 판단 |
| **Neo4j 전환** | GraphRepository Protocol이 이미 있으므로, pgvector 한계에 부딪힐 때 전환해도 늦지 않음 |
| **도메인 특화 임베딩** | Phase 1 수준(tenant 격리 강화)에서는 단일 multilingual 모델로 충분. 필요 시 EmbeddingService 래퍼로 교체 |

---

## Observer 로드맵 — 버전 기반

### 완료

| 버전 | 내용 |
|------|------|
| **v0.1** | 플랫폼 인식 PR 범위 분석 (Spring Boot, Next.js, React SPA) |
| **v0.2** | API 스펙 린트/diff (10개 룰) + PR 타입별 리뷰 체크리스트 |
| **v0.3** | MCP 서버 (Claude Code 네이티브 연동, 6개 도구) |
| **v0.4** | Nexus 연동 — 맥락 기반 리뷰 + 영향 분석 |

### 예정

| 버전 | 내용 | Nexus 연동 |
|------|------|-----------|
| **v0.5** | UI 확장팩 (토큰 검증 / VRT / 접근성 린트) | — |
| **v0.6** | 팀별 린트 프로파일 — tenant의 검색 프로파일과 연동하여 팀별 리뷰 규칙 적용 | Nexus Phase 1 연동 |

---

## 동향 분석 — 흡수/제외 근거

2026년 RAG 동향을 조사하여, Nexus 방향성과 일치하되 꼭 필요한 컨셉만 흡수한다.

### 흡수

| 동향 | 반영 위치 | 근거 |
|------|----------|------|
| **Vertical/Domain-specific RAG** | Phase 1 | 범용 RAG보다 도메인 맞춤형이 성능 차이가 큼. tenant별 프로파일로 구현 |
| **역할별 검색 프로파일** | Phase 1 | 같은 쿼리에 재무분석가와 법무팀이 다른 결과를 받는 패턴. reranking으로 구현 |
| **Adaptive RAG** | Phase 2 | 쿼리 복잡도별 검색 깊이 동적 조정. 비용 30-40% 절감 벤치마크 |

### 제외

| 동향 | 근거 |
|------|------|
| **Agentic RAG** (LLM in search loop) | "System decides, LLM narrates" 원칙과 충돌. 검색 판정에 LLM을 넣으면 비결정적 + 비용 급증 |
| **PageIndex Tree Search** | 구조화된 장문 문서(금융 보고서, 법률 문서)에 최적화. Nexus는 팀 문서 100-500개 규모에 Hybrid+Graph로 이미 충분 |
| **Self-RAG** (자체 신뢰도 평가) | Nexus는 evidence 필수 + quarantine 원칙이 아키텍처 수준에서 할루시네이션을 방지. 별도 자기평가 계층 불필요 |
| **도메인 특화 임베딩 모델** | Phase 1 수준에서는 단일 multilingual 모델로 충분. EmbeddingService 래퍼가 있으므로 필요 시 교체 가능 |
| **GraphRAG Global/Community Search** (Leiden 커뮤니티 탐지 + community report) | 수백만 문서 코퍼스용 기능. 100-500개 규모에서는 커뮤니티가 너무 작아 무의미하다. 결정적으로 community report는 *LLM이 생성한 비그라운디드 파생 요약*이라 "Nexus는 인덱스지 저장소가 아니다" + "evidence 없는 것은 없는 것" 두 원칙과 정면 충돌. **의식적 배제** |
| **LLM 기반 그래프 추출** (gazetteer 대체) | 질의/색인 파이프라인에 LLM 추출을 넣는 것은 "System decides, LLM narrates" + 결정론 + air-gap 원칙 위반. 현재 규칙 기반 gazetteer 추출을 유지한다. (단 *오프라인* 후보 제안 보조는 demand-pull 게이트 항목으로 별도 관리 — 아래 참조) |

> **Neo4j 전환**도 동향(그래프 DB 기반 GraphRAG)에 해당하나, 위 [보류 표](#보류-phase-3-이후-재평가)에서 이미 다룬다 — `GraphRepository` Protocol이 추상화해 두었으므로 pgvector/CTE 한계에 부딪힐 때 전환해도 늦지 않다.

### GraphRAG 정렬 평가 (2026)

Microsoft GraphRAG가 사실상 표준을 정의한 뒤(LLM 추출 → Leiden 커뮤니티 → 계층 요약 → Local/Global/DRIFT search),
Nexus의 그래프 계층을 그 기준선과 대조한 결과를 **의식적 결정으로** 기록한다.
A2A에서 했던 "검토 후 명시적 배제" 규율을 GraphRAG에도 동일하게 적용하기 위함이다.

**이미 정렬됨 (또는 앞섬)**

| 축 | 상태 | 비고 |
|----|------|------|
| Local search (엔티티 중심 k-hop) | 정렬 | `get_neighbors` 2-hop이 Microsoft local search 패턴과 동형 |
| Hybrid (BM25+Vector+Graph, RRF) | 정렬 | 한국어 형태소까지 포함해 견고 |
| Evidence-bound edge / 추적성 | **앞섬** | 모든 edge가 source chunk에 바인딩. 2026 trust/traceability 흐름(KGRAG-Ex 등)을 아키텍처 수준에서 선취 |
| 설계-관측 이중 그래프 (OTel) | **독자적 우위** | 메인스트림 GraphRAG에 등가물 없음. 런타임 관측을 그래프에 결합 |

**demand-pull 게이트 항목** — *구체적 소비자/통증 신호가 잡힐 때만* 착수한다. 지금은 만들지 않는다.

| 항목 | 게이트 조건 | 원칙 정합 |
|------|------------|----------|
| 그래프 근접도를 RRF 랭킹에 반영 | "현재 랭킹이 관련 청크를 놓친다"는 실제 검색 품질 불만 | 그래프 거리는 결정론적 → 원칙 합치 |
| gazetteer 후보 *오프라인* 제안 도구 | entities.yaml 유지보수가 실제로 아픈 일이 됐을 때 | LLM이 제안(narrate), 사람/시스템이 승인(decide) → 파이프라인 밖이라 합치 |

**무조건 개선 (동향과 무관한 구현 결함)**

- **멀티-엔티티 그래프 탐색** — 현재 `hybrid_search`는 감지된 엔티티가 여럿이어도 `entity_rids[0]` 하나에서만 2-hop을 펼친다. 이미 구축된 그래프를 덜 활용하는 순수 미완성으로, 새 표면·의존성·원칙 충돌이 없다. 감지된 모든 엔티티에서 탐색하고 hops를 route별로 설정 가능하게 한다.

### 참고 자료

- [10 RAG Architectures in 2026](https://www.techment.com/blogs/rag-architectures-enterprise-use-cases-2026/)
- [From RAG to Context (RAGFlow)](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)
- [Enterprise Knowledge Systems 2026-2030 (NStarX)](https://nstarxinc.com/blog/the-next-frontier-of-rag-how-enterprise-knowledge-systems-will-evolve-2026-2030/)
- [Hybrid Tree Search (PageIndex)](https://docs.pageindex.ai/tutorials/tree-search/hybrid)
- [Microsoft GraphRAG — Local/Global search & Leiden communities](https://microsoft.github.io/graphrag/)
- [Global Community Summary Retriever (graphrag.com)](https://graphrag.com/reference/graphrag/global-community-summary-retriever/)

---

## 핵심 원칙

1. **Grounded answers only** — 근거 없는 답변은 제공하지 않는다
2. **System decides, LLM narrates** — 접근 통제/분류/검색 경로는 코드가 결정. LLM은 요약만
3. **팀 맞춤형 > 범용** — 전체 조직이 하나의 설정을 공유하는 것은 비효율적이다
4. **정상일 때는 조용히** — 노이즈는 신뢰를 죽인다 (Observer)
5. **없어도 동작, 있으면 풍부** — Observer는 Nexus 없이도 100% 동작한다

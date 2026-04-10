# Khala Ecosystem — Roadmap

> 최종 갱신: 2026-04-10

## 비전

팀/서비스 범주에 맞춤화된 근거 기반 지식 시스템을 구축하고,
개발 워크플로 검증 도구와 연동하여 사람은 판단에만 집중하게 한다.

### 핵심 관점

**전체 조직이 하나의 RAG를 공유하는 것은 비효율적이다.**
팀마다 문서 구조, 용어, 검색 패턴이 다르다.
단일 팀 또는 동일 범주 서비스로 묶인 조직을 위한 맞춤형 RAG가 정답이다.

이를 위해 Khala는 tenant 기반 격리 위에 팀별 검색 프로파일을 얹어,
하나의 인스턴스에서 팀마다 다른 검색 경험을 제공하는 방향으로 진화한다.

---

## 에코시스템 구성

| 프로젝트 | 역할 | 기술 |
|---------|------|------|
| **Khala** | 근거 기반 지식 검색 시스템 (RAG + GraphRAG) | Python, FastAPI, PostgreSQL, mecab-ko |
| **Probe** | 플랫폼 인식 PR 분석 + API 검증 도구 | TypeScript, Node.js, MCP |

Probe는 Khala 없이도 100% 동작한다. Khala가 있으면 조직 맥락이 풍부해진다.

---

## Khala 로드맵 — 테마 기반 페이즈

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

> 같은 Khala 인스턴스에서 팀마다 다른 검색 경험을 제공한다.

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

## Probe 로드맵 — 버전 기반

### 완료

| 버전 | 내용 |
|------|------|
| **v0.1** | 플랫폼 인식 PR 범위 분석 (Spring Boot, Next.js, React SPA) |
| **v0.2** | API 스펙 린트/diff (10개 룰) + PR 타입별 리뷰 체크리스트 |
| **v0.3** | MCP 서버 (Claude Code 네이티브 연동, 6개 도구) |
| **v0.4** | Khala 연동 — 맥락 기반 리뷰 + 영향 분석 |

### 예정

| 버전 | 내용 | Khala 연동 |
|------|------|-----------|
| **v0.5** | UI 확장팩 (토큰 검증 / VRT / 접근성 린트) | — |
| **v0.6** | 팀별 린트 프로파일 — tenant의 검색 프로파일과 연동하여 팀별 리뷰 규칙 적용 | Khala Phase 1 연동 |

---

## 동향 분석 — 흡수/제외 근거

2026년 RAG 동향을 조사하여, Khala 방향성과 일치하되 꼭 필요한 컨셉만 흡수한다.

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
| **PageIndex Tree Search** | 구조화된 장문 문서(금융 보고서, 법률 문서)에 최적화. Khala는 팀 문서 100-500개 규모에 Hybrid+Graph로 이미 충분 |
| **Self-RAG** (자체 신뢰도 평가) | Khala는 evidence 필수 + quarantine 원칙이 아키텍처 수준에서 할루시네이션을 방지. 별도 자기평가 계층 불필요 |
| **도메인 특화 임베딩 모델** | Phase 1 수준에서는 단일 multilingual 모델로 충분. EmbeddingService 래퍼가 있으므로 필요 시 교체 가능 |

### 참고 자료

- [10 RAG Architectures in 2026](https://www.techment.com/blogs/rag-architectures-enterprise-use-cases-2026/)
- [From RAG to Context (RAGFlow)](https://ragflow.io/blog/rag-review-2025-from-rag-to-context)
- [Enterprise Knowledge Systems 2026-2030 (NStarX)](https://nstarxinc.com/blog/the-next-frontier-of-rag-how-enterprise-knowledge-systems-will-evolve-2026-2030/)
- [Hybrid Tree Search (PageIndex)](https://docs.pageindex.ai/tutorials/tree-search/hybrid)

---

## 핵심 원칙

1. **Grounded answers only** — 근거 없는 답변은 제공하지 않는다
2. **System decides, LLM narrates** — 접근 통제/분류/검색 경로는 코드가 결정. LLM은 요약만
3. **팀 맞춤형 > 범용** — 전체 조직이 하나의 설정을 공유하는 것은 비효율적이다
4. **정상일 때는 조용히** — 노이즈는 신뢰를 죽인다 (Probe)
5. **없어도 동작, 있으면 풍부** — Probe는 Khala 없이도 100% 동작한다

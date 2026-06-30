---
title: Nexus
description: 근거 기반 지식 검색 — 인용 가능한 출처에서만 답하는 RAG + GraphRAG.
---

Nexus는 에코시스템의 근거 기반(grounded) 지식 베이스입니다. 조직 내부 지식(문서·정책·설정)과 운영 사실(OpenTelemetry 트레이스)에 대한 질문에, **인용 가능한 근거가 있을 때만** 답합니다. 모든 답변에는 신뢰도(confidence)와 함께, 그 답을 떠받치는 source chunk 또는 trace로 돌아가는 포인터가 붙습니다.

Nexus가 보정(calibrate)하는 문제는 이렇습니다. 일반적인 RAG는 텍스트를 검색한 뒤 모델이 즉흥적으로 답하게 두므로, 근거가 있든 없든 그럴듯한 답을 만들어 냅니다. Nexus는 이를 뒤집습니다. 무엇을 검색할 수 있고 그 답이 근거로 뒷받침되는지는 시스템(결정론적 코드)이 판정하고, LLM은 이미 존재하는 근거 위에서 서술만 합니다. 인용할 출처가 없으면 답은 만들어지지 않습니다.

한 줄 정체성: **근거 기반 지식 검색을 위한 엔터프라이즈 RAG + GraphRAG** — AI 에이전트(코드 리뷰, 트러블슈팅)가 추측이 아니라 실제 문서와 관측된 텔레메트리에서 추론하도록 받쳐 주는 context provider입니다.

<img
  src="/diagrams/nexus.svg"
  alt="하이브리드 검색: 질의가 BM25(mecab-ko)·벡터(768차원)·그래프(2-hop) 검색기로 갈라지고, 그 결과가 RRF(k=60)로 통합되어 출처를 인용하거나 거부하는 근거 기반 답변이 된다."
  style="max-width: 100%; height: auto; display: block; margin: 1.5rem auto;"
/>

## 핵심 개념

- **하이브리드 검색** — 세 검색기를 병렬 실행하고 RRF(Reciprocal Rank Fusion, `k=60`)로 통합합니다: 한국어 형태소(mecab-ko, 조사·어미 정확 분리) 기반 BM25, 벡터(768차원 임베딩), 그래프(엔티티 2-hop 탐색).
- **근거 기반 엣지** — 근거(evidence) 없이는 어떤 관계(edge)도 존재하지 않습니다.
- **이중 지식 계층 — 설계(Designed) vs 관측(Observed)** — 설계 문서에서 추출한 관계와 실제 트레이스에서 관측된 관계(`CALLS_OBSERVED`: 호출 수·에러율·지연)를 나란히 둡니다.
- **설계-관측 diff** — `doc_only`(문서엔 있으나 관측 안 됨), `observed_only`(관측되나 미문서화), `conflict`(둘 다 있으나 불일치)를 자동 탐지합니다.
- **Default-deny 보안** — PII/시크릿 감지 시 즉시 quarantine, 인덱싱에서 제외하고 검색 결과에 절대 포함하지 않습니다. 모든 쿼리는 분류(`PUBLIC < INTERNAL < RESTRICTED`)로 필터링됩니다.
- **저장소가 아니라 인덱스** — 원본은 Git과 Tempo에 있고, Nexus에는 파생 데이터(chunks·embeddings·graph edges)만 저장됩니다.

## 빠른 시작

Docker Compose 스택으로 돕니다. 기본은 **핵심 컨테이너**(PostgreSQL + Ollama + FastAPI 앱)만 뜨고, OTel 관측 파이프라인은 옵트인입니다. 아래 `task` 한 줄은 내부 `docker compose` 명령을 감쌉니다(원시 명령 병기).

사전 준비: Docker Desktop · (선택) [go-task](https://taskfile.dev) · (선택) LLM 답변용 Anthropic API 키.

```bash
# 1. 클론 & 설정
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
cp nexus/.env.example nexus/.env        # (선택) nexus/.env 에 ANTHROPIC_API_KEY 설정 시 LLM 답변 생성

# 2. 기동 (핵심 컨테이너만)
task up        # 또는: cd nexus && docker compose up -d

# 3. 임베딩 모델 받기 (최초 1회)
task models    # 또는: docker compose exec nexus-ollama ollama pull nomic-embed-text
```

→ `http://localhost:8000` 에서 채팅으로 질문(근거와 함께 답). 문서 적재: `docker compose exec nexus-app nexus ingest ./docs`. 웹 UI 사용법은 **[Nexus 웹 사용 가이드](/ko/tools/nexus-web/)** 참고.

```bash
# 업데이트 / 정지
git pull && task update    # 이미지 재빌드·재기동 + DB 마이그레이션 적용
task down                  # 정지 (또는: docker compose down)
```

OTel 관측(trace 집계)이 필요할 때만 옵트인: `docker compose --profile observability up -d`.

전체 명령어·API 레퍼런스는 영어 페이지([Nexus](/tools/nexus/)) 또는 [소스 저장소 README](https://github.com/LivingLikeKrillin/khala)를 참고하세요.

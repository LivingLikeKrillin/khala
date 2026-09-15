---
title: 시작 가이드
description: 엔지니어링 목표별 도구 매핑 및 빠른 실행 가이드.
---

본 가이드는 해결하고자 하는 엔지니어링 과제에 따른 도구 선택 기준과 Nexus 환경의 빠른 구축 절차를 안내합니다.

## 엔지니어링 과제별 도구 매핑

| 엔지니어링 목표 | 권장 도구 | 핵심 메커니즘 |
|---|---|---|
| 코드베이스 및 도메인 사양에 대한 근거 기반 정합성 질의 | [Nexus](/ko/tools/nexus/) / [Archon](/ko/tools/archon/) | 하이브리드 검색(BM25+Vector) 및 도메인 불변식 상수 검증 |
| PR 영향도 분석 및 장애 트러블슈팅을 조직 텔레메트리에 연계 | [Observer](/ko/tools/observer/) | Nexus 지식 기판 및 분산 추적(OTel) 결합 분석 |
| 아키텍처 의사결정 및 사양 검토의 책임 추적성 확립 | [Arbiter](/ko/tools/arbiter/) | 사양 사전 승인 게이트 및 무결성 해시 원장 관리 |
| 생성된 단위/통합 테스트의 실질적 결함 검출 능력 측정 | [Probe](/ko/tools/probe/) | AST 구문 변이 테스트(Mutation Testing) 하니스 |
| 시스템 복잡도 대비 엔지니어링 조직의 인지 부채 계측 | [Adept](/ko/tools/adept/) | 코퍼스 대비 검증된 이해도(Vouch) 커버리지 측정 |

## 5분 빠른 시작: Nexus 로컬 기동

Docker 환경만 설치되어 있으면 로컬 인프라(Postgres, Ollama, App)가 컨테이너 스택 내에서 자동 구성됩니다.

```bash
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
cp nexus/.env.example nexus/.env     # LLM 답변 생성을 위한 ANTHROPIC_API_KEY 설정 (선택 사항)
task up
```

Taskfile 도구가 없는 경우 `nexus/` 디렉토리에서 다음 명령을 직접 실행합니다:

```bash
cd nexus
docker compose up -d --wait                                  # 컨테이너 기동 및 임베딩 모델 자동 다운로드
docker compose exec -T nexus-app python -m scripts.migrate   # 데이터베이스 스키마 마이그레이션 적용
```

최초 빌드 시 `mecab-ko` 형태소 분석기 컴파일로 인해 약 10~20분이 소요되며, 이후 재실행은 수 초 내에 완료됩니다.

### 지식 코퍼스 색인 (Ingestion)

빈 코퍼스 상태에서는 모든 질의에 대해 기각(Abstention) 응답이 반환되므로, 기본 문서를 색인합니다:

```bash
docker compose exec nexus-app nexus ingest ./docs
```

브라우저에서 `http://localhost:8000/` 접속 후 질의를 수행하면 인용된 청크 식별자 및 근거 패킷과 함께 응답이 제공됩니다.

- 서비스 중지: `task down` (또는 `docker compose down`)
- 서비스 갱신: `git pull` 후 `task update` (재빌드 및 DB 마이그레이션 적용)

## 시스템 사전 요구사항

- 공통: `git`, 최신 Python / Node.js 런타임.
- Nexus: Docker 및 Docker Compose.
- Observer: Node.js ≥ 20.
- Arbiter / Probe / Adept: Python 3.11+ (Probe 실행 시 `cosmic-ray` 필요).

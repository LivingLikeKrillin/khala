# Nexus MCP Server 설정 가이드

> **⚠ 2026-08-26 실측 분석 — MCP 인터페이스 비활성화 상태 보고.** 사양 문서 정의와 달리 런타임 환경 구성 누락으로 인해 실제 인터페이스 연동이 차단되어 있었습니다:
>
> 1. **런타임 컨테이너 의존성 누락**: 런타임 이미지가 `.[dev,notion,a2a,slack]`만 설치하여 `mcp` 엑스트라 패키지가 결속되지 않음. CI 파이프라인에는 설치되어 테스트를 통과했으나 실제 런타임 배포 환경에서 누락됨.
> 2. **호스트-서버 간 API 버전 비호환**: 호스트 환경 `mcp` 패키지(1.26)와 서버 구현체의 2.x API(`mcp.server.MCPServer`) 간 인터페이스 불일치.
> 3. **`.mcp.json` 엔드포인트 미등록**: 레거시 모듈 엔트리만 잔존하고 Nexus 엔드포인트가 비활성화 상태로 유지됨.
>
> 결과적으로 최근 2개월간 에이전트 A2A 트래픽이 차단되어(A2A 감사 2건) 에이전트가 직접 `psql` 및 `grep`을 통해 지식 베이스를 조회하는 우회 경로를 사용했습니다.
>
> **현재 유효한 인터페이스는 CLI 계층입니다**: 루트 `CLAUDE.md` 인터페이스 계약을 준수하며, `tenant` 매개변수를 통해 `default` 및 `design_docs` 멀티 테넌트 코퍼스를 동시에 지원합니다. MCP 연동은 단일 토큰당 단일 테넌트로 범위가 제한됩니다(`auth/principal.py`).
>
> **MCP 인터페이스 정식 활성화 요건**: ① 런타임 이미지 빌드 명세에 `mcp` 종속성 추가 및 재빌드 ② 테넌트별 주체(Principal) 식별자 및 인증 토큰 발급/해시 등록 (`config.yaml`) ③ `.mcp.json` 엔드포인트 등록. 요구조건 충족 전 미가동 서버 등록 시 부팅 단계에서 핸드셰이크 예외가 발생하므로 단계적 활성화가 필수적입니다.


> AI Agent(Claude, Cursor 등)가 MCP 프로토콜로 Nexus에 질의하여 조직 내부 지식과 운영 사실을 컨텍스트로 활용할 수 있다.

---

## 1. 설치

```bash
pip install -e '.[mcp]'
```

---

## 2. 실행

### stdio (로컬 Agent 연동)

```bash
# Nexus API가 먼저 실행 중이어야 함
docker compose up -d

# MCP Server 실행 (stdio)
python -m nexus.mcp
```

### streamable-http (원격 Agent 연동)

```bash
python -m nexus.mcp --transport http --port 8001
```

---

## 3. Claude Desktop 연동

`claude_desktop_config.json`에 추가:

```json
{
  "mcpServers": {
    "nexus": {
      "command": "python",
      "args": ["-m", "nexus.mcp"],
      "env": {
        "NEXUS_API_URL": "http://localhost:8000",
        "NEXUS_MCP_TOKEN": "<bearer token — §6 참고. 없으면 모든 툴이 401>"
      }
    }
  }
}
```

---

## 4. 제공 도구 (Tools)

| 도구 | 설명 | 주요 파라미터 |
|------|------|---------------|
| `nexus_search` | 하이브리드 검색 (BM25 + Vector + Graph) | `query`, `top_k`, `route`, `tenant` |
| `nexus_answer` | 검색 + LLM 근거 기반 답변 | `query`, `top_k`, `tenant` |
| `nexus_graph` | 엔티티 관계 그래프 조회 | `entity`, `hops`, `tenant` |
| `nexus_suggest` | 엔티티 자동완성/검색 | `query`, `tenant`, `limit` |
| `nexus_diff` | 설계-관측 불일치 보고서 | `flag_filter`, `entity_filter`, `tenant` |
| `nexus_status` | 시스템 상태 확인 | (없음) |
| `nexus_supersede` | 문서 supersession 선언 — **파괴적**(대상 문서가 검색에서 사라짐) | `old_ref`, `new_ref`, `tenant` |
| `archon_claim_value` | 개념의 현재 값을 코드 상수에서 조회 | `concept`, `tenant`, `classification_max` |
| `archon_grade_authority` | 등급/열거형 권한 질의 | `grade`, `enum_name`, `subpath` |

---

## 5. 사용 예시

Agent가 MCP를 통해 Nexus에 질의하는 흐름:

```
Agent: "결제 서비스가 발행하는 Kafka 토픽이 뭐야?"
  → nexus_answer(query="결제 서비스가 발행하는 Kafka 토픽")
  → 근거 기반 답변 + 출처 chunk 반환

Agent: "payment-service의 관계를 보여줘"
  → nexus_graph(entity="payment-service", hops=1)
  → 설계/관측 관계 목록 반환

Agent: "문서와 실제 관측이 다른 부분이 있어?"
  → nexus_diff()
  → doc_only, observed_only 불일치 목록 반환
```

---

## 6. 환경 변수

```bash
NEXUS_API_URL=http://localhost:8000  # Nexus API 주소 (Docker 내부: http://nexus-app:8000)

# ⚠️ 필수. Nexus 는 기본이 auth.mode=enforced 라, 토큰 없이는 모든 툴이 401 로 실패한다.
#    발급:  docker compose exec nexus-app nexus auth gen-token
#    등록:  config.yaml 의 auth.principals[].token_sha256 (nexus auth hash-token 으로 해시)
#    로컬 dev 는 docker-compose.override.yml 이 주입하는 NEXUS_DEV_TOKEN 값을 그대로 써도 된다.
NEXUS_MCP_TOKEN=<bearer token>
```

---

## 7. 아키텍처

```
AI Agent → MCP Protocol → nexus.mcp.server
                               │
                          @mcp.tool()
                               │
                          httpx → Nexus API
                               │
                          Nexus 검색/그래프/LLM
```

### 파일 구조

```
nexus/mcp/
├── __init__.py
├── server.py       # FastMCP 도구 정의 + API 호출 래퍼
└── __main__.py     # 진입점 (stdio/http transport 선택)
```

---

## 8. 트러블슈팅

### Agent가 도구를 찾지 못함
- MCP Server가 실행 중인지 확인
- `claude_desktop_config.json`의 경로가 올바른지 확인

### "데이터베이스 연결 실패" 오류
- `docker compose up -d`로 인프라가 실행 중인지 확인
- `NEXUS_API_URL` 환경 변수가 올바른지 확인

### 응답이 느림
- Nexus API (`/status`)에서 Ollama 연결 상태 확인
- `top_k`를 줄여 검색 범위 제한

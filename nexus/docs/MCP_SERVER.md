# Nexus MCP Server 설정 가이드

> **⚠ 2026-08-26 실측 — 이 문은 지금 닫혀 있다.** 이 문서대로 하면 되지만, 아무도 그렇게 해
> 두지 않았다. 세 군데가 동시에 끊겨 있었다:
>
> 1. **런타임 컨테이너에 `mcp` 가 없다.** 이미지가 `.[dev,notion,a2a,slack]` 을 설치하는데
>    `mcp` 는 별도 extra 다. CI 는 설치하므로 테스트는 초록이었고, **돌 자리에만 없었다.**
> 2. **호스트의 `mcp` 는 1.26 이고 이 서버는 2.x API**(`mcp.server.MCPServer`)를 쓴다.
> 3. **`.mcp.json` 에 Nexus 가 없었다.** 등록돼 있던 것은 이름이 바뀌어 사라진 모듈 하나뿐이었고,
>    그것도 로컬에서 꺼져 있었다.
>
> 그래서 에이전트 트래픽이 두 달간 0에 가까웠다(A2A 감사 2건). **문이 있는데 안 쓴 것이 아니라
> 문이 안 붙어 있었다.** 그 사이 에이전트가 조직 지식을 꺼낸 경로는 `psql` 과 `grep` 이었다.
>
> **지금 열려 있는 문은 CLI 다** — 루트 `CLAUDE.md` 의 계약이 그것을 가리킨다. 테넌트를 인자로
> 받으므로 `default` 와 `design_docs` 를 **둘 다** 본다. MCP 는 토큰 하나 = 테넌트 하나라
> 그 자체로 코퍼스가 하나로 좁아진다(`auth/principal.py`).
>
> **MCP 를 실제로 열려면**: ①이미지 설치 목록에 `mcp` 를 넣고 다시 빌드 ②테넌트별 principal 과
> 토큰(토큰은 리포에 넣지 않는다 — `.mcp.json` 은 커밋된다) ③`.mcp.json` 등록. 셋 다 하기 전에는
> 등록하지 않는 편이 낫다 — 뜨지 않는 서버가 등록돼 있으면 매 세션이 오류로 시작한다.


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

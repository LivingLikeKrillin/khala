# Khala MCP Server 설정 가이드

> AI Agent(Claude, Cursor 등)가 MCP 프로토콜로 Khala에 질의하여 조직 내부 지식과 운영 사실을 컨텍스트로 활용할 수 있다.

---

## 1. 설치

```bash
pip install -e '.[mcp]'
```

---

## 2. 실행

### stdio (로컬 Agent 연동)

```bash
# Khala API가 먼저 실행 중이어야 함
docker compose up -d

# MCP Server 실행 (stdio)
python -m khala.mcp
```

### streamable-http (원격 Agent 연동)

```bash
python -m khala.mcp --transport http --port 8001
```

---

## 3. Claude Desktop 연동

`claude_desktop_config.json`에 추가:

```json
{
  "mcpServers": {
    "khala": {
      "command": "python",
      "args": ["-m", "khala.mcp"],
      "env": {
        "KHALA_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

---

## 4. 제공 도구 (Tools)

| 도구 | 설명 | 주요 파라미터 |
|------|------|---------------|
| `khala_search` | 하이브리드 검색 (BM25 + Vector + Graph) | `query`, `top_k`, `route`, `tenant` |
| `khala_answer` | 검색 + LLM 근거 기반 답변 | `query`, `top_k`, `tenant` |
| `khala_graph` | 엔티티 관계 그래프 조회 | `entity`, `hops`, `tenant` |
| `khala_suggest` | 엔티티 자동완성/검색 | `query`, `tenant`, `limit` |
| `khala_diff` | 설계-관측 불일치 보고서 | `flag_filter`, `entity_filter`, `tenant` |
| `khala_status` | 시스템 상태 확인 | (없음) |

---

## 5. 사용 예시

Agent가 MCP를 통해 Khala에 질의하는 흐름:

```
Agent: "결제 서비스가 발행하는 Kafka 토픽이 뭐야?"
  → khala_answer(query="결제 서비스가 발행하는 Kafka 토픽")
  → 근거 기반 답변 + 출처 chunk 반환

Agent: "payment-service의 관계를 보여줘"
  → khala_graph(entity="payment-service", hops=1)
  → 설계/관측 관계 목록 반환

Agent: "문서와 실제 관측이 다른 부분이 있어?"
  → khala_diff()
  → doc_only, observed_only 불일치 목록 반환
```

---

## 6. 환경 변수

```bash
KHALA_API_URL=http://localhost:8000  # Khala API 주소 (Docker 내부: http://khala-app:8000)
```

---

## 7. 아키텍처

```
AI Agent → MCP Protocol → khala.mcp.server
                               │
                          @mcp.tool()
                               │
                          httpx → Khala API
                               │
                          Khala 검색/그래프/LLM
```

### 파일 구조

```
khala/mcp/
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
- `KHALA_API_URL` 환경 변수가 올바른지 확인

### 응답이 느림
- Khala API (`/status`)에서 Ollama 연결 상태 확인
- `top_k`를 줄여 검색 범위 제한

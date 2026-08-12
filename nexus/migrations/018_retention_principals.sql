-- 018_retention_principals: 동의 범위를 **표면**까지 좁힌다.
-- (SPEC-nexus-query-text-retention §3.2 amendment, 2026-08-12)
--
-- 017 은 보존을 테넌트 단위로 켰다. 그런데 고지는 **사람 집단**에게 가고, 테넌트에는 그 집단만
-- 도달하지 않는다: 웹 UI·슬랙 봇·CLI·A2A 가 전부 같은 테넌트로 들어온다. 슬랙 채널 하나에
-- 알리고 테넌트를 켜면, 고지를 못 받은 경로의 질문까지 같은 테이블에 쌓인다.
--
-- 경로(path)로는 가를 수 없다 — 슬랙 봇은 HTTP API 를 부르므로 웹 UI 와 구분되지 않는다.
-- 가를 수 있는 것은 **principal** 이다: 봇은 자기 토큰을 쓰고, API 는 그 principal 로
-- (tenant, clearance) 를 정한다.
--
-- 그래서 허용목록이다. 비어 있으면 **아무것도 보존하지 않는다** — 017 의 "기본은 저장 안 함" 을
-- 표면 축으로 한 번 더 적용한 것이고, 새로 생긴 표면이 조용히 포함되는 일을 막는다.
--
-- principal 은 **판단에만 쓰이고 저장되지 않는다.** 저장하면 텍스트 옆에 신원이 앉고, 017 이
-- 소금 친 키로 막아 둔 사람-로그가 같은 행에서 부활한다.

ALTER TABLE query_retention
    ADD COLUMN IF NOT EXISTS principals text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN query_retention.principals IS
    '이 테넌트에서 **질문이 보존되는 principal 목록**. 비면 아무것도 보존하지 않는다. '
    '판단에만 쓰이고 search_query_text 에는 저장되지 않는다.';

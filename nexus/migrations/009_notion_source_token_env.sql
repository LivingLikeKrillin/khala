-- 루트별 integration 토큰 — 워크스페이스가 하나라는 가정을 푼다.
--
-- Notion 의 integration 은 **워크스페이스에 속하고** 페이지마다 명시적으로 연결돼야 읽힌다.
-- 그래서 다른 조직의 문서를 미러하려면 그쪽 워크스페이스의 integration 토큰이 따로 필요하고,
-- 기존 토큰과 **동시에** 들고 있어야 한다. 지금까지 HTTP 표면은 `NOTION_TOKEN` 하나만 읽었다.
--
-- 위험한 것은 기능 부족이 아니라 **조용한 오독**이다: 토큰을 바꿔치면 이전 워크스페이스의 루트가
-- 빈 걸음으로 보이고, `--reconcile` 이 그 문서들을 사라진 것으로 판정한다. prune 임계가 막아줄
-- 수는 있어도 기댈 것은 못 된다.
--
-- 저장하는 것은 **환경변수 이름**이지 시크릿이 아니다. 시크릿은 배포 env 에만 있고 DB·리포에는
-- 들어가지 않는다 (CLI 의 `--token-env` 와 같은 규약).
--
-- 멱등.

ALTER TABLE notion_sources
    ADD COLUMN IF NOT EXISTS token_env TEXT NOT NULL DEFAULT 'NOTION_TOKEN';

COMMENT ON COLUMN notion_sources.token_env IS
    '이 루트를 읽을 integration 토큰이 담긴 환경변수 이름. 시크릿 자체가 아니다.';

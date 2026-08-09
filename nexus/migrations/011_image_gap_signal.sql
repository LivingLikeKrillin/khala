-- 그림에 갇힌 정책을 재는 **관측 기제**. 기능이 아니라 게이트의 첫 하위 단계다.
--
-- ADR-0002 는 부채 상환 기능을 "관측된 **기록된 비율**이 **설정 임계**를 **롤링 윈도**에서
-- 넘을 때" 로 게이트하고, 게이트ⓐ 에서 그 형식을 이렇게 못박았다:
--
--   "관측 기제 — `search_log` 에 준하는 가벼운 로그 — 자체가 ⓐ 의 첫 하위 단계이며,
--    그것이 존재하고 임계를 넘기 전까지 하류는 아무것도 짓지 않는다."
--
-- 2026-08-09: 파트너 코퍼스에서 정책 5건이 스크린샷 44장을 이고 있고 그림당 본문이 100~171자
-- 뿐임을 셌다. 그림 속 표를 묻는 질의 하나가 "찾을 수 없습니다" 로 끝났다 — **정확한 답이었다.**
-- 그것으로 비전 추출을 짓자는 초안(ADR-0010)을 냈고, 비평이 잡았다: 일화 하나는 ADR-0002 가
-- 요구하는 형식이 아니다. 소유자 처분(2026-08-09) = **게이트를 제대로 세운다.**
--
-- 그래서 이 마이그레이션은 **아무 기능도 켜지 않는다.** 세기만 한다.
--
-- 멱등.

-- ── 문서가 그림을 몇 장 이고 있나 ──────────────────────────────────────────
-- 컨버터는 이미 세고 있었고(`blocks_to_markdown` → image_count) frontmatter 에만 넣었다.
-- 신호가 되려면 검색 시점에 **질의 가능한 자리**에 있어야 한다.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS n_images INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN documents.n_images IS
    '이 문서가 담은 이미지 수. 그림에 갇힌 내용의 크기를 재는 신호원 (ADR-0002 게이트 형식).';

-- ── 그 질의의 근거가 그림 있는 문서에서 왔나 ────────────────────────────────
-- **완벽한 분류기가 아니다.** 사용자가 무엇을 원했는지는 알 수 없고, 알 수 있는 것은
-- "돌려준 근거가 그림 있는 문서에서 왔는데 답을 못 냈다" 뿐이다. 게이트ⓐ 의 선례가 요구한 것도
-- 완벽한 판정이 아니라 **가벼운 로그**다. 이 근사가 무엇을 놓치는지는 v_image_gap_signal 의
-- 주석에 적는다 — 신호를 실제보다 세게 읽지 않기 위해서다.
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS n_image_bearing_docs INTEGER;

COMMENT ON COLUMN search_log.n_image_bearing_docs IS
    '이 질의의 근거 스니펫이 나온 문서 중 n_images > 0 인 것의 수. NULL = 이 컬럼 이전의 행.';

-- ── 롤링 윈도의 비율 ───────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_image_gap_signal AS
WITH windowed AS (
    SELECT date_trunc('day', ts) AS day,
           count(*)                                                        AS searches,
           count(*) FILTER (WHERE no_answer)                               AS no_answer,
           count(*) FILTER (WHERE coalesce(n_image_bearing_docs, 0) > 0)   AS image_backed,
           count(*) FILTER (WHERE no_answer
                              AND coalesce(n_image_bearing_docs, 0) > 0)   AS gap_candidates
    FROM search_log
    WHERE ts >= now() - interval '30 days'
      AND n_image_bearing_docs IS NOT NULL      -- 컬럼 이전 행은 분모에 넣지 않는다
    GROUP BY 1)
SELECT day, searches, no_answer, image_backed, gap_candidates,
       round(gap_candidates::numeric / nullif(searches, 0), 4) AS gap_rate
FROM windowed
ORDER BY day DESC;

COMMENT ON VIEW v_image_gap_signal IS
    '그림에 갇힌 내용 때문에 답을 못 냈을 **후보** 비율 (30일 롤링). '
    '근사다: (1) 사용자의 의도를 모르므로 답이 정말 그림 안에 있었는지는 확인되지 않는다, '
    '(2) 검색이 그 문서를 아예 못 가져온 경우는 안 잡힌다(근거가 없으니 image_backed 가 0), '
    '(3) 컬럼 이전 행은 분모에서 제외된다. 임계는 소유자가 **관측 전에** 정한다 — '
    '숫자를 보고 임계를 정하면 그것은 게이트가 아니다.';

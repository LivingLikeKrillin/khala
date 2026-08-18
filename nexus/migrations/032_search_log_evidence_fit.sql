-- 032: 근거 적합도의 **크기**를 신호로 남긴다 (`search_log.top_distance` · `top_bm25`).
--
-- **왜.** `search/confidence.py` 의 문턱(`FAR_DISTANCE=0.48` · `WEAK_BM25=1.5`)은 **지어낸
-- 질문 17개**에서 나왔다. 진짜 눈금은 실사용 질문에서만 나오는데, 그 질문이 어떤 거리·어떤
-- 키워드 점수로 답해졌는지 지금까지 **아무 데도 안 남았다** — 문턱을 다시 잴 재료가 매 요청마다
-- 버려진 것이다. `top_score` 는 RRF 값이라 순위만 담고 크기를 담지 않으므로 대신 쓸 수 없다
-- (그 사실이 애초에 이 층을 만든 이유다).
--
-- **불리언(`weak`)을 안 남긴다.** 그것은 오늘의 문턱으로 계산된 값이라, 문턱을 옮기는 순간
-- 지나간 행의 뜻이 조용히 바뀐다. 거리와 키워드 점수는 문턱과 무관한 사실이고, `weak` 는
-- 언제든 다시 계산할 수 있다.
--
-- **NULL 의 뜻은 '못 쟀다' 이지 0 이 아니다.** 다리가 안 돌았을 때 0 을 적으면 거리 0 =
-- "완벽히 맞았다", BM25 0 = "전혀 못 맞췄다" 로 **양쪽으로** 거짓말한다.
--
-- `nexus/db.py` 의 멱등 DDL 에도 같은 두 줄이 있다(기존 배포가 기동만으로 적재를 시작하도록).
-- 정의가 갈라지지 않게 함께 고친다.

ALTER TABLE search_log ADD COLUMN IF NOT EXISTS top_distance DOUBLE PRECISION;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS top_bm25     DOUBLE PRECISION;

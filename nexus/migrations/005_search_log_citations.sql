-- SPEC-nexus-search-signal-completeness §4.1 · §4.4
--
-- 검색 신호에 인용 지표를 더한다: n_citations(총) + unverified_citations(미검증). 둘 다 nullable —
-- 답변 없는 검색/구버전 행은 NULL(미측정)이라 '측정된 0건'과 구분된다. 멱등.

ALTER TABLE search_log ADD COLUMN IF NOT EXISTS n_citations          INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS unverified_citations INTEGER;

-- 뷰에 인용 fabrication rate 추가. 컬럼 집합이 바뀌므로 CREATE OR REPLACE 대신 DROP+CREATE.
-- SUM 은 NULL 을 무시하므로 미측정 행은 분자·분모에서 자동 제외된다.
DROP VIEW IF EXISTS v_search_health;
CREATE VIEW v_search_health AS
SELECT path, route,
       count(*)                                                        AS n,
       avg((no_answer)::int)::numeric(4,3)                             AS no_answer_rate,
       avg((graph_requested AND n_graph_edges = 0)::int)::numeric(4,3) AS graph_empty_rate,
       avg((llm_failed)::int)::numeric(4,3)                            AS llm_fail_rate,
       avg(n_snippets)::numeric(6,2)                                   AS avg_snippets,
       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms)        AS p95_latency_ms,
       (SUM(unverified_citations)::numeric
          / NULLIF(SUM(n_citations), 0))::numeric(4,3)                 AS citation_fabrication_rate
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;

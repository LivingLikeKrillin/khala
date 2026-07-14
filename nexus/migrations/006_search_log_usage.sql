-- SPEC-nexus-llm-usage-persistence §3
--
-- 검색 신호에 LLM 토큰/비용을 더한다: prompt_tokens · completion_tokens · cost_usd. 셋 다 nullable —
-- LLM 콜 없는 검색/미가격 모델/구버전 행은 NULL(미측정) 이라 '측정된 0'과 구분된다(NULL ≠ 0).
-- cost_usd 는 모니터링 추정치(billing 아님)라 DOUBLE PRECISION. cost 있으면 토큰도 있다(compute_cost 불변식).
-- 멱등.

ALTER TABLE search_log ADD COLUMN IF NOT EXISTS prompt_tokens     INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS completion_tokens INTEGER;
ALTER TABLE search_log ADD COLUMN IF NOT EXISTS cost_usd          DOUBLE PRECISION;

-- 뷰에 비용 집계 추가(priced 행만 — avg/sum 은 NULL 무시). 컬럼 집합이 바뀌므로 DROP+CREATE.
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
          / NULLIF(SUM(n_citations), 0))::numeric(4,3)                 AS citation_fabrication_rate,
       avg(cost_usd)::numeric(12,6)                                    AS avg_cost_priced_usd,
       sum(cost_usd)::numeric(14,6)                                    AS total_cost_usd
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;

-- SPEC-nexus-graph-scope-filter §4.1
--
-- 그래프 채널이 base_filter 를 우회하던 누출을 막는다: f_graph_neighbors 가 호출자의
-- tenant·clearance 를 받아 양 끝 엔티티에 tenant/classification/quarantine/status 를 강제한다.
-- 멱등 — 빈 DB(init.sql 직후, 이미 4-arg)와 기존 DB(옛 2-arg) 양쪽에서 안전.

-- 옛 2-arg 시그니처를 먼저 제거(새 4-arg 는 replace 가 아니라 overload 가 되므로).
DROP FUNCTION IF EXISTS f_graph_neighbors(TEXT, INT);

CREATE OR REPLACE FUNCTION f_graph_neighbors(
    p_entity_rid TEXT, p_max_hops INT, p_tenant TEXT, p_clearance classification_level
) RETURNS TABLE (
    hop INT, edge_rid TEXT, edge_type TEXT,
    from_rid TEXT, from_name TEXT, to_rid TEXT, to_name TEXT,
    confidence FLOAT, source_category TEXT
) AS $$
WITH RECURSIVE neighbors AS (
    SELECT 1 as hop, e.rid as edge_rid, e.edge_type, e.from_rid, ef.name as from_name,
           e.to_rid, et.name as to_name, e.confidence, e.source_category
    FROM edges e
    JOIN entities ef ON e.from_rid = ef.rid JOIN entities et ON e.to_rid = et.rid
    WHERE e.status = 'active' AND (e.from_rid = p_entity_rid OR e.to_rid = p_entity_rid)
      AND ef.tenant = p_tenant AND ef.classification <= p_clearance
      AND ef.is_quarantined = false AND ef.status = 'active'
      AND et.tenant = p_tenant AND et.classification <= p_clearance
      AND et.is_quarantined = false AND et.status = 'active'
    UNION ALL
    SELECT n.hop + 1, e.rid as edge_rid, e.edge_type, e.from_rid, ef.name,
           e.to_rid, et.name, e.confidence, e.source_category
    FROM edges e
    JOIN entities ef ON e.from_rid = ef.rid JOIN entities et ON e.to_rid = et.rid
    JOIN neighbors n ON (e.from_rid = n.to_rid OR e.to_rid = n.from_rid)
    WHERE e.status = 'active' AND n.hop < p_max_hops AND e.rid != n.edge_rid
      AND ef.tenant = p_tenant AND ef.classification <= p_clearance
      AND ef.is_quarantined = false AND ef.status = 'active'
      AND et.tenant = p_tenant AND et.classification <= p_clearance
      AND et.is_quarantined = false AND et.status = 'active'
)
SELECT * FROM neighbors;
$$ LANGUAGE sql STABLE;

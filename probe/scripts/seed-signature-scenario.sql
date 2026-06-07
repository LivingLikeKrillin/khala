-- 시그니처 시나리오 S1 시드 (검증 전용 — 프로덕션 금지)
-- 전제: order-service, inventory-service 엔티티가 이미 존재해야 함 (gazetteer/ingest 선행).
-- observed_edges 스키마(init.sql 189~213): from_name/to_name 컬럼은 없고
--   from_rid/to_rid TEXT NOT NULL REFERENCES entities(rid) 사용. rid는 콘텐츠 해시라
--   직접 만들 수 없으므로 name으로 조회한다.
-- 설계 엣지(edges)는 일부러 만들지 않는다 → /diff가 observed_only를 산출한다.

DO $$
DECLARE v_from TEXT; v_to TEXT;
BEGIN
  SELECT rid INTO v_from FROM entities
    WHERE name = 'order-service' AND tenant = 'default' AND status = 'active';
  SELECT rid INTO v_to FROM entities
    WHERE name = 'inventory-service' AND tenant = 'default' AND status = 'active';
  IF v_from IS NULL OR v_to IS NULL THEN
    RAISE EXCEPTION 'order-service/inventory-service 엔티티가 없습니다 — 먼저 khala ingest로 생성하세요 (Entities missing)';
  END IF;

  INSERT INTO observed_edges
    (rid, rtype, tenant, edge_type, from_rid, to_rid,
     call_count, error_rate, latency_p95, sample_trace_ids, trace_query_ref,
     status, created_at, updated_at)
  VALUES
    ('observed_edge_sig_s1', 'observed_edge', 'default', 'CALLS_OBSERVED', v_from, v_to,
     1500, 0.20, 850, ARRAY['trace-abc123'], 'tempo:order->inventory',
     'active', NOW(), NOW())
  ON CONFLICT (rid) DO UPDATE
    SET error_rate = EXCLUDED.error_rate, call_count = EXCLUDED.call_count;
END $$;

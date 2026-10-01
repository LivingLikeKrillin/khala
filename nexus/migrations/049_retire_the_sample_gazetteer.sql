-- 예시 엔티티 목록(전자상거래 다섯 — 이제 nexus/entities.example.yaml)이 테넌트마다 심어 둔 엔티티와
-- 그 엔티티에 걸린 간선을 soft_deleted 로 내린다.
--
-- ⛔ 왜 (2026-10-01). 그 목록은 예시인데 `entities.yaml` 로 놓여 모든 테넌트에 쓰였다. 질의 검출은 이름과
-- 별칭을 부분 문자열로 찾아서(`order` · `payment`) 무관한 코퍼스의 질의를 엔티티로 잡았고 — 로봇 사건
-- 질의 32건이 전부 `order-service` 로 잡혔다 — 앱은 기동·적재 때마다 다섯을 테넌트에 심었다(출처 없음).
-- 그날 라이브에 일곱 테넌트 35행 + 간선 1. 목록은 이제 예시로만 남고 읽히지 않는다. 이것은 남은 행을 치운다.
--
-- 지우지 않고 내린다: 정책 필터(status = 'active')가 검색 · 그래프 · 자동완성에서 빼 주고, 되돌릴 수 있다
-- (목록이 다시 적으면 `ensure_entity_exists` 가 되살린다).
--
-- 고르는 기준은 **(종류, 이름, 설명) 셋이 예시와 같은 행**이다. 이름만으로 고르면 같은 이름을 자기 목록에 둔
-- 배포의 엔티티까지 내린다. 두 번 돌아도 같다.
--
-- 데이터를 바꾸는 CTE(retired_edges)는 바깥 문이 읽지 않아도 정확히 한 번 끝까지 돈다(PostgreSQL 보장).
WITH sample (entity_type, name, description) AS (VALUES
    ('Service', 'payment-service',      '결제 처리 핵심 서비스'),
    ('Service', 'notification-service', '이메일/SMS/푸시 알림 전송'),
    ('Service', 'order-service',        '주문 생성 및 관리'),
    ('Topic',   'payment.completed',    '결제 완료 시 발행되는 이벤트 토픽'),
    ('Topic',   'order.created',        '새 주문 생성 시 발행되는 이벤트 토픽')
),
seeded AS (
    SELECT e.rid FROM entities e JOIN sample s USING (entity_type, name, description)
),
retired_edges AS (
    UPDATE edges SET status = 'soft_deleted', updated_at = now()
     WHERE status = 'active'
       AND (from_rid IN (SELECT rid FROM seeded) OR to_rid IN (SELECT rid FROM seeded))
)
UPDATE entities SET status = 'soft_deleted', updated_at = now()
 WHERE status = 'active' AND rid IN (SELECT rid FROM seeded);

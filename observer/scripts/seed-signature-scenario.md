# 시그니처 시나리오 S1 — 라이브 실증 런북

목적: Observer 트러블슈팅 그라운딩이 제네릭 리뷰가 못 보는 observed_only 갭을 실제로
드러냄을 증명.

## 절차
1. Nexus 기동: `cd ../../nexus && docker-compose up -d`
2. 설계 문서 인덱싱:
   `nexus ingest ../observer/tests/fixtures/order-service-design.md --force`
3. 관측 엣지 시드:
   `docker exec -i nexus-db psql -U nexus -d nexus < scripts/seed-signature-scenario.sql`
4. 가용성 확인: `observer nexus:status` → observed_edges_count ≥ 1
5. 실증:
   `observer troubleshoot "NPE at com.shop.order.OrderService.checkout(OrderService.java:88)"`
   기대 출력: designObservationGaps에 `observed_only: order-service → inventory-service`
   (error_rate 0.20) 가 포함.
6. 대조: 동일 입력을 일반 코드 리뷰 스킬에 주면 trace가 없어 이 갭을 낼 수 없음 → 해자 실증.

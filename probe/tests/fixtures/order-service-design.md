# Order Service 설계

order-service는 결제 완료 후 order 상태만 갱신한다.
**inventory-service를 직접 호출하지 않는다** — 재고 차감은 이벤트로 비동기 처리한다.

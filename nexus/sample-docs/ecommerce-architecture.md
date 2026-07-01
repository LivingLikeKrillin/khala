# 커머스 서비스 아키텍처 (샘플)

order-service, payment-service, notification-service 세 서비스와 order.created, payment.completed 이벤트 토픽으로 구성된 이벤트 주도 예시 시스템이다. 아래 각 절은 하나의 관계를 설명한다.

## 결제 호출

결제가 필요한 시점에 order-service는 payment-service를 호출한다.

## 주문 생성 이벤트 발행

주문이 생성되면 order-service는 order.created 이벤트를 발행한다.

## 결제 완료 이벤트 발행

결제가 완료되면 payment-service는 payment.completed 이벤트를 발행한다.

## 결제 완료 이벤트 구독

notification-service는 payment.completed 이벤트를 구독한다.

## 주문 생성 이벤트 구독

notification-service는 order.created 이벤트를 수신한다.

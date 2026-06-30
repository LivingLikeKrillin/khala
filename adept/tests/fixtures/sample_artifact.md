# Payment service

The payment service publishes the `orders` topic. Downstream consumers (the
fulfillment and analytics services) subscribe to that topic to react to new orders.

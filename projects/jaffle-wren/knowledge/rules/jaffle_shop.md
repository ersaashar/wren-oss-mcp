# Jaffle Shop business rules

## Canonical tables

- `customers` — one row per customer. Use this for customer counts.
- `orders` — one row per order. Use this for order and revenue questions.
- Do not query `raw_*` seeds or `stg_*` views; they exist only as dbt build inputs.

## Money

- All amounts are in AUD.
- `orders.amount` is the order total and equals
  `credit_card_amount + coupon_amount + bank_transfer_amount + gift_card_amount`.
  Sum `amount` for revenue; never sum two or more payment-method columns
  together, or payments are double counted.
- Payment-method columns hold `0` (not NULL) when that method was unused.

## Order status

| status           | meaning                                                              |
|------------------|----------------------------------------------------------------------|
| `placed`         | Order placed, not yet left the warehouse                             |
| `shipped`        | Shipped to the customer, in transit                                  |
| `completed`      | Received by the customer                                             |
| `returned`       | Returned by the customer and received back at the warehouse          |
| `return_pending` | Customer requested a return; not yet received at the warehouse       |

Filter on `status` explicitly when a question asks about a particular stage of
the order lifecycle.

## Customer aggregates

- `customers.number_of_orders`, `first_order`, `most_recent_order`, and
  `customer_lifetime_value` are derived from `orders`.
- Customers with no orders have NULL (not 0) in all four of those columns.
  Use `COALESCE(customer_lifetime_value, 0)` when a zero baseline is needed,
  and treat NULL as "no orders", not as missing data.
- `customer_lifetime_value` sums payments across all of the customer's orders
  regardless of order status, so it is not equal to the sum of `completed`
  order amounts.

## Dates

All dates are UTC calendar dates. `orders.order_date` spans 2018-01-01 to
2018-04-09.

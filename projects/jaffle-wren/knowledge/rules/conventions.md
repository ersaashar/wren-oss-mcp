## Naming Conventions

- "revenue" always means the order `amount`, not one of the per-payment-method

  columns like `credit_card_amount`

- "active customers" means customers with at least one order in the last 90 days

## Query Rules

- Always use order\_date for time-based filtering, not created\_at
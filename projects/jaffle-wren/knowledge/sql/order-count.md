---
nl: How many orders are there?
sql: |
  SELECT COUNT(*) AS order_count FROM orders
datasource: duckdb
source: user
tags:
  - orders
---
Counts every row in the `orders` model. Returns 99 for the Jaffle fixture.

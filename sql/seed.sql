-- seed.sql: empty the shop tables and load a fixed, repeatable dataset.
\echo 'Emptying tables...'
TRUNCATE order_items, orders, products, customers RESTART IDENTITY CASCADE;

\echo 'Loading 200 products...'
INSERT INTO products (sku, name, price, attrs)
SELECT 'SKU-' || lpad(CAST(n AS text), 4, '0'),
       'Product ' || n,
       (5 + (n * 37) % 495) + 0.99,
       jsonb_build_object(
           'category',  (ARRAY['books', 'games', 'tools', 'garden', 'audio'])[1 + n % 5],
           'color',     (ARRAY['red', 'green', 'blue', 'black'])[1 + n % 4],
           'weight_kg', round((n % 50) / 10.0 + 0.1, 1))
FROM generate_series(1, 200) AS n;

\echo 'Loading 10,000 customers...'
INSERT INTO customers (email, name, country, created_at)
SELECT 'user' || n || '@example.com',
       'Customer ' || n,
       (ARRAY['US', 'MX', 'VE', 'ES', 'DE', 'JP', 'BR', 'CA'])[1 + n % 8],
       timestamptz '2024-01-01 00:00+00' + n * interval '50 minutes'
FROM generate_series(1, 10000) AS n;

\echo 'Loading 200,000 orders...'
INSERT INTO orders (customer_id, status, ordered_at)
SELECT 1 + (n * 7919) % 10000,
       CASE WHEN n % 100 = 0 THEN 'new'
            WHEN n % 100 < 3 THEN 'cancelled'
            WHEN n % 100 < 10 THEN 'paid'
            ELSE 'shipped'
       END,
       timestamptz '2025-01-01 00:00+00' + n * interval '157 seconds'
FROM generate_series(1, 200000) AS n;

\echo 'Loading order lines...'
INSERT INTO order_items (order_id, product_id, qty, unit_price)
SELECT orders.id,
       products.id,
       1 + (orders.id + line_number) % 4,
       products.price
FROM orders
CROSS JOIN LATERAL generate_series(0, orders.id % 3) AS line_number
JOIN products ON products.id = 1 + (orders.id * 7 + line_number * 13) % 200;

ANALYZE;

SELECT (SELECT count(*) FROM products)    AS products,
       (SELECT count(*) FROM customers)   AS customers,
       (SELECT count(*) FROM orders)      AS orders,
       (SELECT count(*) FROM order_items) AS order_items;

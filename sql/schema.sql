CREATE TABLE customers (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       text NOT NULL UNIQUE,
    name        text NOT NULL,
    country     char(2) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku    text NOT NULL UNIQUE,
    name   text NOT NULL,
    price  numeric(10,2) NOT NULL CHECK (price > 0),
    attrs  jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  bigint NOT NULL REFERENCES customers (id),
    status       text NOT NULL DEFAULT 'new'
                 CHECK (status IN ('new', 'paid', 'shipped', 'cancelled')),
    ordered_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    order_id    bigint NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id  bigint NOT NULL REFERENCES products (id),
    qty         integer NOT NULL CHECK (qty > 0),
    unit_price  numeric(10,2) NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

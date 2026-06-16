-- 초기 테이블 생성

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(10) NOT NULL CHECK (role IN ('seller', 'buyer')),
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    price       INTEGER NOT NULL,
    description TEXT,
    category    VARCHAR(50) DEFAULT '기타',
    image_url   VARCHAR(500),
    stock       INTEGER NOT NULL DEFAULT 0,
    seller_id   INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS timesale (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER REFERENCES product(id) ON DELETE CASCADE,
    sale_price  INTEGER NOT NULL,
    sale_start  TIMESTAMP NOT NULL,
    sale_end    TIMESTAMP NOT NULL,
    stock       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id          SERIAL PRIMARY KEY,
    buyer_id    INTEGER REFERENCES users(id),
    address     TEXT,
    status      VARCHAR(20) DEFAULT 'pending',
    total_price INTEGER NOT NULL DEFAULT 0,
    ordered_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id             SERIAL PRIMARY KEY,
    order_id       INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES product(id),
    product_name   VARCHAR(100) NOT NULL,
    quantity       INTEGER NOT NULL DEFAULT 1,
    price_at_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id         SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES product(id) ON DELETE CASCADE,
    buyer_id   INTEGER REFERENCES users(id),
    rating     INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment    TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (product_id, buyer_id)
);

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import List
from datetime import datetime, timedelta
import os, re

app = FastAPI(title="Infraboy Shop")

DB_URL     = os.getenv("DB_URL", "postgresql://scott:tiger@localhost:5432/scott_db")
SECRET_KEY = os.getenv("SECRET_KEY", "infraboy-dev-secret-key")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HOURS = 24
EMAIL_RE   = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
CATEGORIES = ['전자기기', '패션', '식품', '뷰티', '스포츠', '도서', '기타']

engine      = create_engine(DB_URL, poolclass=QueuePool, pool_size=5, max_overflow=5, pool_timeout=30, pool_pre_ping=True)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2      = OAuth2PasswordBearer(tokenUrl="/auth/login")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── 모델 ───────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: str
    password: str
    role: str

class ProductCreate(BaseModel):
    name: str
    price: int
    description: str = ""
    category: str = "기타"
    image_url: str = ""
    stock: int = 0
    is_timesale: bool = False
    sale_price: int = 0
    sale_stock: int = 0
    sale_duration_min: int = 60

class CartItem(BaseModel):
    product_id: int
    quantity: int

class OrderCreate(BaseModel):
    address: str
    items: List[CartItem]

class ReviewCreate(BaseModel):
    product_id: int
    rating: int
    comment: str = ""


# ── 인증 헬퍼 ──────────────────────────────────────────────────

def hash_password(pw): return pwd_context.hash(pw)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)

def create_token(user_id, username, role):
    return jwt.encode({
        "sub": str(user_id), "username": username, "role": role,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2)):
    try:
        p = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {"id": int(p["sub"]), "username": p["username"], "role": p["role"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

def require_seller(user=Depends(get_current_user)):
    if user["role"] != "seller": raise HTTPException(403, "판매자만 접근 가능합니다")
    return user

def require_buyer(user=Depends(get_current_user)):
    if user["role"] != "buyer": raise HTTPException(403, "구매자만 접근 가능합니다")
    return user


# ── 기본 ───────────────────────────────────────────────────────

@app.get("/")
def index(): return FileResponse("static/index.html")

@app.get("/health")
def health(): return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/categories")
def categories(): return {"data": CATEGORIES}


# ── 인증 ───────────────────────────────────────────────────────

@app.post("/auth/register")
def register(data: UserRegister):
    if data.role not in ("seller", "buyer"):
        raise HTTPException(400, "role은 seller 또는 buyer여야 합니다")
    if not EMAIL_RE.match(data.username):
        raise HTTPException(400, "올바른 이메일 형식이 아닙니다")
    with engine.begin() as conn:
        if conn.execute(text("SELECT id FROM users WHERE username=:u"), {"u": data.username}).first():
            raise HTTPException(400, "이미 사용 중인 이메일입니다")
        conn.execute(
            text("INSERT INTO users (username,password_hash,role) VALUES (:u,:p,:r)"),
            {"u": data.username, "p": hash_password(data.password), "r": data.role}
        )
    return {"message": "회원가입이 완료됐습니다"}

@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    with engine.connect() as conn:
        user = conn.execute(
            text("SELECT id,password_hash,role FROM users WHERE username=:u"), {"u": form.username}
        ).mappings().first()
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(401, "아이디 또는 비밀번호가 틀렸습니다")
    token = create_token(user["id"], form.username, user["role"])
    return {"access_token": token, "token_type": "bearer", "role": user["role"], "username": form.username}

@app.get("/auth/me")
def me(user=Depends(get_current_user)): return user


# ── 상품 (공개) ────────────────────────────────────────────────

@app.get("/products")
def get_products(category: str = "", search: str = ""):
    q = """
        SELECT p.id, p.name, p.price, p.description, p.category, p.image_url, p.stock,
               u.username AS seller_name,
               ROUND(COALESCE(AVG(r.rating), 0), 1) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM product p
        LEFT JOIN users u ON p.seller_id = u.id
        LEFT JOIN reviews r ON r.product_id = p.id
        WHERE 1=1
    """
    params = {}
    if category:
        q += " AND p.category = :cat"; params["cat"] = category
    if search:
        q += " AND (p.name ILIKE :s OR p.description ILIKE :s)"; params["s"] = f"%{search}%"
    q += " GROUP BY p.id, u.username ORDER BY p.id DESC"
    with engine.connect() as conn:
        rows = conn.execute(text(q), params).mappings().all()
    return {"status": "success", "data": [dict(r) for r in rows]}

@app.get("/products/{product_id}")
def get_product(product_id: int):
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT p.id, p.name, p.price, p.description, p.category, p.image_url, p.stock,
                   u.username AS seller_name,
                   ROUND(COALESCE(AVG(r.rating), 0), 1) AS avg_rating,
                   COUNT(r.id) AS review_count
            FROM product p
            LEFT JOIN users u ON p.seller_id = u.id
            LEFT JOIN reviews r ON r.product_id = p.id
            WHERE p.id = :id
            GROUP BY p.id, u.username
        """), {"id": product_id}).mappings().first()
        if not row: raise HTTPException(404, "상품을 찾을 수 없습니다")
        reviews = conn.execute(text("""
            SELECT r.id, r.rating, r.comment, r.created_at, u.username AS reviewer
            FROM reviews r JOIN users u ON r.buyer_id = u.id
            WHERE r.product_id = :id ORDER BY r.created_at DESC
        """), {"id": product_id}).mappings().all()
    return {"status": "success", "data": dict(row), "reviews": [dict(r) for r in reviews]}

@app.get("/timesale")
def get_timesale():
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.name, p.price, p.description, p.category, p.image_url,
                   t.sale_price, t.sale_end, t.stock,
                   ROUND((1 - t.sale_price::numeric / p.price) * 100) AS discount_pct,
                   u.username AS seller_name
            FROM timesale t
            JOIN product p ON t.product_id = p.id
            LEFT JOIN users u ON p.seller_id = u.id
            WHERE t.sale_start <= NOW() AND t.sale_end >= NOW() AND t.stock > 0
            ORDER BY t.sale_end ASC
        """)).mappings().all()
    return {"status": "success", "data": [dict(r) for r in rows]}


# ── 상품 (판매자) ──────────────────────────────────────────────

@app.post("/products")
def create_product(data: ProductCreate, user=Depends(require_seller)):
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO product (name,price,description,category,image_url,stock,seller_id)
            VALUES (:n,:p,:d,:cat,:img,:st,:s) RETURNING id
        """), {"n": data.name, "p": data.price, "d": data.description,
               "cat": data.category, "img": data.image_url, "st": data.stock, "s": user["id"]})
        product_id = result.first()[0]

        if data.is_timesale and data.sale_price > 0 and data.sale_stock > 0:
            now = datetime.now()
            conn.execute(text("""
                INSERT INTO timesale (product_id,sale_price,sale_start,sale_end,stock)
                VALUES (:pid,:sp,:ss,:se,:st)
            """), {"pid": product_id, "sp": data.sale_price,
                   "ss": now, "se": now + timedelta(minutes=data.sale_duration_min),
                   "st": data.sale_stock})
    return {"status": "success", "message": "상품이 등록됐습니다", "product_id": product_id}

@app.delete("/products/{product_id}")
def delete_product(product_id: int, user=Depends(require_seller)):
    with engine.begin() as conn:
        row = conn.execute(text("SELECT seller_id FROM product WHERE id=:id"), {"id": product_id}).first()
        if not row: raise HTTPException(404, "상품을 찾을 수 없습니다")
        if row[0] != user["id"]: raise HTTPException(403, "본인이 등록한 상품만 삭제할 수 있습니다")
        conn.execute(text("DELETE FROM product WHERE id=:id"), {"id": product_id})
    return {"status": "success", "message": "상품이 삭제됐습니다"}

@app.get("/seller/products")
def seller_products(user=Depends(require_seller)):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT p.id, p.name, p.price, p.description, p.category, p.image_url, p.stock,
                   t.sale_price, t.sale_end, t.stock AS sale_stock,
                   CASE WHEN t.id IS NOT NULL AND t.sale_end > NOW() THEN true ELSE false END AS is_timesale,
                   ROUND(COALESCE(AVG(r.rating), 0), 1) AS avg_rating,
                   COUNT(DISTINCT r.id) AS review_count
            FROM product p
            LEFT JOIN timesale t ON t.product_id = p.id
            LEFT JOIN reviews r ON r.product_id = p.id
            WHERE p.seller_id = :uid
            GROUP BY p.id, t.id ORDER BY p.id DESC
        """), {"uid": user["id"]}).mappings().all()
    return {"status": "success", "data": [dict(r) for r in rows]}

@app.get("/seller/stats")
def seller_stats(user=Depends(require_seller)):
    with engine.connect() as conn:
        stats = conn.execute(text("""
            SELECT COUNT(DISTINCT p.id) AS total_products,
                   COUNT(DISTINCT oi.order_id) AS total_orders,
                   COALESCE(SUM(oi.price_at_order * oi.quantity), 0) AS total_revenue
            FROM product p
            LEFT JOIN order_items oi ON oi.product_id = p.id
            WHERE p.seller_id = :uid
        """), {"uid": user["id"]}).mappings().first()
        monthly = conn.execute(text("""
            SELECT TO_CHAR(DATE_TRUNC('month', o.ordered_at), 'YYYY-MM') AS month,
                   COALESCE(SUM(oi.price_at_order * oi.quantity), 0) AS revenue,
                   COUNT(DISTINCT o.id) AS orders
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN product p ON oi.product_id = p.id
            WHERE p.seller_id = :uid
            GROUP BY DATE_TRUNC('month', o.ordered_at)
            ORDER BY DATE_TRUNC('month', o.ordered_at) DESC LIMIT 6
        """), {"uid": user["id"]}).mappings().all()
    return {"status": "success", "data": dict(stats), "monthly": [dict(r) for r in monthly]}

@app.get("/seller/orders")
def seller_orders(user=Depends(require_seller)):
    with engine.connect() as conn:
        orders = conn.execute(text("""
            SELECT DISTINCT o.id, o.status, o.address, o.ordered_at,
                   o.total_price, u.username AS buyer_name
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN product p ON oi.product_id = p.id
            JOIN users u ON o.buyer_id = u.id
            WHERE p.seller_id = :uid
            ORDER BY o.ordered_at DESC LIMIT 50
        """), {"uid": user["id"]}).mappings().all()
        result = []
        for order in orders:
            items = conn.execute(text("""
                SELECT oi.product_name, oi.quantity, oi.price_at_order
                FROM order_items oi
                JOIN product p ON oi.product_id = p.id
                WHERE oi.order_id = :oid AND p.seller_id = :uid
            """), {"oid": order["id"], "uid": user["id"]}).mappings().all()
            result.append({**dict(order), "items": [dict(i) for i in items]})
    return {"status": "success", "data": result}

@app.put("/orders/{order_id}/status")
def update_order_status(order_id: int, status: str, user=Depends(require_seller)):
    if status not in ["confirmed", "shipped", "delivered", "cancelled"]:
        raise HTTPException(400, "유효하지 않은 상태입니다")
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT 1 FROM order_items oi
            JOIN product p ON oi.product_id = p.id
            WHERE oi.order_id = :oid AND p.seller_id = :uid
        """), {"oid": order_id, "uid": user["id"]}).first()
        if not row: raise HTTPException(403, "권한이 없습니다")
        conn.execute(text("UPDATE orders SET status=:s WHERE id=:id"), {"s": status, "id": order_id})
    return {"status": "success", "message": "주문 상태가 업데이트됐습니다"}


# ── 주문 (구매자) ──────────────────────────────────────────────

@app.post("/orders")
def create_order(data: OrderCreate, user=Depends(require_buyer)):
    if not data.address.strip(): raise HTTPException(400, "배송 주소를 입력해주세요")
    if not data.items: raise HTTPException(400, "주문 상품이 없습니다")
    with engine.begin() as conn:
        total = 0
        products = []
        for item in data.items:
            row = conn.execute(
                text("SELECT id,name,price,stock FROM product WHERE id=:pid FOR UPDATE"),
                {"pid": item.product_id}
            ).mappings().first()
            if not row: raise HTTPException(404, "상품을 찾을 수 없습니다")
            if row["stock"] < item.quantity:
                raise HTTPException(409, f"'{row['name']}' 재고가 부족합니다 (재고: {row['stock']}개)")
            products.append({**dict(row), "quantity": item.quantity})
            total += row["price"] * item.quantity

        result = conn.execute(
            text("INSERT INTO orders (buyer_id,address,status,total_price,ordered_at) VALUES (:uid,:addr,'pending',:total,:now) RETURNING id"),
            {"uid": user["id"], "addr": data.address, "total": total, "now": datetime.now()}
        )
        order_id = result.first()[0]

        for p in products:
            conn.execute(
                text("INSERT INTO order_items (order_id,product_id,product_name,quantity,price_at_order) VALUES (:oid,:pid,:name,:qty,:price)"),
                {"oid": order_id, "pid": p["id"], "name": p["name"], "qty": p["quantity"], "price": p["price"]}
            )
            conn.execute(
                text("UPDATE product SET stock = stock - :qty WHERE id=:pid"),
                {"qty": p["quantity"], "pid": p["id"]}
            )
    return {"status": "success", "message": "주문이 완료됐습니다", "order_id": order_id}

@app.post("/orders/timesale")
def order_timesale(product_id: int, quantity: int = 1, user=Depends(require_buyer)):
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT t.stock, p.name, t.sale_price FROM timesale t
            JOIN product p ON t.product_id = p.id
            WHERE t.product_id=:pid AND t.sale_end >= NOW() FOR UPDATE
        """), {"pid": product_id}).mappings().first()
        if not row: raise HTTPException(404, "진행 중인 타임세일 상품을 찾을 수 없습니다")
        if row["stock"] < quantity: raise HTTPException(409, "재고가 부족합니다")

        conn.execute(text("UPDATE timesale SET stock = stock - :qty WHERE product_id=:pid"),
                     {"qty": quantity, "pid": product_id})
        result = conn.execute(
            text("INSERT INTO orders (buyer_id,address,status,total_price,ordered_at) VALUES (:uid,'타임세일 직구','confirmed',:total,:now) RETURNING id"),
            {"uid": user["id"], "total": row["sale_price"] * quantity, "now": datetime.now()}
        )
        order_id = result.first()[0]
        conn.execute(
            text("INSERT INTO order_items (order_id,product_id,product_name,quantity,price_at_order) VALUES (:oid,:pid,:name,:qty,:price)"),
            {"oid": order_id, "pid": product_id, "name": row["name"], "qty": quantity, "price": row["sale_price"]}
        )
    return {"status": "success", "message": "타임세일 주문이 완료됐습니다", "order_id": order_id}

@app.get("/orders")
def get_orders(user=Depends(get_current_user)):
    with engine.connect() as conn:
        orders = conn.execute(text("""
            SELECT o.id, o.status, o.address, o.total_price, o.ordered_at
            FROM orders o WHERE o.buyer_id = :uid
            ORDER BY o.ordered_at DESC LIMIT 30
        """), {"uid": user["id"]}).mappings().all()
        result = []
        for order in orders:
            items = conn.execute(text("""
                SELECT oi.product_id, oi.product_name, oi.quantity, oi.price_at_order
                FROM order_items oi WHERE oi.order_id = :oid
            """), {"oid": order["id"]}).mappings().all()
            result.append({**dict(order), "items": [dict(i) for i in items]})
    return {"status": "success", "data": result}


# ── 리뷰 ───────────────────────────────────────────────────────

@app.post("/reviews")
def create_review(data: ReviewCreate, user=Depends(require_buyer)):
    if not 1 <= data.rating <= 5: raise HTTPException(400, "별점은 1~5 사이여야 합니다")
    with engine.begin() as conn:
        if conn.execute(text("SELECT id FROM reviews WHERE product_id=:pid AND buyer_id=:uid"),
                        {"pid": data.product_id, "uid": user["id"]}).first():
            raise HTTPException(400, "이미 리뷰를 작성했습니다")
        conn.execute(
            text("INSERT INTO reviews (product_id,buyer_id,rating,comment) VALUES (:pid,:uid,:r,:c)"),
            {"pid": data.product_id, "uid": user["id"], "r": data.rating, "c": data.comment}
        )
    return {"status": "success", "message": "리뷰가 등록됐습니다"}

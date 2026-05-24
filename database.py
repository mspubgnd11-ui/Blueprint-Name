import sqlite3
import config

def get_conn():
    return sqlite3.connect(config.DB_NAME)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            balance     REAL DEFAULT 0.0,
            joined_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            number      TEXT,
            activation_id TEXT,
            service     TEXT DEFAULT 'whatsapp',
            status      TEXT DEFAULT 'pending',
            otp_code    TEXT,
            cost        REAL DEFAULT 0.0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            type        TEXT,   -- 'deposit' | 'purchase' | 'refund'
            amount      REAL,
            note        TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# ─── المستخدمين ─────────────────────────────────────────
def register_user(user_id, username, full_name):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
    """, (user_id, username, full_name))
    conn.commit(); conn.close()

def get_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row  # (user_id, username, full_name, balance, joined_at)

def get_balance(user_id):
    conn = get_conn()
    row = conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0.0

def update_balance(user_id, amount, note="", tx_type="deposit"):
    """amount موجب = إضافة، سالب = خصم"""
    conn = get_conn()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.execute("INSERT INTO transactions (user_id, type, amount, note) VALUES (?,?,?,?)",
                 (user_id, tx_type, amount, note))
    conn.commit(); conn.close()

def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT user_id, username, full_name, balance FROM users ORDER BY joined_at DESC").fetchall()
    conn.close()
    return rows

# ─── الطلبات ─────────────────────────────────────────────
def create_order(user_id, number, activation_id, cost):
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO orders (user_id, number, activation_id, cost)
        VALUES (?,?,?,?)
    """, (user_id, number, activation_id, cost))
    order_id = cur.lastrowid
    conn.commit(); conn.close()
    return order_id

def update_order(activation_id, status, otp_code=None):
    conn = get_conn()
    conn.execute("""
        UPDATE orders SET status=?, otp_code=COALESCE(?,otp_code)
        WHERE activation_id=?
    """, (status, otp_code, activation_id))
    conn.commit(); conn.close()

def get_order_by_activation(activation_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM orders WHERE activation_id=?", (activation_id,)).fetchone()
    conn.close()
    return row

import sqlite3
import datetime

DB_FILE = "vpn.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            sub_id TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP
        )
    ''')

    # Update existing table with new columns if they don't exist
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN client_uuid TEXT")
    except sqlite3.OperationalError:
        pass # Column already exists

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN trial_used BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN notified_3_days BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL, -- 'percent' or 'rub'
            discount_value REAL NOT NULL,
            uses_left INTEGER NOT NULL,
            expires_at TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS plans (
            plan_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            days INTEGER NOT NULL,
            price REAL NOT NULL
        )
    ''')

    # Populate default plans if not exists
    cursor.execute("SELECT COUNT(*) FROM plans")
    if cursor.fetchone()[0] == 0:
        default_plans = [
            ("trial", "3 дня (Пробный)", 3, 0),
            ("1m", "1 месяц", 30, 150),
            ("3m", "3 месяца", 90, 400),
            ("6m", "6 месяцев", 180, 700),
            ("1y", "1 год", 365, 1200)
        ]
        cursor.executemany("INSERT INTO plans (plan_id, name, days, price) VALUES (?, ?, ?, ?)", default_plans)

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT UNIQUE NOT NULL,
            telegram_id INTEGER NOT NULL,
            plan_duration_days INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    ''')

    try:
        cursor.execute("ALTER TABLE pending_payments ADD COLUMN target_telegram_id INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pending_payments ADD COLUMN plan_id TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pending_payments ADD COLUMN amount REAL")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pending_payments ADD COLUMN promo_code TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pending_payments ADD COLUMN balance_used REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            referrer_id INTEGER,
            rewarded BOOLEAN DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            plan_id TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

def create_user(telegram_id: int, sub_id: str, client_uuid: str, expires_at: datetime.datetime = None, trial_used: int = 0, notified_3_days: int = 0, username: str = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    created_at = datetime.datetime.now()
    try:
        cursor.execute(
            "INSERT INTO users (telegram_id, sub_id, created_at, expires_at, client_uuid, trial_used, notified_3_days, username) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (telegram_id, sub_id, created_at, expires_at, client_uuid, trial_used, notified_3_days, username)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass # User might already exist
    finally:
        conn.close()

def get_user_by_username(username: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user(telegram_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_expiry(telegram_id: int, expires_at: datetime.datetime):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET expires_at = ?, notified_3_days = 0 WHERE telegram_id = ?", (expires_at, telegram_id))
    conn.commit()
    conn.close()

def set_trial_used(telegram_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET trial_used = 1 WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()

def set_notified_3_days(telegram_id: int, status: bool):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET notified_3_days = ? WHERE telegram_id = ?", (int(status), telegram_id))
    conn.commit()
    conn.close()

def get_expiring_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    three_days_from_now = datetime.datetime.now() + datetime.timedelta(days=3)
    cursor.execute("SELECT * FROM users WHERE expires_at <= ? AND notified_3_days = 0 AND expires_at >= ?",
                   (three_days_from_now, datetime.datetime.now()))
    users = cursor.fetchall()
    conn.close()
    return users

def create_pending_payment(payment_id: str, telegram_id: int, plan_duration_days: int, target_telegram_id: int = None, plan_id: str = None, amount: float = None, promo_code: str = None, balance_used: float = 0.0):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    created_at = datetime.datetime.now()
    cursor.execute(
        "INSERT INTO pending_payments (payment_id, telegram_id, plan_duration_days, created_at, target_telegram_id, plan_id, amount, promo_code, balance_used) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (payment_id, telegram_id, plan_duration_days, created_at, target_telegram_id, plan_id, amount, promo_code, balance_used)
    )
    conn.commit()
    conn.close()

def get_pending_payment(payment_id: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_payments WHERE payment_id = ?", (payment_id,))
    payment = cursor.fetchone()
    conn.close()
    return payment

def delete_pending_payment(payment_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_payments WHERE payment_id = ?", (payment_id,))
    conn.commit()
    conn.close()

def add_referral(user_id: int, referrer_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR IGNORE INTO referrals (user_id, referrer_id) VALUES (?, ?)", (user_id, referrer_id))
        conn.commit()
    finally:
        conn.close()

def get_referrer(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM referrals WHERE user_id = ?", (user_id,))
    referrer = cursor.fetchone()
    conn.close()
    return referrer

def mark_referral_rewarded(user_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE referrals SET rewarded = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def update_username(telegram_id: int, username: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET username = ? WHERE telegram_id = ?", (username, telegram_id))
    conn.commit()
    conn.close()

def record_sale(telegram_id: int, plan_id: str, amount: float):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    created_at = datetime.datetime.now()
    cursor.execute(
        "INSERT INTO sales (telegram_id, plan_id, amount, created_at) VALUES (?, ?, ?, ?)",
        (telegram_id, plan_id, amount, created_at)
    )
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    now = datetime.datetime.now()

    # Total users
    cursor.execute("SELECT COUNT(*) as count FROM users")
    total_users = cursor.fetchone()['count']

    # Active subscriptions
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE expires_at > ?", (now,))
    active_subs = cursor.fetchone()['count']

    # Expired subscriptions
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
    expired_subs = cursor.fetchone()['count']

    # Trial users
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE trial_used = 1")
    trial_users = cursor.fetchone()['count']

    # Sales & Earnings for today, week, month
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - datetime.timedelta(days=7)
    month_ago = today - datetime.timedelta(days=30)

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total FROM sales WHERE created_at >= ?", (today,))
    row = cursor.fetchone()
    sales_today = row['count']
    earnings_today = row['total']

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total FROM sales WHERE created_at >= ?", (week_ago,))
    row = cursor.fetchone()
    sales_week = row['count']
    earnings_week = row['total']

    cursor.execute("SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total FROM sales WHERE created_at >= ?", (month_ago,))
    row = cursor.fetchone()
    sales_month = row['count']
    earnings_month = row['total']

    # Top 3 plans
    cursor.execute("SELECT plan_id, COUNT(*) as count FROM sales GROUP BY plan_id ORDER BY count DESC LIMIT 3")
    top_plans = [(row['plan_id'], row['count']) for row in cursor.fetchall()]

    conn.close()

    return {
        "total_users": total_users,
        "active_subs": active_subs,
        "expired_subs": expired_subs,
        "trial_users": trial_users,
        "sales_today": sales_today,
        "earnings_today": earnings_today,
        "sales_week": sales_week,
        "earnings_week": earnings_week,
        "sales_month": sales_month,
        "earnings_month": earnings_month,
        "top_plans": top_plans
    }

def get_all_users():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

def search_user(query: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    if query.isdigit():
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (int(query),))
    else:
        q = query.lstrip('@')
        cursor.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (q,))
    user = cursor.fetchone()
    conn.close()
    return user

def set_user_blocked(telegram_id: int, is_blocked: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_blocked = ? WHERE telegram_id = ?", (is_blocked, telegram_id))
    conn.commit()
    conn.close()

def update_balance(telegram_id: int, delta: float):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (delta, telegram_id))
    conn.commit()
    conn.close()

def create_promocode(code: str, discount_type: str, discount_value: float, uses_left: int, expires_at: datetime.datetime = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO promocodes (code, discount_type, discount_value, uses_left, expires_at) VALUES (?, ?, ?, ?, ?)",
            (code, discount_type, discount_value, uses_left, expires_at)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_promocode(code: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM promocodes WHERE code = ? COLLATE NOCASE", (code,))
    promocode = cursor.fetchone()
    conn.close()
    return promocode

def use_promocode(code: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = ? COLLATE NOCASE", (code,))
    conn.commit()
    conn.close()

def get_all_plans():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans")
    plans = cursor.fetchall()
    conn.close()

    # Return as dict matching old format {plan_id: {"name": ..., "days": ..., "price": ...}}
    result = {}
    for p in plans:
        result[p['plan_id']] = {
            "name": p['name'],
            "days": p['days'],
            "price": p['price']
        }
    return result

def get_plan(plan_id: str):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    plan = cursor.fetchone()
    conn.close()
    if plan:
        return {
            "name": plan['name'],
            "days": plan['days'],
            "price": plan['price']
        }
    return None

def update_plan_price(plan_id: str, new_price: float):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE plans SET price = ? WHERE plan_id = ?", (new_price, plan_id))
    conn.commit()
    conn.close()

def get_sales_graph_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    data = []

    # Get last 7 days
    for i in range(7):
        day = today - datetime.timedelta(days=i)
        next_day = day + datetime.timedelta(days=1)
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM sales WHERE created_at >= ? AND created_at < ?", (day, next_day))
        total = cursor.fetchone()[0]
        data.append({"date": day, "total": total})

    conn.close()
    return data

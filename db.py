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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            referrer_id INTEGER,
            rewarded BOOLEAN DEFAULT 0
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

def create_pending_payment(payment_id: str, telegram_id: int, plan_duration_days: int, target_telegram_id: int = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    created_at = datetime.datetime.now()
    cursor.execute(
        "INSERT INTO pending_payments (payment_id, telegram_id, plan_duration_days, created_at, target_telegram_id) VALUES (?, ?, ?, ?, ?)",
        (payment_id, telegram_id, plan_duration_days, created_at, target_telegram_id)
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

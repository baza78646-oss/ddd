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
    conn.commit()
    conn.close()

def create_user(telegram_id: int, sub_id: str, expires_at: datetime.datetime = None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    created_at = datetime.datetime.now()
    try:
        cursor.execute(
            "INSERT INTO users (telegram_id, sub_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (telegram_id, sub_id, created_at, expires_at)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass # User might already exist
    finally:
        conn.close()

def get_user(telegram_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

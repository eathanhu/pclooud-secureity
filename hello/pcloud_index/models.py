import sqlite3
import hashlib
import time
from config import DATABASE


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            browser TEXT,
            os TEXT,
            device TEXT,
            location TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            last_login REAL
        );

        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            browser TEXT,
            os TEXT,
            device TEXT,
            location TEXT,
            status TEXT DEFAULT 'blocked',
            reason TEXT,
            attempted_at REAL
        );
    """)
    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(email, password, ip, user_agent, browser, os_name, device, location):
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO users (email, password_hash, ip_address, user_agent,
               browser, os, device, location, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (email, hash_password(password), ip, user_agent,
             browser, os_name, device, location, time.time()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user(email):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return user


def approve_user(email):
    conn = get_db()
    conn.execute("UPDATE users SET status = 'approved' WHERE email = ?", (email,))
    conn.commit()
    conn.close()


def deny_user(email):
    conn = get_db()
    conn.execute("UPDATE users SET status = 'denied' WHERE email = ?", (email,))
    conn.commit()
    conn.close()


def update_user_login(email, ip, user_agent, browser, os_name, device, location):
    conn = get_db()
    conn.execute(
        """UPDATE users SET ip_address = ?, user_agent = ?, browser = ?,
           os = ?, device = ?, location = ?, last_login = ?
           WHERE email = ?""",
        (ip, user_agent, browser, os_name, device, location, time.time(), email),
    )
    conn.commit()
    conn.close()


def log_login_attempt(email, ip, user_agent, browser, os_name, device, location, status, reason):
    conn = get_db()
    conn.execute(
        """INSERT INTO login_attempts (email, ip_address, user_agent, browser,
           os, device, location, status, reason, attempted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (email, ip, user_agent, browser, os_name, device, location, status, reason, time.time()),
    )
    conn.commit()
    conn.close()


init_db()

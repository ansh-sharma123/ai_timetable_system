import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    conn.commit()
    conn.close()


def create_user(email, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    try:
        hashed = generate_password_hash(password)
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()


def check_user(email, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE email=?", (email,))
    user = c.fetchone()

    conn.close()
    # Verify password hash
    if user and check_password_hash(user[2], password):
        return user
    return None

def get_user_by_email(email):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE email=?", (email,))
    user = c.fetchone()

    conn.close()
    return user

def update_password(email, new_password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    try:
        hashed = generate_password_hash(new_password)
        c.execute("UPDATE users SET password=? WHERE email=?", (hashed, email))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()
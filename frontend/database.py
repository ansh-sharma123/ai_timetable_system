import sqlite3

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
        c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, password))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()


def check_user(email, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
    user = c.fetchone()

    conn.close()
    return user

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
        c.execute("UPDATE users SET password=? WHERE email=?", (new_password, email))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()
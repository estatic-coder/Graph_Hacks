import sqlite3
from config import load_config

def get_db_connection():
    config = load_config()
    conn = sqlite3.connect(config['db_path'])
    return conn

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

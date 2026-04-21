import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

DEFAULT_SUBJECTS = [
    "Português", "Matemática", "Ciências", "História",
    "Geografia", "Arte", "Educação Física", "Inglês",
]

def get_conn():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Erro crítico ao conectar no Supabase: {e}")
        return None

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
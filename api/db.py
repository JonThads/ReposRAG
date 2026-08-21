from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from .config import settings

@contextmanager
def get_conn():
    """Yield a psycopg connection with pgvector registered."""
    conn = psycopg.connect(settings.database_url, autocommit=True)
    try:
        register_vector(conn)
        yield conn
    finally:
        conn.close()

def check_db_health() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return True
    except Exception:
        return False
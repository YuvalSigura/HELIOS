import hashlib
import hmac
import os
import secrets
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

def database():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)

@contextmanager
def transaction():
    with database() as conn:
        with conn.transaction():
            yield conn

def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + "$" + digest.hex()

def password_valid(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False

def audit(conn, kind: str, actor_id: int | None, owner_org_id: int | None, details: dict):
    from psycopg.types.json import Jsonb
    conn.execute(
        "INSERT INTO audit_events(kind,actor_id,owner_org_id,details) VALUES(%s,%s,%s,%s)",
        (kind, actor_id, owner_org_id, Jsonb(details))
    )

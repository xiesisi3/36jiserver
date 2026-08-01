import uuid
import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS system_user (
                    id VARCHAR(32) PRIMARY KEY,
                    username VARCHAR(32) NOT NULL,
                    password VARCHAR(32) NOT NULL,
                    phone VARCHAR(16) DEFAULT '',
                    zt VARCHAR(4) DEFAULT '0'
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def get_all_users():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, username, password, phone, zt FROM system_user WHERE zt = '0'")
            return await cur.fetchall()


async def get_user_by_username(username):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, username, password, phone, zt FROM system_user WHERE username = %s AND zt = '0'",
                (username,)
            )
            return await cur.fetchone()


async def get_user_by_phone(phone):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, username, password, phone, zt FROM system_user WHERE phone = %s AND zt = '0'",
                (phone,)
            )
            return await cur.fetchone()


async def insert_user(username, password, phone):
    pool = get_pool()
    user_id = str(uuid.uuid4()).replace("-", "")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO system_user (id, username, password, phone, zt) VALUES (%s, %s, %s, %s, '0')",
                (user_id, username, password, phone)
            )
    return user_id
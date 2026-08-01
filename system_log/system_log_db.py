import uuid
import aiomysql
from core.database import get_pool


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS system_log_dic (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    type_name VARCHAR(32) NOT NULL,
                    type_father VARCHAR(32) DEFAULT ''
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS system_log (
                    id VARCHAR(32) PRIMARY KEY,
                    log_id INT NOT NULL,
                    user_id VARCHAR(32) DEFAULT '',
                    target_id VARCHAR(32) DEFAULT '',
                    zt VARCHAR(4) DEFAULT '0',
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")

    await _init_log_dic()


async def _init_log_dic():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM system_log_dic")
            row = await cur.fetchone()
            if row[0] == 0:
                await cur.execute(
                    "INSERT INTO system_log_dic (id, type_name, type_father) VALUES "
                    "(1, '登录', ''), (2, '注册', '')"
                )


async def insert_log(log_id, user_id, target_id, zt):
    pool = get_pool()
    log_id_str = str(uuid.uuid4()).replace("-", "")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO system_log (id, log_id, user_id, target_id, zt) VALUES (%s, %s, %s, %s, %s)",
                (log_id_str, log_id, user_id, target_id, zt)
            )


async def get_all_log_dic():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT id, type_name, type_father FROM system_log_dic")
            return await cur.fetchall()


async def query_logs_by_user(user_id, limit=100, offset=0):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT sl.id, sl.log_id, sld.type_name, sld.type_father, "
                "sl.create_time, sl.user_id, sl.target_id, sl.zt "
                "FROM system_log sl "
                "LEFT JOIN system_log_dic sld ON sl.log_id = sld.id "
                "WHERE sl.user_id = %s ORDER BY sl.create_time DESC LIMIT %s OFFSET %s",
                (user_id, limit, offset)
            )
            return await cur.fetchall()


async def query_logs_by_type(log_id, limit=100, offset=0):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT sl.id, sl.log_id, sld.type_name, sld.type_father, "
                "sl.create_time, sl.user_id, sl.target_id, sl.zt "
                "FROM system_log sl "
                "LEFT JOIN system_log_dic sld ON sl.log_id = sld.id "
                "WHERE sl.log_id = %s ORDER BY sl.create_time DESC LIMIT %s OFFSET %s",
                (log_id, limit, offset)
            )
            return await cur.fetchall()
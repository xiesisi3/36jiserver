import aiomysql
import json
from core.database import get_pool


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS fiefs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(32) NOT NULL,
                    town_id INT NOT NULL,
                    nation_id INT NOT NULL,
                    name VARCHAR(32) NOT NULL DEFAULT '',
                    grid_data JSON NOT NULL,
                    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_user_town (user_id, town_id),
                    INDEX idx_user_id (user_id),
                    INDEX idx_town_id (town_id),
                    INDEX idx_nation_id (nation_id)
                )
            """)
            try:
                await cur.execute("""
                    ALTER TABLE fiefs ADD COLUMN name VARCHAR(32) NOT NULL DEFAULT ''
                """)
            except Exception:
                pass
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS fief_troops (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    fief_id INT NOT NULL,
                    troop_name VARCHAR(32) NOT NULL,
                    count INT NOT NULL DEFAULT 0,
                    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE KEY uk_fief_troop (fief_id, troop_name),
                    INDEX idx_fief_id (fief_id)
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS fief_destroy_log (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
                    user_id VARCHAR(32) NOT NULL COMMENT '封地所属用户ID',
                    town_id INT NOT NULL COMMENT '封地所在城池ID',
                    nation_id INT NOT NULL COMMENT '封地所属国家ID',
                    fief_name VARCHAR(32) NOT NULL DEFAULT '' COMMENT '封地名称',
                    grid_data JSON NOT NULL COMMENT '封地建筑数据快照',
                    destroy_reason VARCHAR(64) NOT NULL DEFAULT '' COMMENT '摧毁原因',
                    destroy_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '摧毁时间',
                    INDEX idx_user_id (user_id),
                    INDEX idx_town_id (town_id)
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def get_all_fiefs():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM fiefs ORDER BY id")
            rows = await cur.fetchall()
            for row in rows:
                if isinstance(row["grid_data"], str):
                    row["grid_data"] = json.loads(row["grid_data"])
            return rows


async def get_all_fief_troops():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM fief_troops ORDER BY fief_id, troop_name")
            return await cur.fetchall()


async def insert_fief(user_id, town_id, nation_id, grid_data, name):
    pool = get_pool()
    grid_json = json.dumps(grid_data, ensure_ascii=False)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO fiefs (user_id, town_id, nation_id, grid_data, name) VALUES (%s, %s, %s, %s, %s)",
                (user_id, town_id, nation_id, grid_json, name)
            )
            return cur.lastrowid


async def update_fief_grid_data(fief_id, grid_data):
    pool = get_pool()
    grid_json = json.dumps(grid_data, ensure_ascii=False)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE fiefs SET grid_data = %s WHERE id = %s",
                (grid_json, fief_id)
            )


async def update_fief_name(fief_id, name):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE fiefs SET name = %s WHERE id = %s",
                (name, fief_id)
            )


async def delete_fief(fief_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM fiefs WHERE id = %s", (fief_id,))


async def upsert_fief_troop(fief_id, troop_name, count):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO fief_troops (fief_id, troop_name, count) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE count = %s",
                (fief_id, troop_name, count, count)
            )


async def delete_fief_troop(fief_id, troop_name):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM fief_troops WHERE fief_id = %s AND troop_name = %s",
                (fief_id, troop_name)
            )


async def delete_fief_troops(fief_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM fief_troops WHERE fief_id = %s", (fief_id,))


async def insert_fief_destroy_log(user_id, town_id, nation_id, fief_name, grid_data, destroy_reason):
    pool = get_pool()
    grid_json = json.dumps(grid_data, ensure_ascii=False)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO fief_destroy_log (user_id, town_id, nation_id, fief_name, grid_data, destroy_reason) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id, town_id, nation_id, fief_name, grid_json, destroy_reason)
            )
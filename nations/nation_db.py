import aiomysql
from core.database import get_pool


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS nations (
                    id INT PRIMARY KEY,
                    name VARCHAR(32) NOT NULL,
                    position VARCHAR(16) DEFAULT ''
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS user_nation (
                    id VARCHAR(32) PRIMARY KEY,
                    user_id VARCHAR(32) NOT NULL,
                    nation_id INT NOT NULL
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def truncate_nations():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE nations")


async def insert_nations(nations):
    pool = get_pool()
    sql = "INSERT INTO nations (id, name, position) VALUES (%s, %s, %s)"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, [
                (n["id"], n["name"], n["position"])
                for n in nations
            ])


async def get_all_nations():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM nations ORDER BY id")
            return await cur.fetchall()


async def get_nation_count():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM nations")
            row = await cur.fetchone()
            return row[0]


async def batch_update_town_owners(updates):
    pool = get_pool()
    sql = "UPDATE towns SET owner = %s WHERE id = %s"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, updates)


async def insert_user_nation(user_id, nation_id):
    import uuid
    pool = get_pool()
    nation_user_id = str(uuid.uuid4()).replace("-", "")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO user_nation (id, user_id, nation_id) VALUES (%s, %s, %s)",
                (nation_user_id, user_id, nation_id)
            )


async def get_all_user_nations():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM user_nation")
            return await cur.fetchall()
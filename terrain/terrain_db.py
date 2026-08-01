import aiomysql
from core.database import get_pool


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS mountains (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(32) NOT NULL,
                    cells TEXT NOT NULL,
                    vertices TEXT NOT NULL,
                    size VARCHAR(16) DEFAULT 'small'
                )
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS rivers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(32) NOT NULL,
                    segments TEXT NOT NULL
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def batch_insert_mountains(mountains):
    pool = get_pool()
    sql = "INSERT INTO mountains (name, cells, vertices, size) VALUES (%s, %s, %s, %s)"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, [
                (m["name"], m["cells"], m["vertices"], m["size"])
                for m in mountains
            ])


async def get_all_mountains():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM mountains ORDER BY id")
            return await cur.fetchall()


async def get_mountain_count():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM mountains")
            row = await cur.fetchone()
            return row[0]


async def truncate_mountains():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE mountains")


async def batch_insert_rivers(rivers):
    pool = get_pool()
    sql = "INSERT INTO rivers (name, segments) VALUES (%s, %s)"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, [
                (r["name"], r["segments"]) for r in rivers
            ])


async def get_all_rivers():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM rivers ORDER BY id")
            return await cur.fetchall()


async def get_river_count():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM rivers")
            row = await cur.fetchone()
            return row[0]


async def truncate_rivers():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE rivers")


async def update_mountain_vertices(mid, vertices_str):
    pool = get_pool()
    sql = "UPDATE mountains SET vertices = %s WHERE id = %s"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (vertices_str, mid))
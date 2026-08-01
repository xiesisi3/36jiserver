import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS roads (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    start_town_id INT NOT NULL,
                    end_town_id INT NOT NULL,
                    distance INT NOT NULL
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def batch_insert_roads(roads):
    pool = get_pool()
    sql = (
        "INSERT INTO roads (start_town_id, end_town_id, distance) "
        "VALUES (%s, %s, %s)"
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, [
                (r["start_town_id"], r["end_town_id"], r["distance"])
                for r in roads
            ])


async def truncate_roads():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("TRUNCATE TABLE roads")


async def get_all_roads():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM roads ORDER BY id")
            return await cur.fetchall()


async def get_road_count():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM roads")
            row = await cur.fetchone()
            return row[0]


async def get_roads_by_town(town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM roads WHERE start_town_id = %s OR end_town_id = %s",
                (town_id, town_id),
            )
            return await cur.fetchall()
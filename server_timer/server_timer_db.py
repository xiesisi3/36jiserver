import aiomysql
from core.database import get_pool

TIMER_ID = "00000000000000000000000000000001"


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS server_timer (
                    id VARCHAR(32) PRIMARY KEY,
                    uptime_ms BIGINT NOT NULL DEFAULT 0,
                    cycle_count INT NOT NULL DEFAULT 1,
                    last_start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def load_timer():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM server_timer WHERE id = %s", (TIMER_ID,))
            row = await cur.fetchone()
            if row is None:
                await cur.execute(
                    "INSERT INTO server_timer (id) VALUES (%s)",
                    (TIMER_ID,)
                )
                return {"id": TIMER_ID, "uptime_ms": 0, "cycle_count": 1}
            return dict(row)


async def save_timer(uptime_ms, cycle_count):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE server_timer SET uptime_ms = %s, cycle_count = %s WHERE id = %s",
                (uptime_ms, cycle_count, TIMER_ID)
            )
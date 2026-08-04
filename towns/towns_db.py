import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS towns (
                    id INT PRIMARY KEY,
                    pos_x INT NOT NULL,
                    pos_y INT NOT NULL,
                    name VARCHAR(32) NOT NULL,
                    name_rect_x INT DEFAULT 0,
                    name_rect_y INT DEFAULT 0,
                    name_rect_w INT DEFAULT 0,
                    name_rect_h INT DEFAULT 0,
                    owner INT DEFAULT 1,
                    level INT DEFAULT 1,
                    status INT DEFAULT 0,
                    forest DECIMAL(4,2) DEFAULT 0.00,
                    fertile DECIMAL(4,2) DEFAULT 0.00,
                    mine DECIMAL(4,2) DEFAULT 0.00,
                    stability INT DEFAULT 0,
                    defense INT DEFAULT 0,
                    traffic INT DEFAULT 0,
                    popular_support INT DEFAULT 0
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def batch_insert_towns(towns):
    pool = get_pool()
    sql = (
        "INSERT INTO towns "
        "(id, pos_x, pos_y, name, name_rect_x, name_rect_y, name_rect_w, name_rect_h, "
        "owner, level, status, forest, fertile, mine, stability, defense, traffic, popular_support) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, [
                (
                    t["id"], t["pos_x"], t["pos_y"], t["name"],
                    t["name_rect_x"], t["name_rect_y"], t["name_rect_w"], t["name_rect_h"],
                    t["owner"], t["level"], t["status"],
                    t["forest"], t["fertile"], t["mine"],
                    t["stability"], t["defense"], t["traffic"], t.get("popular_support", 0),
                )
                for t in towns
            ])


async def get_all_towns():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM towns ORDER BY id")
            return await cur.fetchall()


async def get_town_count():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM towns")
            row = await cur.fetchone()
            return row[0]


async def get_towns_in_viewport(x1, y1, x2, y2):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM towns WHERE pos_x >= %s AND pos_x <= %s "
                "AND pos_y >= %s AND pos_y <= %s ORDER BY id",
                (x1, x2, y1, y2)
            )
            return await cur.fetchall()


async def get_town_by_id(town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM towns WHERE id = %s", (town_id,))
            return await cur.fetchone()


async def batch_update_town_levels(updates):
    pool = get_pool()
    sql = (
        "UPDATE towns SET level = %s, forest = %s, fertile = %s, mine = %s, "
        "stability = %s, defense = %s, traffic = %s, popular_support = %s WHERE id = %s"
    )
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(sql, [
                (u["level"], u["forest"], u["fertile"], u["mine"],
                 u["stability"], u["defense"], u["traffic"], u.get("popular_support", 0), u["id"])
                for u in updates
            ])


async def update_town_status(town_id, status):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE towns SET status = %s WHERE id = %s",
                (status, town_id)
            )
            return cur.rowcount


async def update_town_owner(town_id, owner):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE towns SET owner = %s WHERE id = %s",
                (owner, town_id)
            )
            return cur.rowcount


async def update_town_attrs(town_id, updates):
    set_clauses = []
    values = []
    for key in ("stability", "defense", "traffic", "popular_support"):
        if key in updates:
            set_clauses.append(f"{key} = %s")
            values.append(updates[key])
    if not set_clauses:
        return 0
    values.append(town_id)
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE towns SET {', '.join(set_clauses)} WHERE id = %s",
                values
            )
            return cur.rowcount


async def update_town_popular_support(town_id, popular_support):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE towns SET popular_support = %s WHERE id = %s",
                (popular_support, town_id)
            )
            return cur.rowcount
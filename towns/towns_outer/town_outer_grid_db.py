import json
import aiomysql
from core.database import get_pool
from server_timer.server_timer_core import get_uptime_ms


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS town_outer_grid (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
                    town_id INT NOT NULL COMMENT '城池ID',
                    grid JSON NOT NULL COMMENT '19×19网格部队数据（JSON二维数组）',
                    create_time BIGINT DEFAULT NULL COMMENT '创建时间(毫秒时间戳)',
                    update_time BIGINT DEFAULT NULL COMMENT '更新时间(毫秒时间戳)',
                    UNIQUE KEY uk_town_id (town_id) COMMENT '城池ID唯一索引'
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='外城网格部队数据表'
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def get_all_grids():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM town_outer_grid ORDER BY id")
            rows = await cur.fetchall()
            for row in rows:
                if isinstance(row["grid"], str):
                    row["grid"] = json.loads(row["grid"])
            return rows


async def get_grid_by_town_id(town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_outer_grid WHERE town_id = %s",
                (town_id,)
            )
            row = await cur.fetchone()
            if row and isinstance(row["grid"], str):
                row["grid"] = json.loads(row["grid"])
            return row


async def insert_grid(data):
    pool = get_pool()
    now = get_uptime_ms()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO town_outer_grid (town_id, grid, create_time, update_time) "
                "VALUES (%s, %s, %s, %s)",
                (
                    data["town_id"],
                    json.dumps(data["grid"], ensure_ascii=False),
                    now,
                    now,
                )
            )
            return cur.lastrowid


async def update_grid(town_id, grid):
    pool = get_pool()
    now = get_uptime_ms()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE town_outer_grid SET grid = %s, update_time = %s WHERE town_id = %s",
                (json.dumps(grid, ensure_ascii=False), now, town_id)
            )


async def update_grid_cell(town_id, row, col, troop_ids, grid=None):
    """更新网格中指定单元格，并持久化整个grid到DB

    Args:
        town_id: 城池ID
        row, col: 单元格坐标
        troop_ids: 该单元格的部队ID列表
        grid: 可选，缓存中的完整grid对象。传入时跳过DB读取，直接使用缓存数据写回，
              消除读-改-写竞态窗口。不传时保持原有逻辑（从DB读取后修改再写回）。
    """
    if grid is None:
        row_data = await get_grid_by_town_id(town_id)
        if row_data is None:
            return
        grid = row_data["grid"]
    grid[row][col] = troop_ids
    await update_grid(town_id, grid)


async def get_grid_count():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) as cnt FROM town_outer_grid")
            row = await cur.fetchone()
            return row[0] if row else 0


async def delete_all_grids():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM town_outer_grid")


async def batch_insert_grids(grid_list):
    pool = get_pool()
    now = get_uptime_ms()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO town_outer_grid (town_id, grid, create_time, update_time) "
                "VALUES (%s, %s, %s, %s)",
                [
                    (
                        g["town_id"],
                        json.dumps(g["grid"], ensure_ascii=False),
                        now,
                        now,
                    )
                    for g in grid_list
                ]
            )
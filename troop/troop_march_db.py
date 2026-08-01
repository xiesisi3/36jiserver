# 行军持久化操作
# 更新部队状态为行军

import json
import logging

from core.database import get_pool
from server_timer.server_timer_core import get_uptime_ms

logger = logging.getLogger('36ji-server')


async def update_troop_march_status(troop_id, status, dest, dep_time, arrive_time, grid_x, grid_y):
    """更新部队行军状态"""
    pool = get_pool()
    now = get_uptime_ms()
    sql = """UPDATE troops SET status=%s, dest=%s, dep_time=%s, arrive_time=%s,
             grid_x=%s, grid_y=%s, update_time=%s WHERE id=%s"""
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (
                status, dest, dep_time, arrive_time, grid_x, grid_y,
                now, troop_id
            ))
            return cur.rowcount


async def update_troop_arrive_status(troop_id, status, grid_x, grid_y, pos=None, dest=None, conn=None):
    """更新部队到达状态（行军→驻守/战斗中）"""
    now = get_uptime_ms()
    sql = """UPDATE troops SET status=%s, grid_x=%s, grid_y=%s, pos=%s, dest=%s, update_time=%s WHERE id=%s"""
    if conn is not None:
        async with conn.cursor() as cur:
            await cur.execute(sql, (status, grid_x, grid_y, pos, dest, now, troop_id))
            return cur.rowcount
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (status, grid_x, grid_y, pos, dest, now, troop_id))
            return cur.rowcount


async def batch_update_troop_march_status(troop_updates, conn=None):
    """批量更新部队行军状态
    troop_updates: [(troop_id, status, dest, dep_time, arrive_time, grid_x, grid_y, food), ...]
    """
    if not troop_updates:
        return 0
    now = get_uptime_ms()
    sql = """UPDATE troops SET status=%s, dest=%s, dep_time=%s, arrive_time=%s,
             grid_x=%s, grid_y=%s, food=%s, update_time=%s WHERE id=%s"""
    if conn is not None:
        async with conn.cursor() as cur:
            total = 0
            for tid, status, dest, dep_time, arrive_time, grid_x, grid_y, food in troop_updates:
                row_count = await cur.execute(sql, (
                    status, dest, dep_time, arrive_time, grid_x, grid_y,
                    food, now, tid
                ))
                total += row_count
            return total
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            total = 0
            for tid, status, dest, dep_time, arrive_time, grid_x, grid_y, food in troop_updates:
                row_count = await cur.execute(sql, (
                    status, dest, dep_time, arrive_time, grid_x, grid_y,
                    food, now, tid
                ))
                total += row_count
            return total
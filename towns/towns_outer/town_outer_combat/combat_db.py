import json
import datetime
import aiomysql
from core.database import get_pool
from server_timer.server_timer_core import get_uptime_ms


def _json_default(obj):
    if isinstance(obj, datetime.datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, datetime.date):
        return obj.strftime("%Y-%m-%d")
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS town_combat_history (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
                    town_id INT NOT NULL COMMENT '城池ID',
                    start_time BIGINT DEFAULT 0 COMMENT '战斗开始时间(毫秒)',
                    end_time BIGINT DEFAULT 0 COMMENT '战斗结束时间(毫秒)',
                    winner INT DEFAULT NULL COMMENT '胜利方nation_id',
                    victory_type VARCHAR(32) DEFAULT NULL COMMENT '胜利类型: 占领/防御成功/全军覆没',
                    total_rounds INT DEFAULT 0 COMMENT '总回合数',
                    is_finished TINYINT DEFAULT 0 COMMENT '是否结束: 0=进行中, 1=已结束',
                    participants JSON DEFAULT NULL COMMENT '参战部队ID列表',
                    final_stats JSON DEFAULT NULL COMMENT '最终统计数据',
                    create_time BIGINT DEFAULT NULL COMMENT '创建时间(毫秒)',
                    INDEX idx_town_id (town_id),
                    INDEX idx_is_finished (is_finished)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='城池战斗历史记录主表'
            """)
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS town_combat_round (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
                    history_id INT DEFAULT NULL COMMENT '关联战斗历史记录ID',
                    town_id INT NOT NULL COMMENT '城池ID',
                    round_num INT NOT NULL COMMENT '回合编号',
                    state TINYINT DEFAULT 0 COMMENT '回合状态: 0=预加载, 1=已开始',
                    preload_start_ms BIGINT DEFAULT 0 COMMENT '预加载开始时间(毫秒)',
                    preload_end_ms BIGINT DEFAULT 0 COMMENT '预加载结束时间(毫秒)',
                    round_start_ms BIGINT DEFAULT 0 COMMENT '回合开始时间(毫秒)',
                    round_end_ms BIGINT DEFAULT 0 COMMENT '回合结束时间(毫秒)',
                    round_data JSON COMMENT '回合结束时的部队状态(用于中断恢复)',
                    initial_troops JSON COMMENT '回合开始时的部队初始兵力: {troop_id: total_soldiers, ...}',
                    create_time BIGINT DEFAULT NULL COMMENT '创建时间(毫秒)',
                    UNIQUE KEY uk_history_round (history_id, round_num),
                    INDEX idx_town_id (town_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='城池战斗回合记录表'
            """)
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS town_combat_general_kills (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
                    history_id INT NOT NULL COMMENT '关联战斗历史记录ID',
                    round_num INT NOT NULL COMMENT '回合编号',
                    general_id INT NOT NULL COMMENT '武将ID',
                    user_id VARCHAR(32) NOT NULL COMMENT '归属用户ID',
                    kills JSON NOT NULL COMMENT '消灭兵种统计: [{"兵种名称":"轻步兵","数量":10},...]',
                    losses JSON NOT NULL COMMENT '损失兵种统计: [{"兵种名称":"轻骑兵","数量":5},...]',
                    eliminated_troops JSON COMMENT '消灭的敌方部队ID列表: [troop_id, ...]',
                    create_time BIGINT DEFAULT NULL COMMENT '创建时间(毫秒)',
                    INDEX idx_history_id (history_id),
                    INDEX idx_general_id (general_id),
                    UNIQUE KEY uk_history_round_general (history_id, round_num, general_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='城池战斗武将消灭统计表'
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def insert_combat_history(data):
    pool = get_pool()
    now = get_uptime_ms()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO town_combat_history "
                "(town_id, start_time, end_time, winner, victory_type, total_rounds, "
                "is_finished, participants, final_stats, create_time) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    data["town_id"],
                    data.get("start_time", now),
                    data.get("end_time", 0),
                    data.get("winner"),
                    data.get("victory_type"),
                    data.get("total_rounds", 0),
                    data.get("is_finished", 0),
                    json.dumps(data.get("participants", []), ensure_ascii=False, default=_json_default),
                    json.dumps(data.get("final_stats", {}), ensure_ascii=False, default=_json_default),
                    now,
                )
            )
            return cur.lastrowid


async def update_combat_history(history_id, updates):
    if not updates:
        return 0
    pool = get_pool()
    set_str = ", ".join([f"`{k}` = %s" for k in updates.keys()])
    sql = f"UPDATE town_combat_history SET {set_str} WHERE id = %s"
    values = []
    for k in updates.keys():
        v = updates[k]
        if k in ("participants", "final_stats") and isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False, default=_json_default)
        values.append(v)
    values.append(history_id)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            return await cur.execute(sql, values)


async def get_combat_history(history_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM town_combat_history WHERE id = %s", (history_id,))
            row = await cur.fetchone()
            if row:
                for field in ("participants", "final_stats"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
            return row


async def get_combat_rounds_by_town(town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_combat_round WHERE town_id = %s ORDER BY round_num",
                (town_id,)
            )
            rows = await cur.fetchall()
            for row in rows:
                for field in ("round_data", "initial_troops"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
            return rows


async def get_combat_round_by_history(history_id, round_num):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_combat_round WHERE history_id = %s AND round_num = %s",
                (history_id, round_num)
            )
            row = await cur.fetchone()
            if row:
                for field in ("round_data", "initial_troops"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
            return row


async def get_unfinished_combat_histories():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_combat_history WHERE is_finished = 0"
            )
            rows = await cur.fetchall()
            for row in rows:
                for field in ("participants", "final_stats"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
            return rows


async def get_last_combat_round(town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_combat_round WHERE town_id = %s ORDER BY round_num DESC LIMIT 1",
                (town_id,)
            )
            row = await cur.fetchone()
            if row and isinstance(row.get("round_data"), str):
                row["round_data"] = json.loads(row["round_data"])
            return row


async def insert_combat_round(data):
    pool = get_pool()
    now = get_uptime_ms()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO town_combat_round "
                "(history_id, town_id, round_num, state, preload_start_ms, preload_end_ms, "
                "round_start_ms, round_end_ms, round_data, initial_troops, create_time) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    data.get("history_id"),
                    data["town_id"],
                    data["round_num"],
                    data.get("state", 0),
                    data.get("preload_start_ms", 0),
                    data.get("preload_end_ms", 0),
                    data.get("round_start_ms", 0),
                    data.get("round_end_ms", 0),
                    json.dumps(data.get("round_data", {}), ensure_ascii=False, default=_json_default),
                    json.dumps(data.get("initial_troops", {}), ensure_ascii=False, default=_json_default),
                    now,
                )
            )
            return cur.lastrowid


async def update_combat_round(history_id, round_num, updates):
    if not updates:
        return 0
    pool = get_pool()
    set_str = ", ".join([f"`{k}` = %s" for k in updates.keys()])
    sql = f"UPDATE town_combat_round SET {set_str} WHERE history_id = %s AND round_num = %s"
    values = []
    for k in updates.keys():
        v = updates[k]
        if k in ("round_data", "initial_troops") and isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False, default=_json_default)
        values.append(v)
    values.extend([history_id, round_num])
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            return await cur.execute(sql, values)


async def delete_combat_rounds_by_town(town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM town_combat_round WHERE town_id = %s", (town_id,))


async def insert_general_kills(kills_list):
    pool = get_pool()
    now = get_uptime_ms()
    total = 0
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for k in kills_list:
                await cur.execute(
                    "INSERT INTO town_combat_general_kills "
                    "(history_id, round_num, general_id, user_id, kills, losses, eliminated_troops, create_time) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE "
                    "kills = VALUES(kills), losses = VALUES(losses), "
                    "eliminated_troops = VALUES(eliminated_troops), create_time = VALUES(create_time)",
                    (
                        k["history_id"],
                        k["round_num"],
                        k["general_id"],
                        k["user_id"],
                        json.dumps(k["kills"], ensure_ascii=False, default=_json_default),
                        json.dumps(k.get("losses", []), ensure_ascii=False, default=_json_default),
                        json.dumps(k.get("eliminated_troops", []), ensure_ascii=False, default=_json_default),
                        now,
                    )
                )
                total += 1
    return total


async def get_general_kills_by_history(history_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_combat_general_kills WHERE history_id = %s ORDER BY round_num, general_id",
                (history_id,)
            )
            rows = await cur.fetchall()
            for row in rows:
                for field in ("kills", "losses", "eliminated_troops"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
            return rows


async def delete_general_kills_by_history(history_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM town_combat_general_kills WHERE history_id = %s", (history_id,))


async def get_all_combat_rounds_by_history(history_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM town_combat_round WHERE history_id = %s ORDER BY round_num",
                (history_id,)
            )
            rows = await cur.fetchall()
            for row in rows:
                for field in ("round_data", "initial_troops"):
                    if isinstance(row.get(field), str):
                        row[field] = json.loads(row[field])
            return rows


async def insert_player_stats(stats_list):
    pass


async def delete_player_stats_by_town(town_id):
    pass
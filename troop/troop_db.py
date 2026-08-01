import aiomysql
import json
from core.database import get_pool
from server_timer.server_timer_core import get_uptime_ms


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS troops (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
                    user_id VARCHAR(32) NOT NULL COMMENT '归属用户ID',
                    general_id INT NOT NULL COMMENT '武将ID',
                    team JSON NOT NULL COMMENT '部队阵容JSON字符串',
                    food INT DEFAULT 0 COMMENT '携带粮食',
                    status TINYINT DEFAULT 1 COMMENT '1-驻守 2-行军中 3-战斗中 4-死亡等待复活',
                    pos INT DEFAULT NULL COMMENT '当前所在城池ID（驻守时有效）',
                    dest INT DEFAULT NULL COMMENT '目标城池ID（行军时有效）',
                    dep_time BIGINT DEFAULT NULL COMMENT '出发时间（服务器运行时长，毫秒）',
                    arrive_time BIGINT DEFAULT NULL COMMENT '预计到达时间（服务器运行时长，毫秒）',
                    grid_x INT DEFAULT NULL COMMENT '驻守时的网格X坐标（0-18）',
                    grid_y INT DEFAULT NULL COMMENT '驻守时的网格Y坐标（0-18）',
                    target_type VARCHAR(32) DEFAULT 'nearest' COMMENT '目标选择类型: nearest-最近, highest_attack-最高攻击, lowest_attack-最低攻击, most_food-最大粮食, most_troops-最多兵力, fewest_troops-最少兵力',
                    create_time BIGINT DEFAULT NULL COMMENT '创建时间（服务器运行时长，毫秒）',
                    update_time BIGINT DEFAULT NULL COMMENT '更新时间（服务器运行时长，毫秒）',
                    INDEX idx_user_id (user_id),
                    INDEX idx_pos (pos),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='部队主表'
            """)
            await cur.execute("SET SESSION sql_notes = 0")
            try:
                await cur.execute("ALTER TABLE troops DROP INDEX uk_general_id")
            except Exception:
                pass
            await cur.execute("SET SESSION sql_notes = 0")
            try:
                await cur.execute("ALTER TABLE troops ADD COLUMN target_type VARCHAR(32) DEFAULT 'nearest' COMMENT '目标选择类型: nearest-最近, highest_attack-最高攻击, lowest_attack-最低攻击, most_food-最大粮食, most_troops-最多兵力, fewest_troops-最少兵力'")
            except Exception:
                pass
            await cur.execute("SET SESSION sql_notes = 1")


async def get_all_troops():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM troops ORDER BY id")
            rows = await cur.fetchall()
            for row in rows:
                if isinstance(row["team"], str):
                    row["team"] = json.loads(row["team"])
            return rows


async def get_troop_by_id(troop_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM troops WHERE id = %s", (troop_id,))
            row = await cur.fetchone()
            if row and isinstance(row["team"], str):
                row["team"] = json.loads(row["team"])
            return row


async def get_troop_by_general_id(general_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM troops WHERE general_id = %s", (general_id,))
            row = await cur.fetchone()
            if row and isinstance(row["team"], str):
                row["team"] = json.loads(row["team"])
            return row


async def insert_troop(data):
    pool = get_pool()
    now = get_uptime_ms()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO troops (user_id, general_id, team, food, status, pos, dest, "
                "dep_time, arrive_time, grid_x, grid_y, target_type, create_time, update_time) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    data["user_id"],
                    data["general_id"],
                    json.dumps(data["team"], ensure_ascii=False),
                    data.get("food", 0),
                    data.get("status", 1),
                    data.get("pos"),
                    data.get("dest"),
                    data.get("dep_time", 0),
                    data.get("arrive_time", 0),
                    data.get("grid_x", 10),
                    data.get("grid_y", 9),
                    data.get("target_type", "nearest"),
                    now,
                    now,
                )
            )
            return cur.lastrowid


async def update_troop(troop_id, updates):
    if not updates:
        return 0
    pool = get_pool()
    now = get_uptime_ms()
    updates["update_time"] = now
    set_str = ", ".join([f"`{k}`=%s" for k in updates.keys()])
    sql = f"UPDATE troops SET {set_str} WHERE id = %s"
    values = []
    for k in updates.keys():
        v = updates[k]
        if k == "team" and isinstance(v, list):
            v = json.dumps(v, ensure_ascii=False)
        values.append(v)
    values.append(troop_id)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            row_count = await cur.execute(sql, values)
            return row_count


async def delete_troop(troop_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM troops WHERE id = %s", (troop_id,))
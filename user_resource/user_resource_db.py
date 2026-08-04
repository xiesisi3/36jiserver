import uuid
import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS user_resource (
                    id VARCHAR(32) PRIMARY KEY,
                    user_id VARCHAR(32) NOT NULL UNIQUE,
                    player_name VARCHAR(32) NOT NULL DEFAULT '',
                    avatar_small VARCHAR(255) NOT NULL DEFAULT 'resources/img/player/玩家.png',
                    avatar_large VARCHAR(255) NOT NULL DEFAULT 'resources/img/player/大明.png',
                    official_position VARCHAR(32) NOT NULL DEFAULT '平民',
                    gold BIGINT NOT NULL DEFAULT 10000,
                    prestige_level INT NOT NULL DEFAULT 1,
                    merit BIGINT NOT NULL DEFAULT 0,
                    nation_contribution BIGINT NOT NULL DEFAULT 0,
                    copper BIGINT NOT NULL DEFAULT 1000,
                    wood BIGINT NOT NULL DEFAULT 30000,
                    grain BIGINT NOT NULL DEFAULT 20000,
                    iron BIGINT NOT NULL DEFAULT 10000,
                    red_iron BIGINT NOT NULL DEFAULT 0 COMMENT '赤铁（强化神兵材料）',
                    books BIGINT NOT NULL DEFAULT 0 COMMENT '书籍（强化宝典材料）',
                    flint BIGINT NOT NULL DEFAULT 0 COMMENT '燧石（强化神器材料）',
                    road_repair_score BIGINT NOT NULL DEFAULT 0 COMMENT '修路分',
                    wall_repair_score BIGINT NOT NULL DEFAULT 0 COMMENT '修墙分',
                    robber_score BIGINT NOT NULL DEFAULT 0 COMMENT '剿匪分',
                    personal_combat_score BIGINT NOT NULL DEFAULT 0 COMMENT '个人战斗积分',
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def get_all_user_resources():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM user_resource")
            return await cur.fetchall()


async def get_user_resource_by_user_id(user_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM user_resource WHERE user_id = %s",
                (user_id,)
            )
            return await cur.fetchone()


async def get_user_resource_by_player_name(player_name):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM user_resource WHERE player_name = %s",
                (player_name,)
            )
            return await cur.fetchone()


async def insert_user_resource(user_id):
    pool = get_pool()
    resource_id = str(uuid.uuid4()).replace("-", "")
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO user_resource (id, user_id, wood, grain, iron) VALUES (%s, %s, 30000, 20000, 10000)",
                (resource_id, user_id)
            )
    return resource_id


async def update_player_name(user_id, player_name):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE user_resource SET player_name = %s WHERE user_id = %s",
                (player_name, user_id)
            )


async def update_user_resource_field(user_id, field_name, value, conn=None):
    """更新用户资源表的单个字段（如 copper、gold 等）
    field_name: 字段名（仅允许白名单字段，防止 SQL 注入）
    """
    allowed_fields = {"copper", "gold", "wood", "grain", "iron", "merit", "nation_contribution", "red_iron", "books", "flint", "road_repair_score", "wall_repair_score", "robber_score"}
    if field_name not in allowed_fields:
        raise ValueError(f"不允许更新的字段: {field_name}")

    if conn is not None:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE user_resource SET `{field_name}` = %s WHERE user_id = %s",
                (value, user_id)
            )
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE user_resource SET `{field_name}` = %s WHERE user_id = %s",
                (value, user_id)
            )


async def update_user_resource(user_id, updates):
    """批量更新用户资源表多个字段，一次 SQL 完成
    updates: {"wood": 100, "grain": 200, ...}
    """
    if not updates:
        return
    set_str = ", ".join([f"`{k}`=%s" for k in updates.keys()])
    sql = f"UPDATE user_resource SET {set_str} WHERE user_id = %s"
    values = list(updates.values()) + [user_id]
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)


async def batch_update_user_resources(user_updates, chunk_size=200):
    """批量更新多个用户的资源，每次 chunk_size 个用户拼接一条 SQL
    user_updates: {user_id: {"wood": 100, "grain": 200, "iron": 50, "copper": 500}, ...}
    """
    if not user_updates:
        return

    items = list(user_updates.items())
    all_resource_fields = ["wood", "grain", "iron", "copper", "red_iron", "books", "flint"]
    active_fields = []
    for field in all_resource_fields:
        for _, res in items:
            if field in res:
                active_fields.append(field)
                break
    if not active_fields:
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for i in range(0, len(items), chunk_size):
                chunk = items[i:i + chunk_size]
                user_ids = [uid for uid, _ in chunk]

                case_parts = []
                for field in active_fields:
                    when_parts = []
                    for uid, res in chunk:
                        when_parts.append("WHEN %s THEN %s")
                    case_parts.append(
                        f"`{field}` = CASE user_id {' '.join(when_parts)} END"
                    )

                set_clause = ", ".join(case_parts)
                placeholders = ", ".join(["%s"] * len(user_ids))
                sql = f"UPDATE user_resource SET {set_clause} WHERE user_id IN ({placeholders})"

                params = []
                for field in active_fields:
                    for uid, res in chunk:
                        params.append(uid)
                        params.append(res.get(field, 0))
                params.extend(user_ids)

                await cur.execute(sql, params)
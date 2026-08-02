import aiomysql
from core.database import get_pool


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS legions (
                    id                    INT AUTO_INCREMENT PRIMARY KEY COMMENT '军团唯一ID',
                    nation_id             INT          NOT NULL COMMENT '所属国家ID',
                    name                  VARCHAR(50)  NOT NULL COMMENT '军团名称',
                    description           VARCHAR(200) NOT NULL DEFAULT '' COMMENT '军团简介',
                    total_combat_score    BIGINT       NOT NULL DEFAULT 0 COMMENT '总战斗积分',
                    available_combat_score BIGINT      NOT NULL DEFAULT 0 COMMENT '当前可用战斗积分',
                    granary_max           BIGINT       NOT NULL DEFAULT 100000 COMMENT '军团粮仓上限',
                    granary_current       BIGINT       NOT NULL DEFAULT 0 COMMENT '军团当前粮仓存储量',
                    create_time           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    UNIQUE KEY uk_name (name),
                    INDEX idx_nation (nation_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='军团表'
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS legion_members (
                    id                    INT AUTO_INCREMENT PRIMARY KEY COMMENT '记录唯一ID',
                    legion_id             INT          NOT NULL COMMENT '所属军团ID',
                    user_id               VARCHAR(32)  NOT NULL COMMENT '玩家ID',
                    role                  TINYINT      NOT NULL DEFAULT 3 COMMENT '军团职务: 1=军团长 2=副军团长 3=普通成员',
                    personal_granary      BIGINT       NOT NULL DEFAULT 0 COMMENT '个人粮仓存储量',
                    personal_total_score  BIGINT       NOT NULL DEFAULT 0 COMMENT '个人总积分',
                    personal_current_score BIGINT      NOT NULL DEFAULT 0 COMMENT '个人当前积分',
                    join_time             TIMESTAMP    DEFAULT CURRENT_TIMESTAMP COMMENT '加入时间',
                    UNIQUE KEY uk_user (user_id),
                    INDEX idx_legion (legion_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='军团玩家归属表'
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS legion_applications (
                    id            INT AUTO_INCREMENT PRIMARY KEY COMMENT '申请记录唯一ID',
                    legion_id     INT          NOT NULL COMMENT '申请的军团ID',
                    user_id       VARCHAR(32)  NOT NULL COMMENT '申请人ID',
                    status        TINYINT      NOT NULL DEFAULT 0 COMMENT '0=待处理 1=已同意 2=已拒绝',
                    create_time   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP COMMENT '申请时间',
                    update_time   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '处理时间',
                    UNIQUE KEY uk_user_legion (user_id, legion_id),
                    INDEX idx_legion_status (legion_id, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='军团申请记录表'
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS fief_item_effects (
                    id          INT AUTO_INCREMENT PRIMARY KEY COMMENT '记录唯一ID',
                    user_id     VARCHAR(32)    NOT NULL COMMENT '玩家ID',
                    town_id     INT            NOT NULL COMMENT '城池ID',
                    item_name   VARCHAR(32)    NOT NULL COMMENT '道具名称(土灵珠/水灵珠)',
                    bonus       DECIMAL(4,2)   NOT NULL COMMENT '资源加成值',
                    create_time TIMESTAMP      DEFAULT CURRENT_TIMESTAMP COMMENT '使用时间',
                    UNIQUE KEY uk_user_town (user_id, town_id),
                    INDEX idx_user_id (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='封地灵珠效果表'
            """)
            # 为已有数据库增加军团兑换阶段字段（兼容旧表）
            alter_columns = [
                ("legions", "granary_stage", "INT NOT NULL DEFAULT 0 COMMENT '粮仓扩展阶段 0-9'"),
                ("legions", "chest_ticket_stage", "INT NOT NULL DEFAULT 0 COMMENT '宝箱货票解锁阶段 0-8'"),
                ("legions", "buff_stage", "INT NOT NULL DEFAULT 0 COMMENT '加成类道具解锁阶段 0-4'"),
                ("legions", "special_stage", "INT NOT NULL DEFAULT 0 COMMENT '特殊道具解锁阶段 0-4'"),
            ]
            for table, col, definition in alter_columns:
                try:
                    await cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
                except Exception:
                    pass
            await cur.execute("SET SESSION sql_notes = 1")


# ==================== 军团表 CRUD ====================


async def get_all_legions():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM legions")
            return await cur.fetchall()


async def get_legion_by_id(legion_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM legions WHERE id = %s", (legion_id,))
            return await cur.fetchone()


async def get_legion_by_name(name):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM legions WHERE name = %s", (name,))
            return await cur.fetchone()


async def insert_legion(data):
    pool = get_pool()
    fields = ["nation_id", "name", "description"]
    placeholders = ", ".join(["%s"] * len(fields))
    field_str = ", ".join(fields)
    sql = f"INSERT INTO legions ({field_str}) VALUES ({placeholders})"
    values = [data.get(f) for f in fields]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
            return cur.lastrowid


async def update_legion_field(legion_id, field_name, value):
    allowed_fields = {
        "total_combat_score", "available_combat_score",
        "granary_max", "granary_current",
        "granary_stage", "chest_ticket_stage", "buff_stage", "special_stage",
    }
    if field_name not in allowed_fields:
        raise ValueError(f"不允许更新的字段: {field_name}")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE legions SET `{field_name}` = %s WHERE id = %s",
                (value, legion_id)
            )


# ==================== 军团成员表 CRUD ====================


async def get_all_legion_members():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM legion_members")
            return await cur.fetchall()


async def get_member_by_user(user_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM legion_members WHERE user_id = %s",
                (user_id,)
            )
            return await cur.fetchone()


async def get_members_by_legion(legion_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM legion_members WHERE legion_id = %s",
                (legion_id,)
            )
            return await cur.fetchall()


async def insert_legion_member(data):
    pool = get_pool()
    fields = ["legion_id", "user_id", "role"]
    placeholders = ", ".join(["%s"] * len(fields))
    field_str = ", ".join(fields)
    sql = f"INSERT INTO legion_members ({field_str}) VALUES ({placeholders})"
    values = [data.get(f) for f in fields]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
            return cur.lastrowid


async def update_member_role(user_id, role):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE legion_members SET role = %s WHERE user_id = %s",
                (role, user_id)
            )


async def update_member_field(user_id, field_name, value):
    allowed_fields = {
        "personal_granary", "personal_total_score", "personal_current_score",
    }
    if field_name not in allowed_fields:
        raise ValueError(f"不允许更新的字段: {field_name}")
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE legion_members SET `{field_name}` = %s WHERE user_id = %s",
                (value, user_id)
            )


async def delete_member(user_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM legion_members WHERE user_id = %s",
                (user_id,)
            )


# ==================== 军团申请表 CRUD ====================


async def get_application(legion_id, user_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM legion_applications WHERE legion_id = %s AND user_id = %s",
                (legion_id, user_id)
            )
            return await cur.fetchone()


async def upsert_application(legion_id, user_id, status):
    """插入或更新申请记录（重新申请时更新status和create_time）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO legion_applications (legion_id, user_id, status)
                   VALUES (%s, %s, %s)
                   ON DUPLICATE KEY UPDATE status = %s, create_time = CURRENT_TIMESTAMP""",
                (legion_id, user_id, status, status)
            )


async def update_application_status(legion_id, user_id, status):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE legion_applications SET status = %s WHERE legion_id = %s AND user_id = %s",
                (status, legion_id, user_id)
            )


async def get_pending_applications(legion_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM legion_applications WHERE legion_id = %s AND status = 0",
                (legion_id,)
            )
            return await cur.fetchall()


# ==================== 封地灵珠效果表 CRUD ====================


async def get_all_fief_item_effects():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM fief_item_effects")
            return await cur.fetchall()


async def get_fief_item_effect(user_id, town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM fief_item_effects WHERE user_id = %s AND town_id = %s",
                (user_id, town_id)
            )
            return await cur.fetchone()


async def upsert_fief_item_effect(user_id, town_id, item_name, bonus):
    """插入或更新灵珠效果（水灵珠覆盖土灵珠）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO fief_item_effects (user_id, town_id, item_name, bonus)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE item_name = %s, bonus = %s""",
                (user_id, town_id, item_name, bonus, item_name, bonus)
            )


async def delete_fief_item_effect(user_id, town_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM fief_item_effects WHERE user_id = %s AND town_id = %s",
                (user_id, town_id)
            )
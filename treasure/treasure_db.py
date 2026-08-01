import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS treasures (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '宝物唯一ID',
                    user_id VARCHAR(32) NOT NULL COMMENT '归属用户ID',
                    treasure_name VARCHAR(50) NOT NULL COMMENT '宝物名称',
                    treasure_type VARCHAR(10) NOT NULL COMMENT '宝物类型：神兵/宝典/神器',
                    level INT NOT NULL DEFAULT 1 COMMENT '需求等级',
                    enhance INT NOT NULL DEFAULT 0 COMMENT '强化等级',
                    `force` INT NOT NULL DEFAULT 0 COMMENT '武力加成',
                    intelligence INT NOT NULL DEFAULT 0 COMMENT '智力加成',
                    charisma INT NOT NULL DEFAULT 0 COMMENT '魅力加成',
                    infantry INT NOT NULL DEFAULT 0 COMMENT '步兵加成',
                    cavalry INT NOT NULL DEFAULT 0 COMMENT '骑兵加成',
                    archer INT NOT NULL DEFAULT 0 COMMENT '弓兵加成',
                    governance INT NOT NULL DEFAULT 0 COMMENT '内政加成',
                    wisdom INT NOT NULL DEFAULT 0 COMMENT '悟性加成',
                    star_level INT NOT NULL DEFAULT 0 COMMENT '星等：0=无星 1=一星 2=二星 3=三星',
                    star_force INT NOT NULL DEFAULT 0 COMMENT '星等武力加成',
                    star_intelligence INT NOT NULL DEFAULT 0 COMMENT '星等智力加成',
                    star_charisma INT NOT NULL DEFAULT 0 COMMENT '星等魅力加成',
                    star_wisdom INT NOT NULL DEFAULT 0 COMMENT '星等悟性加成',
                    star_infantry INT NOT NULL DEFAULT 0 COMMENT '星等步兵加成',
                    star_cavalry INT NOT NULL DEFAULT 0 COMMENT '星等骑兵加成',
                    star_archer INT NOT NULL DEFAULT 0 COMMENT '星等弓兵加成',
                    star_governance INT NOT NULL DEFAULT 0 COMMENT '星等内政加成',
                    combo_rate FLOAT NOT NULL DEFAULT 0.0 COMMENT '连击率（含星等加成）',
                    exclusive VARCHAR(50) NOT NULL DEFAULT '' COMMENT '专属英雄名称',
                    icon_path VARCHAR(255) NOT NULL DEFAULT '' COMMENT '图标路径',
                    is_equipped TINYINT NOT NULL DEFAULT 0 COMMENT '是否装备中：0未装备 1已装备',
                    general_id INT DEFAULT NULL COMMENT '装备的武将ID（NULL=未装备）',
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    INDEX idx_user_id (user_id),
                    INDEX idx_general_id (general_id),
                    INDEX idx_is_equipped (is_equipped)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宝物表'
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def insert_treasure(data):
    """插入宝物记录，返回自增ID"""
    pool = get_pool()
    fields = [
        "user_id", "treasure_name", "treasure_type", "level", "enhance",
        "force", "intelligence", "charisma",
        "infantry", "cavalry", "archer", "governance", "wisdom",
        "star_level", "star_force", "star_intelligence", "star_charisma",
        "star_wisdom", "star_infantry", "star_cavalry", "star_archer", "star_governance",
        "combo_rate",
        "exclusive", "icon_path", "is_equipped", "general_id",
    ]
    placeholders = ", ".join(["%s"] * len(fields))
    field_str = ", ".join([f"`{f}`" for f in fields])
    sql = f"INSERT INTO treasures ({field_str}) VALUES ({placeholders})"
    values = [data.get(f, None) for f in fields]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
            return cur.lastrowid


async def get_treasure_by_id(treasure_id):
    """根据宝物ID查询单条记录"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM treasures WHERE id = %s", (treasure_id,))
            return await cur.fetchone()


async def get_treasures_by_user(user_id):
    """根据用户ID查询所有宝物"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM treasures WHERE user_id = %s ORDER BY id ASC",
                (user_id,)
            )
            return await cur.fetchall()


async def update_treasure(treasure_id, updates, conn=None):
    """更新宝物字段"""
    if not updates:
        return 0
    set_str = ", ".join([f"`{k}`=%s" for k in updates.keys()])
    sql = f"UPDATE treasures SET {set_str} WHERE id = %s"
    values = list(updates.values()) + [treasure_id]
    if conn is not None:
        async with conn.cursor() as cur:
            row_count = await cur.execute(sql, values)
            return row_count
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            row_count = await cur.execute(sql, values)
            return row_count


async def get_all_treasures():
    """获取全量宝物数据（用于启动时加载缓存）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM treasures")
            return await cur.fetchall()


async def delete_treasure(treasure_id, conn=None):
    """删除宝物记录"""
    if conn is not None:
        async with conn.cursor() as cur:
            return await cur.execute("DELETE FROM treasures WHERE id = %s", (treasure_id,))
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            return await cur.execute("DELETE FROM treasures WHERE id = %s", (treasure_id,))
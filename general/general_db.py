import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS generals (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '武将唯一ID',
                    user_id VARCHAR(32) NOT NULL COMMENT '归属用户ID',
                    hero_name VARCHAR(50) NOT NULL COMMENT '英雄名称',
                    level_initial INT NOT NULL DEFAULT 1 COMMENT '等级（初始）',
                    level INT NOT NULL DEFAULT 1 COMMENT '当前等级',
                    force_initial INT NOT NULL DEFAULT 0 COMMENT '武力（初始）',
                    intelligence_initial INT NOT NULL DEFAULT 0 COMMENT '智力（初始）',
                    charisma_initial INT NOT NULL DEFAULT 0 COMMENT '魅力（初始）',
                    `force` INT NOT NULL DEFAULT 0 COMMENT '当前武力',
                    intelligence INT NOT NULL DEFAULT 0 COMMENT '当前智力',
                    charisma INT NOT NULL DEFAULT 0 COMMENT '当前魅力',
                    infantry_phase_initial TINYINT NOT NULL DEFAULT 0 COMMENT '步兵相性（初始）',
                    cavalry_phase_initial TINYINT NOT NULL DEFAULT 0 COMMENT '骑兵相性（初始）',
                    archer_phase_initial TINYINT NOT NULL DEFAULT 0 COMMENT '弓兵相性（初始）',
                    governance_phase_initial TINYINT NOT NULL DEFAULT 0 COMMENT '内政相性（初始）',
                    infantry_phase TINYINT NOT NULL DEFAULT 0 COMMENT '当前步兵相性',
                    cavalry_phase TINYINT NOT NULL DEFAULT 0 COMMENT '当前骑兵相性',
                    archer_phase TINYINT NOT NULL DEFAULT 0 COMMENT '当前弓兵相性',
                    governance_phase TINYINT NOT NULL DEFAULT 0 COMMENT '当前内政相性',
                    morale INT NOT NULL DEFAULT 100 COMMENT '士气',
                    personality VARCHAR(30) DEFAULT NULL COMMENT '性格',
                    wisdom INT NOT NULL DEFAULT 0 COMMENT '悟性',
                    exp INT NOT NULL DEFAULT 0 COMMENT '当前经验',
                    skill_points INT NOT NULL DEFAULT 0 COMMENT '剩余技能点',
                    talent_ygzq INT NOT NULL DEFAULT 0 COMMENT '天赋-一鼓作气',
                    talent_ygsj INT NOT NULL DEFAULT 0 COMMENT '天赋-勇冠三军',
                    talent_djzc INT NOT NULL DEFAULT 0 COMMENT '天赋-大将之材',
                    talent_tqtb INT NOT NULL DEFAULT 0 COMMENT '天赋-铜墙铁壁',
                    talent_skill INT NOT NULL DEFAULT 0 COMMENT '天赋-剩余技能点',
                    exp_bonus FLOAT NOT NULL DEFAULT 0.0 COMMENT '经验加成',
                    attack_bonus FLOAT NOT NULL DEFAULT 0.0 COMMENT '攻击加成',
                    defense_bonus FLOAT NOT NULL DEFAULT 0.0 COMMENT '防御加成',
                    hp_bonus FLOAT NOT NULL DEFAULT 0.0 COMMENT '血量加成',
                    morale_bonus FLOAT NOT NULL DEFAULT 0.0 COMMENT '士气加成',
                    combo_rate FLOAT NOT NULL DEFAULT 0.0 COMMENT '连击率（装备宝物+星等累积）',
                    skill_name VARCHAR(100) DEFAULT NULL COMMENT '技能名称',
                    skill_desc VARCHAR(500) DEFAULT NULL COMMENT '技能说明',
                    status TINYINT NOT NULL DEFAULT 0 COMMENT '状态：0未编组 1驻守 2行军 3战斗 4死亡',
                    pos INT DEFAULT NULL COMMENT '所处位置(城池ID)',
                    dest INT DEFAULT NULL COMMENT '目的地(城池ID)',
                    death_time BIGINT DEFAULT NULL COMMENT '阵亡时间(毫秒时间戳)',
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    INDEX idx_user_id (user_id),
                    INDEX idx_status (status),
                    INDEX idx_pos (pos)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='武将信息表'
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def insert_general(data):
    pool = get_pool()
    fields = [
        "user_id", "hero_name", "level_initial", "level",
        "force_initial", "intelligence_initial", "charisma_initial",
        "force", "intelligence", "charisma",
        "infantry_phase_initial", "cavalry_phase_initial",
        "archer_phase_initial", "governance_phase_initial",
        "infantry_phase", "cavalry_phase", "archer_phase", "governance_phase",
        "morale", "personality", "wisdom", "exp", "skill_points",
        "talent_ygzq", "talent_ygsj", "talent_djzc", "talent_tqtb", "talent_skill",
        "exp_bonus", "attack_bonus", "defense_bonus", "hp_bonus", "morale_bonus",
        "combo_rate",
        "skill_name", "skill_desc", "status", "pos", "dest", "death_time",
    ]
    placeholders = ", ".join(["%s"] * len(fields))
    field_str = ", ".join([f"`{f}`" for f in fields])
    sql = f"INSERT INTO generals ({field_str}) VALUES ({placeholders})"
    values = [data.get(f, None) for f in fields]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
            return cur.lastrowid


async def get_general_by_id(general_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM generals WHERE id = %s", (general_id,))
            return await cur.fetchone()


async def get_generals_by_user(user_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM generals WHERE user_id = %s ORDER BY id ASC",
                (user_id,)
            )
            return await cur.fetchall()


async def update_general(general_id, updates, conn=None):
    if not updates:
        return 0
    set_str = ", ".join([f"`{k}`=%s" for k in updates.keys()])
    sql = f"UPDATE generals SET {set_str} WHERE id = %s"
    values = list(updates.values()) + [general_id]
    if conn is not None:
        async with conn.cursor() as cur:
            row_count = await cur.execute(sql, values)
            return row_count
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            row_count = await cur.execute(sql, values)
            return row_count


async def delete_general(general_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM generals WHERE id = %s", (general_id,))


async def get_all_generals():
    """获取全量武将数据（用于启动时加载缓存）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM generals")
            return await cur.fetchall()
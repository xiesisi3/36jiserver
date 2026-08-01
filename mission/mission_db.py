import aiomysql
import logging
from core.database import get_pool

logger = logging.getLogger('36ji-server')


async def create_table():
    """创建使命进度表"""
    sql = """
    CREATE TABLE IF NOT EXISTS user_missions (
        user_id             VARCHAR(32) PRIMARY KEY       COMMENT '用户ID',
        combat_score        INT          DEFAULT 0         COMMENT '累计战斗积分',
        development_score   INT          DEFAULT 0         COMMENT '累计发展分',
        general_claimed     TEXT         COMMENT '武将升级已领取阶段JSON数组',
        hero_claimed        TEXT         COMMENT '英雄招募已领取阶段JSON数组',
        fief_claimed        TEXT         COMMENT '个人扩张已领取阶段JSON数组',
        combat_claimed      TEXT         COMMENT '战斗已领取阶段JSON数组',
        city_claimed        TEXT         COMMENT '国家扩张已领取阶段JSON数组',
        development_claimed TEXT         COMMENT '发展已领取阶段JSON数组'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='使命进度表'
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql)
    logger.info("使命进度表创建/检查完成")


async def get_all_missions():
    """获取所有用户的使命进度"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM user_missions")
            return await cursor.fetchall()


async def get_mission_by_user(user_id):
    """获取单个用户的使命进度，不存在则返回None"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT * FROM user_missions WHERE user_id = %s", (user_id,)
            )
            return await cursor.fetchone()


async def insert_mission(user_id):
    """为新用户创建使命进度记录"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "INSERT INTO user_missions (user_id) VALUES (%s)",
                (user_id,)
            )
    logger.info(f"用户 {user_id} 使命进度记录创建成功")


async def update_mission_claimed(user_id, mission_type, claimed_json):
    """更新已领取阶段列表
    :param mission_type: general_claimed / hero_claimed / fief_claimed / combat_claimed / city_claimed / development_claimed
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                f"UPDATE user_missions SET {mission_type} = %s WHERE user_id = %s",
                (claimed_json, user_id)
            )


async def update_mission_combat_score(user_id, score):
    """更新累计战斗积分"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "UPDATE user_missions SET combat_score = %s WHERE user_id = %s",
                (score, user_id)
            )


async def update_mission_development_score(user_id, score):
    """更新累计发展分"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "UPDATE user_missions SET development_score = %s WHERE user_id = %s",
                (score, user_id)
            )
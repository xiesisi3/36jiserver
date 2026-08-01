import aiomysql
import logging
from core.database import get_pool

logger = logging.getLogger('36ji-server')


async def create_table():
    """创建科技进度表"""
    sql = """
    CREATE TABLE IF NOT EXISTS user_tech (
        user_id             VARCHAR(32) NOT NULL              COMMENT '用户ID',
        tech_type           VARCHAR(32) NOT NULL              COMMENT '科技类型',
        level               INT          DEFAULT 0            COMMENT '当前等级',
        PRIMARY KEY (user_id, tech_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='科技进度表'
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql)
    logger.info("科技进度表创建/检查完成")


async def get_all_techs():
    """获取所有用户的科技进度"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM user_tech")
            return await cursor.fetchall()


async def get_tech_by_user(user_id):
    """获取单个用户的所有科技进度"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT * FROM user_tech WHERE user_id = %s", (user_id,)
            )
            return await cursor.fetchall()


async def upsert_tech(user_id, tech_type, level):
    """插入或更新科技等级"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "INSERT INTO user_tech (user_id, tech_type, level) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE level = %s",
                (user_id, tech_type, level, level)
            )
    logger.info(f"用户 {user_id} 科技 {tech_type} 更新为 {level} 级")
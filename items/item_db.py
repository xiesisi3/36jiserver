import aiomysql
from core.database import get_pool


async def create_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '道具唯一ID',
                    user_id VARCHAR(32) NOT NULL COMMENT '归属用户ID',
                    item_name VARCHAR(50) NOT NULL COMMENT '道具名称',
                    item_category VARCHAR(20) NOT NULL COMMENT '道具类别：chest/player/general',
                    quantity INT NOT NULL DEFAULT 1 COMMENT '数量',
                    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    INDEX idx_user_id (user_id),
                    INDEX idx_item_name (item_name),
                    INDEX idx_user_item (user_id, item_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='道具表'
            """)
            await cur.execute("SET SESSION sql_notes = 1")


async def insert_item(data):
    """插入道具记录，返回自增ID"""
    pool = get_pool()
    sql = "INSERT INTO items (user_id, item_name, item_category, quantity) VALUES (%s, %s, %s, %s)"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, (
                data["user_id"],
                data["item_name"],
                data["item_category"],
                data.get("quantity", 1),
            ))
            return cur.lastrowid


async def get_item_by_id(item_id):
    """根据道具ID查询单条记录"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM items WHERE id = %s", (item_id,))
            return await cur.fetchone()


async def get_items_by_user(user_id):
    """根据用户ID查询所有道具"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM items WHERE user_id = %s ORDER BY id ASC",
                (user_id,)
            )
            return await cur.fetchall()


async def get_item_by_user_and_name(user_id, item_name):
    """根据用户ID和道具名称查询单条记录（用于堆叠）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM items WHERE user_id = %s AND item_name = %s LIMIT 1",
                (user_id, item_name)
            )
            return await cur.fetchone()


async def update_item_quantity(item_id, quantity, conn=None):
    """更新道具数量"""
    sql = "UPDATE items SET quantity = %s WHERE id = %s"
    if conn is not None:
        async with conn.cursor() as cur:
            await cur.execute(sql, (quantity, item_id))
    else:
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (quantity, item_id))


async def delete_item(item_id):
    """删除道具记录"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM items WHERE id = %s", (item_id,))


async def get_all_items():
    """获取全部道具记录（用于启动时加载缓存）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM items ORDER BY id ASC")
            return await cur.fetchall()
import aiomysql
from core.database import get_pool


async def create_tables():
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET SESSION sql_notes = 0")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id                INT AUTO_INCREMENT PRIMARY KEY COMMENT '消息唯一ID',
                    sender_id         VARCHAR(32)  DEFAULT NULL COMMENT '发送方ID(NULL=系统)',
                    sender_name       VARCHAR(50)  DEFAULT NULL COMMENT '发送方名称',
                    receiver_id       VARCHAR(32)  NOT NULL COMMENT '接收方ID',
                    receiver_name     VARCHAR(50)  DEFAULT NULL COMMENT '接收方名称',
                    title             VARCHAR(200) DEFAULT NULL COMMENT '消息标题',
                    content           TEXT                     COMMENT '消息正文',
                    category          VARCHAR(20)  DEFAULT NULL COMMENT '分类(战斗/城池/外交/活动/公告/系统)',
                    msg_type          TINYINT      NOT NULL COMMENT '1=系统消息 2=好友申请 3=好友私聊 4=申请结果 5=军团申请',
                    extra_data        JSON         DEFAULT NULL COMMENT '扩展数据(军团申请:{"legion_id":1,"replied":0})',
                    is_read           TINYINT      NOT NULL DEFAULT 0 COMMENT '接收方是否已读',
                    sender_deleted    TINYINT      NOT NULL DEFAULT 0 COMMENT '发送方删除标记',
                    receiver_deleted  TINYINT      NOT NULL DEFAULT 0 COMMENT '接收方删除标记',
                    create_time       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    INDEX idx_receiver_msg (receiver_id, receiver_deleted, is_read),
                    INDEX idx_sender_msg (sender_id, sender_deleted)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息表'
            """)
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS friends (
                    id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '好友关系唯一ID',
                    user_id         VARCHAR(32)  NOT NULL COMMENT '发起方ID',
                    friend_id       VARCHAR(32)  NOT NULL COMMENT '目标方ID',
                    user_name       VARCHAR(50)  DEFAULT NULL COMMENT '发起方名称(缓存)',
                    friend_name     VARCHAR(50)  DEFAULT NULL COMMENT '目标方名称(缓存)',
                    remark          VARCHAR(100) DEFAULT NULL COMMENT '申请附言(非必填)',
                    status          TINYINT      NOT NULL DEFAULT 0 COMMENT '0=待确认 1=已接受 2=已拒绝',
                    create_time     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    update_time     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    UNIQUE KEY uk_user_friend (user_id, friend_id),
                    INDEX idx_user_status (user_id, status),
                    INDEX idx_friend_status (friend_id, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='好友表'
            """)
            # 为已有数据库增加 extra_data 字段（兼容旧表）
            try:
                await cur.execute(
                    "ALTER TABLE messages ADD COLUMN extra_data JSON DEFAULT NULL "
                    "COMMENT '扩展数据(军团申请:{\"legion_id\":1,\"replied\":0})'"
                )
            except Exception:
                pass
            await cur.execute("SET SESSION sql_notes = 1")


# ==================== 消息表 CRUD ====================


async def insert_message(data):
    pool = get_pool()
    fields = [
        "sender_id", "sender_name", "receiver_id", "receiver_name",
        "title", "content", "category", "msg_type",
        "extra_data", "is_read", "sender_deleted", "receiver_deleted",
    ]
    placeholders = ", ".join(["%s"] * len(fields))
    field_str = ", ".join(fields)
    sql = f"INSERT INTO messages ({field_str}) VALUES ({placeholders})"
    values = [data.get(f, None) for f in fields]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
            return cur.lastrowid


async def get_message_by_id(message_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM messages WHERE id = %s", (message_id,))
            return await cur.fetchone()


async def get_messages_by_user(user_id, msg_type=None, limit=20, offset=0):
    """获取用户可见的消息列表（排除用户已删除的）
    :param user_id: 用户ID
    :param msg_type: 可选的消息类型过滤
    :param limit: 分页大小
    :param offset: 分页偏移
    """
    pool = get_pool()
    conditions = ["((receiver_id = %s AND receiver_deleted = 0) OR (sender_id = %s AND sender_deleted = 0))"]
    params = [user_id, user_id]
    if msg_type is not None:
        conditions.append("msg_type = %s")
        params.append(msg_type)
    where = " AND ".join(conditions)
    sql = f"SELECT * FROM messages WHERE {where} ORDER BY create_time DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()


async def get_message_count(user_id, msg_type=None):
    pool = get_pool()
    conditions = ["((receiver_id = %s AND receiver_deleted = 0) OR (sender_id = %s AND sender_deleted = 0))"]
    params = [user_id, user_id]
    if msg_type is not None:
        conditions.append("msg_type = %s")
        params.append(msg_type)
    where = " AND ".join(conditions)
    sql = f"SELECT COUNT(*) FROM messages WHERE {where}"
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_unread_count(user_id):
    """获取用户未读消息数量"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM messages WHERE receiver_id = %s AND is_read = 0 AND receiver_deleted = 0",
                (user_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else 0


async def mark_message_read(message_id):
    """标记单条消息为已读"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE messages SET is_read = 1 WHERE id = %s",
                (message_id,)
            )


async def batch_mark_read(message_ids):
    """批量标记消息为已读"""
    if not message_ids:
        return
    pool = get_pool()
    placeholders = ", ".join(["%s"] * len(message_ids))
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE messages SET is_read = 1 WHERE id IN ({placeholders})",
                message_ids
            )


async def delete_message(message_id, user_id):
    """用户删除消息（P2P双删逻辑 / 系统消息直接物理删除）
    返回: "deleted" = 已物理删除, "soft" = 已标记删除, "not_found" = 消息不存在
    """
    msg = await get_message_by_id(message_id)
    if msg is None:
        return "not_found"

    sender_id = msg.get("sender_id")

    if sender_id is None:
        # 系统消息：直接物理删除
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM messages WHERE id = %s", (message_id,))
        return "deleted"

    # P2P 消息：标记己方删除
    if user_id == sender_id:
        field = "sender_deleted"
    else:
        field = "receiver_deleted"

    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"UPDATE messages SET {field} = 1 WHERE id = %s",
                (message_id,)
            )

    # 检查双方是否都删了，都删则物理删除
    msg_after = await get_message_by_id(message_id)
    if msg_after and msg_after.get("sender_deleted") and msg_after.get("receiver_deleted"):
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM messages WHERE id = %s", (message_id,))
        return "deleted"

    return "soft"


async def update_message_extra_data(message_id, extra_data):
    """更新消息的扩展数据字段"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE messages SET extra_data = %s WHERE id = %s",
                (extra_data, message_id)
            )


async def mark_application_replied(leader_user_id, application_user_id):
    """标记军团申请消息为已回复（找到 msg_type=5 的消息并更新 extra_data.replied=1）"""
    import json
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, extra_data FROM messages "
                "WHERE receiver_id = %s AND sender_id = %s AND msg_type = 5 AND receiver_deleted = 0 "
                "ORDER BY create_time DESC LIMIT 1",
                (leader_user_id, application_user_id)
            )
            row = await cur.fetchone()
            if row is None:
                return
            message_id = row["id"]
            extra = row["extra_data"] if row["extra_data"] else {}
            if isinstance(extra, str):
                extra = json.loads(extra)
            extra["replied"] = 1
            await cur.execute(
                "UPDATE messages SET extra_data = %s WHERE id = %s",
                (json.dumps(extra, ensure_ascii=False), message_id)
            )


# ==================== 好友表 CRUD ====================


async def insert_friend(data):
    """插入好友关系
    :param data: {user_id, friend_id, user_name, friend_name, remark, status}
    """
    pool = get_pool()
    fields = ["user_id", "friend_id", "user_name", "friend_name", "remark", "status"]
    placeholders = ", ".join(["%s"] * len(fields))
    field_str = ", ".join(fields)
    sql = f"INSERT INTO friends ({field_str}) VALUES ({placeholders})"
    values = [data.get(f, None) for f in fields]
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, values)
            return cur.lastrowid


async def get_friend_by_id(friend_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM friends WHERE id = %s", (friend_id,))
            return await cur.fetchone()


async def get_friend_relation(user_id, friend_id):
    """查询两人之间的好友关系（不管方向）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM friends WHERE (user_id = %s AND friend_id = %s) OR (user_id = %s AND friend_id = %s)",
                (user_id, friend_id, friend_id, user_id)
            )
            return await cur.fetchone()


async def get_friends_by_user(user_id):
    """获取某用户的所有好友（已接受状态）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM friends WHERE (user_id = %s OR friend_id = %s) AND status = 1",
                (user_id, user_id)
            )
            return await cur.fetchall()


async def get_pending_requests(user_id):
    """获取发给某用户的待处理好友申请（别人发给我的）"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM friends WHERE friend_id = %s AND status = 0",
                (user_id,)
            )
            return await cur.fetchall()


async def update_friend_status(friend_id, status):
    """更新好友关系状态"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE friends SET status = %s WHERE id = %s",
                (status, friend_id)
            )


async def delete_friend(friend_id):
    """删除好友关系"""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM friends WHERE id = %s", (friend_id,))
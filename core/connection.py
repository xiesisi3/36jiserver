import asyncio
import logging
import uuid

from data.global_data import clients
from message.protocol import encode

logger = logging.getLogger('36ji-server')


async def send_message(websocket, msg_dict):
    try:
        await websocket.send(encode(msg_dict))
    except Exception as e:
        logger.error(f"发送消息失败: {e}")


async def broadcast(msg_dict):
    if not clients:
        logger.info("广播失败：没有在线客户端")
        return
    msg_dict["type"] = "broadcast"
    tasks = [send_message(info["ws"], msg_dict) for info in clients.values()]
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"广播消息: {msg_dict}")


async def send_to_user(user_id, msg_dict):
    """向指定用户推送消息（用户不在线则静默跳过）"""
    if not user_id or not clients:
        return
    for info in clients.values():
        if info.get("user_id") == user_id:
            await send_message(info["ws"], msg_dict)
            return


def get_online_user_ids():
    """获取所有已登录的在线用户ID列表"""
    return [info["user_id"] for info in clients.values() if info.get("user_id")]


def is_user_online(user_id):
    """判断指定用户是否在线"""
    if not user_id:
        return False
    for info in clients.values():
        if info.get("user_id") == user_id:
            return True
    return False


def bind_user(client_id, user_id):
    """登录成功后，将 user_id 绑定到指定客户端"""
    if client_id in clients:
        clients[client_id]["user_id"] = user_id
        logger.info(f"用户绑定: client_id={client_id} -> user_id={user_id}")


async def register_client(websocket):
    client_id = str(uuid.uuid4())[:8]
    clients[client_id] = {"ws": websocket, "user_id": None}
    logger.info(f"客户端连接: {client_id} (当前在线: {len(clients)})")
    await send_message(websocket, {
        "code": "success",
        "message": "connected",
        "data": {"client_id": client_id}
    })
    return client_id


async def unregister_client(client_id):
    if client_id in clients:
        del clients[client_id]
        logger.info(f"客户端断开: {client_id} (当前在线: {len(clients)})")
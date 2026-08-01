import logging
from core.connection import send_message
from message.protocol import make_response
from tech.tech_core import ensure_tech, get_tech_list, get_tech_detail, unlock_tech
from data.global_data import tech_cache, clients

logger = logging.getLogger('36ji-server')


def _get_user_id(client_id):
    """从client_id获取user_id"""
    return clients.get(client_id, {}).get("user_id")


async def handle_tech_list(websocket, client_id, msg):
    """获取科技列表（九种科技当前状态）"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if user_id not in tech_cache:
        await ensure_tech(user_id)

    result = get_tech_list(user_id)
    await send_message(websocket, make_response("success", "科技列表", result))


async def handle_tech_detail(websocket, client_id, msg):
    """获取某种科技的所有等级详情"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    tech_type = data.get("tech_type")

    if not tech_type:
        await send_message(websocket, make_response("error", "缺少科技类型", ""))
        return

    if user_id not in tech_cache:
        await ensure_tech(user_id)

    result = get_tech_detail(user_id, tech_type)
    if result is None:
        await send_message(websocket, make_response("error", "无效的科技类型", ""))
    else:
        await send_message(websocket, make_response("success", "科技详情", result))


async def handle_tech_unlock(websocket, client_id, msg):
    """解锁科技下一级"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    tech_type = data.get("tech_type")

    if not tech_type:
        await send_message(websocket, make_response("error", "缺少科技类型", ""))
        return

    if user_id not in tech_cache:
        await ensure_tech(user_id)

    success, result = await unlock_tech(user_id, tech_type)
    if success:
        await send_message(websocket, make_response("success", "解锁成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))
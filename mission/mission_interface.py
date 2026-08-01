import logging
from core.connection import send_message
from message.protocol import make_response
from mission.mission_core import ensure_mission, get_mission_list, get_mission_detail, claim_mission_reward
from data.global_data import mission_cache, clients

logger = logging.getLogger('36ji-server')


def _get_user_id(client_id):
    """从client_id获取user_id"""
    return clients.get(client_id, {}).get("user_id")


async def handle_mission_list(websocket, client_id, msg):
    """获取使命列表及进度"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if user_id not in mission_cache:
        await ensure_mission(user_id)

    result = get_mission_list(user_id)
    await send_message(websocket, make_response("success", "使命列表", result))


async def handle_mission_claim(websocket, client_id, msg):
    """领取使命奖励（自动领取第一个未领取的阶段）"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    mission_type = data.get("mission_type")

    if not mission_type:
        await send_message(websocket, make_response("error", "缺少使命类型", ""))
        return

    if user_id not in mission_cache:
        await ensure_mission(user_id)

    success, result = await claim_mission_reward(user_id, mission_type)
    if success:
        await send_message(websocket, make_response("success", "领取成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_mission_detail(websocket, client_id, msg):
    """获取单种使命类型的所有阶段详情"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    mission_type = data.get("mission_type")

    if not mission_type:
        await send_message(websocket, make_response("error", "缺少使命类型", ""))
        return

    if user_id not in mission_cache:
        await ensure_mission(user_id)

    result = get_mission_detail(user_id, mission_type)
    if result is None:
        await send_message(websocket, make_response("error", "无效的使命类型", ""))
    else:
        await send_message(websocket, make_response("success", "使命详情", result))
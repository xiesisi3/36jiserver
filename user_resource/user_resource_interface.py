from core.connection import send_message
from message.protocol import make_response
from user_resource.user_resource_core import (
    get_user_resource_from_cache,
    check_user_exists_by_player_name,
)

import logging
logger = logging.getLogger('36ji-server')


async def handle_user_resource(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id", "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    resource = get_user_resource_from_cache(user_id)
    if resource is None:
        await send_message(websocket, make_response("error", "用户资源不存在", ""))
        return

    await send_message(websocket, make_response("success", "用户资源", resource))


async def handle_user_exists(websocket, client_id, msg):
    data = msg.get("data", {})
    player_name = (data.get("player_name") or "").strip()

    if not player_name:
        await send_message(websocket, make_response("error", "缺少游戏名称", ""))
        return

    exists, user_id = await check_user_exists_by_player_name(player_name)
    await send_message(websocket, make_response("success", "查询成功", {
        "exists": exists,
        "user_id": user_id,
    }))
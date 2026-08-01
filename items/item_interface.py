import logging

from core.connection import send_message
from message.protocol import make_response
from data.global_data import clients
from items.item_core import get_user_items_from_cache, use_item

logger = logging.getLogger('36ji-server')


def _get_user_id(client_id):
    info = clients.get(client_id, {})
    return info.get("user_id")


async def handle_item_list(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    items = get_user_items_from_cache(user_id)
    await send_message(websocket, make_response("success", "道具列表", {
        "items": items,
        "count": len(items),
    }))


async def handle_item_use(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    item_id = data.get("item_id")
    general_id = data.get("general_id")
    quantity = data.get("quantity", 1)

    if not item_id:
        await send_message(websocket, make_response("error", "缺少道具ID", ""))
        return

    if not isinstance(item_id, int):
        await send_message(websocket, make_response("error", "道具ID必须是整数", ""))
        return

    if general_id is not None and not isinstance(general_id, int):
        await send_message(websocket, make_response("error", "武将ID必须是整数", ""))
        return

    if not isinstance(quantity, int) or quantity <= 0:
        await send_message(websocket, make_response("error", "使用数量必须为正整数", ""))
        return

    success, result = await use_item(user_id, item_id, general_id, quantity)
    if success:
        await send_message(websocket, make_response("success", "使用成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))
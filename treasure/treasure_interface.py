import logging

from core.connection import send_message
from message.protocol import make_response
from data.global_data import clients
from treasure.treasure_core import (
    equip_treasure,
    unequip_treasure,
    get_user_treasures_from_cache,
    enhance_treasure,
    decompose_treasure,
    reset_treasure,
    buy_material,
    get_enhance_quota,
    star_upgrade,
)

logger = logging.getLogger('36ji-server')


def _get_user_id(client_id):
    info = clients.get(client_id, {})
    return info.get("user_id")


async def handle_treasure_list(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    treasures = get_user_treasures_from_cache(user_id)
    await send_message(websocket, make_response("success", "宝物列表", {
        "treasures": treasures,
        "count": len(treasures),
    }))


async def handle_treasure_equip(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    treasure_id = data.get("treasure_id")
    general_id = data.get("general_id")

    if not treasure_id:
        await send_message(websocket, make_response("error", "缺少宝物ID", ""))
        return

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    success, result = await equip_treasure(user_id, treasure_id, general_id)
    if success:
        await send_message(websocket, make_response("success", result, {
            "treasure_id": treasure_id,
            "general_id": general_id,
        }))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_treasure_unequip(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    treasure_id = data.get("treasure_id")

    if not treasure_id:
        await send_message(websocket, make_response("error", "缺少宝物ID", ""))
        return

    success, result = await unequip_treasure(user_id, treasure_id)
    if success:
        await send_message(websocket, make_response("success", result, {
            "treasure_id": treasure_id,
        }))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_treasure_enhance(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    treasure_id = data.get("treasure_id")
    use_gold = data.get("use_gold", False)

    if not treasure_id:
        await send_message(websocket, make_response("error", "缺少宝物ID", ""))
        return

    success, result, extra = await enhance_treasure(user_id, treasure_id, use_gold=use_gold)
    if success:
        await send_message(websocket, make_response("success", result, extra))
    elif extra is not None:
        await send_message(websocket, make_response("fail", result, extra))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_treasure_decompose(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    treasure_id = data.get("treasure_id")

    if not treasure_id:
        await send_message(websocket, make_response("error", "缺少宝物ID", ""))
        return

    success, result, extra = await decompose_treasure(user_id, treasure_id)
    if success:
        await send_message(websocket, make_response("success", result, extra))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_treasure_reset(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    treasure_id = data.get("treasure_id")

    if not treasure_id:
        await send_message(websocket, make_response("error", "缺少宝物ID", ""))
        return

    success, result, extra = await reset_treasure(user_id, treasure_id)
    if success:
        await send_message(websocket, make_response("success", result, extra))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_treasure_enhance_quota(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    quota = get_enhance_quota(user_id)
    await send_message(websocket, make_response("success", "强化剩余次数", quota))


async def handle_treasure_material_buy(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    material_type = data.get("material_type")
    quantity = data.get("quantity")

    if not material_type:
        await send_message(websocket, make_response("error", "缺少材料类型", ""))
        return

    if not quantity:
        await send_message(websocket, make_response("error", "缺少购买数量", ""))
        return

    success, result, extra = await buy_material(user_id, material_type, quantity)
    if success:
        await send_message(websocket, make_response("success", result, extra))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_treasure_star_upgrade(websocket, client_id, msg):
    user_id = _get_user_id(client_id)
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    data = msg.get("data", {})
    treasure_ids = data.get("treasure_ids")
    base_index = data.get("base_index", 0)
    target_attr = data.get("target_attr")

    if not treasure_ids or not isinstance(treasure_ids, list) or len(treasure_ids) != 5:
        await send_message(websocket, make_response("error", "需要5件宝物ID", ""))
        return

    if not target_attr:
        await send_message(websocket, make_response("error", "缺少指定属性", ""))
        return

    success, result, extra = await star_upgrade(user_id, treasure_ids, base_index, target_attr)
    if success:
        await send_message(websocket, make_response("success", result, extra))
    else:
        await send_message(websocket, make_response("error", result, ""))
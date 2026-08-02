from legion.legion_core import (
    get_legions_by_nation, create_legion, apply_join_legion, handle_application,
    set_vice_leader, transfer_leader, leave_legion, get_legion_detail,
    get_my_legion_detail, supply_from_granary, supply_from_legion_granary,
    unlock_legion_stage, exchange_legion_item, get_legion_exchange_items,
    use_pearl_on_fief,
)
from data.global_data import user_nation_cache, legion_member_cache
from core.connection import send_message
from message.protocol import make_response


async def handle_legion_list(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    nation_id = user_nation_cache.get(user_id)
    if nation_id is None:
        await send_message(websocket, make_response("error", "你还没有选择国家", ""))
        return

    legions = get_legions_by_nation(nation_id)
    my_legion = legion_member_cache.get(user_id)
    await send_message(websocket, make_response("success", "军团列表", {
        "nation_id": nation_id,
        "my_legion_id": my_legion["legion_id"] if my_legion else None,
        "legions": legions,
    }))


async def handle_legion_create(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    if not user_id or not name:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    nation_id = user_nation_cache.get(user_id)
    if nation_id is None:
        await send_message(websocket, make_response("error", "你还没有选择国家", ""))
        return

    ok, result = await create_legion(user_id, nation_id, name, description)
    if ok:
        await send_message(websocket, make_response("success", "军团创建成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_apply(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    legion_id = data.get("legion_id")
    if not user_id or legion_id is None:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return
    legion_id = int(legion_id)

    ok, result = await apply_join_legion(user_id, legion_id)
    if ok:
        await send_message(websocket, make_response("success", result, ""))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_application_handle(websocket, client_id, msg):
    data = msg.get("data", {})
    leader_user_id = data.get("user_id")
    application_user_id = data.get("application_user_id")
    legion_id = data.get("legion_id")
    accept = data.get("accept")
    if not leader_user_id or not application_user_id or legion_id is None:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return
    legion_id = int(legion_id)
    accept = bool(accept)

    ok, result = await handle_application(leader_user_id, application_user_id, legion_id, accept)
    if ok:
        await send_message(websocket, make_response("success", result, ""))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_set_vice(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    target_user_id = data.get("target_user_id")
    if not user_id or not target_user_id:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    ok, result = await set_vice_leader(user_id, target_user_id)
    if ok:
        await send_message(websocket, make_response("success", result, ""))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_transfer(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    target_user_id = data.get("target_user_id")
    if not user_id or not target_user_id:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    ok, result = await transfer_leader(user_id, target_user_id)
    if ok:
        await send_message(websocket, make_response("success", result, ""))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_leave(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    ok, result = await leave_legion(user_id)
    if ok:
        await send_message(websocket, make_response("success", result, ""))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_detail(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    legion_id = data.get("legion_id")
    if not user_id:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    if legion_id is not None:
        detail = get_legion_detail(int(legion_id))
    else:
        detail = get_my_legion_detail(user_id)

    if detail is None:
        await send_message(websocket, make_response("error", "军团不存在或你不在军团中", ""))
        return

    await send_message(websocket, make_response("success", "军团详情", detail))


async def handle_legion_supply(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = data.get("user_id")
    troop_id = data.get("troop_id")
    food_amount = data.get("food_amount")
    if not user_id or troop_id is None or food_amount is None:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return
    troop_id = int(troop_id)
    food_amount = int(food_amount)

    ok, result = await supply_from_granary(user_id, troop_id, food_amount)
    if ok:
        await send_message(websocket, make_response("success", "补给成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_granary_supply(websocket, client_id, msg):
    data = msg.get("data", {})
    operator_user_id = data.get("user_id")
    target_troop_id = data.get("troop_id")
    food_amount = data.get("food_amount")
    if not operator_user_id or target_troop_id is None or food_amount is None:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return
    target_troop_id = int(target_troop_id)
    food_amount = int(food_amount)

    ok, result = await supply_from_legion_granary(operator_user_id, target_troop_id, food_amount)
    if ok:
        await send_message(websocket, make_response("success", "补给成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_unlock(websocket, client_id, msg):
    """军团阶段解锁"""
    data = msg.get("data", {})
    user_id = data.get("user_id")
    category = data.get("category")
    if not user_id or not category:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    ok, result = await unlock_legion_stage(user_id, category)
    if ok:
        await send_message(websocket, make_response("success", "解锁成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_exchange(websocket, client_id, msg):
    """军团积分兑换道具"""
    data = msg.get("data", {})
    user_id = data.get("user_id")
    item_name = (data.get("item_name") or "").strip()
    quantity = data.get("quantity", 1)
    if not user_id or not item_name:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return
    quantity = int(quantity) if quantity else 1

    ok, result = await exchange_legion_item(user_id, item_name, quantity)
    if ok:
        await send_message(websocket, make_response("success", "兑换成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_legion_exchange_list(websocket, client_id, msg):
    """查询军团可兑换列表"""
    data = msg.get("data", {})
    user_id = data.get("user_id")
    if not user_id:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return

    ok, result = get_legion_exchange_items(user_id)
    if ok:
        await send_message(websocket, make_response("success", "可兑换列表", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_pearl_use(websocket, client_id, msg):
    """使用灵珠（土灵珠/水灵珠）"""
    data = msg.get("data", {})
    user_id = data.get("user_id")
    item_name = (data.get("item_name") or "").strip()
    town_id = data.get("town_id")
    if not user_id or not item_name or town_id is None:
        await send_message(websocket, make_response("error", "参数解析失败", ""))
        return
    town_id = int(town_id)

    ok, result = await use_pearl_on_fief(user_id, item_name, town_id)
    if ok:
        await send_message(websocket, make_response("success", "灵珠使用成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))
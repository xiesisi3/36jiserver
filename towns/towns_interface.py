from core.connection import send_message
from message.protocol import make_response
from data.global_data import clients, fief_cache
from towns.towns_core import (
    get_all_towns_from_cache,
    get_town_by_id_from_cache,
    get_towns_in_viewport_from_cache,
)


def _attach_fief_flag(towns, client_id):
    user_id = clients.get(client_id, {}).get("user_id")
    if user_id:
        user_towns = {f["town_id"] for f in fief_cache.values() if f["user_id"] == user_id}
    else:
        user_towns = set()
    return [{**t, "has_fief": t["id"] in user_towns} for t in towns]


async def handle_towns_all(websocket, client_id, msg):
    towns = get_all_towns_from_cache()
    towns = _attach_fief_flag(towns, client_id)
    await send_message(websocket, make_response("success", "城池列表", towns))


async def handle_towns_viewport(websocket, client_id, msg):
    data = msg.get("data", {})
    x1 = data.get("x1", 0)
    y1 = data.get("y1", 0)
    x2 = data.get("x2", 0)
    y2 = data.get("y2", 0)
    towns = get_towns_in_viewport_from_cache(x1, y1, x2, y2)
    towns = _attach_fief_flag(towns, client_id)
    await send_message(websocket, make_response("success", "视口城池", towns))


async def handle_towns_detail(websocket, client_id, msg):
    data = msg.get("data", {})
    town_id = data.get("town_id")
    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return
    town = get_town_by_id_from_cache(town_id)
    if town is None:
        await send_message(websocket, make_response("error", "城池不存在", ""))
        return

    status = town.get("status", 0)
    if status in (1, 2, 3):
        from towns.towns_outer.town_outer_combat.combat_interface import handle_town_combat_detail
        await handle_town_combat_detail(websocket, client_id, msg)
        return

    user_id = clients.get(client_id, {}).get("user_id")
    if user_id:
        user_towns = {f["town_id"] for f in fief_cache.values() if f["user_id"] == user_id}
    else:
        user_towns = set()
    town["has_fief"] = town["id"] in user_towns
    await send_message(websocket, make_response("success", "城池详情", town))
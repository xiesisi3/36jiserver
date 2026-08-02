import json
from legion.legion_core import (
    get_legions_by_nation, create_legion, apply_join_legion, handle_application,
    set_vice_leader, transfer_leader, leave_legion, get_legion_detail,
    get_my_legion_detail, supply_from_granary, supply_from_legion_granary,
)
from data.global_data import user_nation_cache

MSG_PARSE_ERROR = json.dumps({"type": "legion_error", "code": -1, "msg": "参数解析失败"})


async def handle_legion_list(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
    except (KeyError, TypeError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    nation_id = user_nation_cache.get(user_id)
    if nation_id is None:
        await websocket.send(json.dumps({
            "type": "legion_list",
            "code": 1,
            "msg": "你还没有选择国家",
        }))
        return

    legions = get_legions_by_nation(nation_id)
    await websocket.send(json.dumps({
        "type": "legion_list",
        "code": 0,
        "data": {
            "nation_id": nation_id,
            "legions": legions,
        },
    }))


async def handle_legion_create(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
        name = params["name"].strip()
        description = params.get("description", "").strip()
    except (KeyError, TypeError, AttributeError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    if not name:
        await websocket.send(json.dumps({
            "type": "legion_create",
            "code": 1,
            "msg": "军团名称不能为空",
        }))
        return

    nation_id = user_nation_cache.get(user_id)
    if nation_id is None:
        await websocket.send(json.dumps({
            "type": "legion_create",
            "code": 1,
            "msg": "你还没有选择国家",
        }))
        return

    ok, result = await create_legion(user_id, nation_id, name, description)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_create",
            "code": 0,
            "data": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_create",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_apply(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
        legion_id = int(params["legion_id"])
    except (KeyError, TypeError, ValueError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await apply_join_legion(user_id, legion_id)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_apply",
            "code": 0,
            "msg": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_apply",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_application_handle(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        leader_user_id = params["user_id"]
        application_user_id = params["application_user_id"]
        legion_id = int(params["legion_id"])
        accept = bool(params["accept"])
    except (KeyError, TypeError, ValueError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await handle_application(leader_user_id, application_user_id, legion_id, accept)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_application_handle",
            "code": 0,
            "msg": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_application_handle",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_set_vice(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
        target_user_id = params["target_user_id"]
    except (KeyError, TypeError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await set_vice_leader(user_id, target_user_id)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_set_vice",
            "code": 0,
            "msg": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_set_vice",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_transfer(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
        target_user_id = params["target_user_id"]
    except (KeyError, TypeError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await transfer_leader(user_id, target_user_id)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_transfer",
            "code": 0,
            "msg": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_transfer",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_leave(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
    except (KeyError, TypeError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await leave_legion(user_id)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_leave",
            "code": 0,
            "msg": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_leave",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_detail(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
        legion_id = params.get("legion_id")
    except (KeyError, TypeError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    if legion_id is not None:
        detail = get_legion_detail(int(legion_id))
    else:
        detail = get_my_legion_detail(user_id)

    if detail is None:
        await websocket.send(json.dumps({
            "type": "legion_detail",
            "code": 1,
            "msg": "军团不存在或你不在军团中",
        }))
        return

    await websocket.send(json.dumps({
        "type": "legion_detail",
        "code": 0,
        "data": detail,
    }))


async def handle_legion_supply(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        user_id = params["user_id"]
        troop_id = int(params["troop_id"])
        food_amount = int(params["food_amount"])
    except (KeyError, TypeError, ValueError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await supply_from_granary(user_id, troop_id, food_amount)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_supply",
            "code": 0,
            "data": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_supply",
            "code": 1,
            "msg": result,
        }))


async def handle_legion_granary_supply(websocket, client_id, msg):
    params = json.loads(msg)
    try:
        operator_user_id = params["user_id"]
        target_troop_id = int(params["troop_id"])
        food_amount = int(params["food_amount"])
    except (KeyError, TypeError, ValueError):
        await websocket.send(MSG_PARSE_ERROR)
        return

    ok, result = await supply_from_legion_granary(operator_user_id, target_troop_id, food_amount)
    if ok:
        await websocket.send(json.dumps({
            "type": "legion_granary_supply",
            "code": 0,
            "data": result,
        }))
    else:
        await websocket.send(json.dumps({
            "type": "legion_granary_supply",
            "code": 1,
            "msg": result,
        }))
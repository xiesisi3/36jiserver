from core.connection import send_message
from message.protocol import make_response
from message.combat_guard import require_town_peace
from data.global_data import clients
from troop.troop_core import (
    create_troop,
    dismiss_troop,
    update_troop,
    swap_troops,
    get_user_troop_list,
    get_troop_detail,
    move_troop,
)


async def handle_troop_list(websocket, client_id, msg):
    user_id = clients.get(client_id, {}).get("user_id")

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    troops = get_user_troop_list(user_id)
    await send_message(websocket, make_response("success", "部队列表", {
        "troops": troops,
        "count": len(troops),
    }))


@require_town_peace
async def handle_troop_create(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    general_id = data.get("general_id")
    town_id = data.get("town_id")
    team = data.get("team")
    food = data.get("food", 0)
    grid_x = data.get("grid_x", 10)
    grid_y = data.get("grid_y", 9)
    target_type = data.get("target_type", "nearest")

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not general_id:
        await send_message(websocket, make_response("error", "缺少武将ID", ""))
        return

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    if not team:
        await send_message(websocket, make_response("error", "缺少编组阵容", ""))
        return

    success, result = await create_troop(user_id, general_id, town_id, team, food, grid_x, grid_y, target_type)
    if success:
        await send_message(websocket, make_response("success", "编组成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_troop_dismiss(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    troop_id = data.get("troop_id")

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not troop_id:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    success, result = await dismiss_troop(user_id, troop_id)
    if success:
        await send_message(websocket, make_response("success", "取消编组成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_troop_detail(websocket, client_id, msg):
    data = msg.get("data", {})
    troop_id = data.get("troop_id")

    if not troop_id:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    troop = get_troop_detail(troop_id)
    if troop is None:
        await send_message(websocket, make_response("error", "部队不存在", ""))
        return

    await send_message(websocket, make_response("success", "部队详情", dict(troop)))


@require_town_peace
async def handle_troop_move(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    troop_id = data.get("troop_id")
    grid_x = data.get("grid_x")
    grid_y = data.get("grid_y")
    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not troop_id:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    if grid_x is None or grid_y is None:
        await send_message(websocket, make_response("error", "缺少目标网格坐标", ""))
        return

    if not isinstance(grid_x, int) or not isinstance(grid_y, int):
        await send_message(websocket, make_response("error", "网格坐标必须为整数", ""))
        return

    success, result = await move_troop(user_id, troop_id, grid_x, grid_y)
    if success:
        await send_message(websocket, make_response("success", "移动成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_troop_update(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    troop_id = data.get("troop_id")
    team = data.get("team")
    food = data.get("food", 0)
    target_type = data.get("target_type", None)

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not troop_id:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    if not team:
        await send_message(websocket, make_response("error", "缺少编组阵容", ""))
        return

    success, result = await update_troop(user_id, troop_id, team, food, target_type)
    if success:
        await send_message(websocket, make_response("success", "修改成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_troop_swap(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = clients.get(client_id, {}).get("user_id")
    troop_id_a = data.get("troop_id_a")
    team_a = data.get("team_a")
    food_a = data.get("food_a", 0)
    troop_id_b = data.get("troop_id_b")
    team_b = data.get("team_b")
    food_b = data.get("food_b", 0)

    if not user_id:
        await send_message(websocket, make_response("error", "未登录", ""))
        return

    if not troop_id_a or not troop_id_b:
        await send_message(websocket, make_response("error", "缺少部队ID", ""))
        return

    if team_a is None or team_b is None:
        await send_message(websocket, make_response("error", "缺少编组阵容", ""))
        return

    if isinstance(team_a, list) and len(team_a) == 0:
        team_a = [None, None, None, None, None]
    if isinstance(team_b, list) and len(team_b) == 0:
        team_b = [None, None, None, None, None]

    success, result = await swap_troops(
        user_id, troop_id_a, team_a, food_a, troop_id_b, team_b, food_b
    )
    if success:
        await send_message(websocket, make_response("success", "交换成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))
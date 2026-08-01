import logging

from core.connection import send_message
from message.protocol import make_response
from message.combat_guard import require_town_peace
from data.global_data import user_resource_cache
from fief.fief_core import (
    get_initial_l1_towns,
    get_user_fief_list,
    get_fief_detail,
    get_fief_by_user_and_town,
    get_fief_building_detail,
    create_initial_fief,
    create_fief,
    build_building,
    upgrade_building,
    cancel_build,
    demolish_building,
    upgrade_all_same_type,
    unlock_grid,
    train_troop,
    train_troop_all,
    speedup_training,
    abandon_fief,
    get_buildable_list,
    get_fief_income,
    rename_fief,
)
from treasure.treasure_core import grant_initial_treasures
from items.item_core import grant_initial_items

logger = logging.getLogger('36ji-server')


async def handle_fief_initial_info(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    towns, err = get_initial_l1_towns(user_id)
    if err:
        await send_message(websocket, make_response("error", err, ""))
        return

    await send_message(websocket, make_response("success", "初始封地可选列表", towns))


async def handle_fief_initial_select(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()
    town_id = data.get("town_id")

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    success, result = await create_initial_fief(user_id, town_id)
    if success:
        await grant_initial_treasures(user_id)
        await grant_initial_items(user_id)
        await send_message(websocket, make_response("success", "初始封地创建成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_create(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()
    town_id = data.get("town_id")

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    success, result = await create_fief(user_id, town_id)
    if success:
        await send_message(websocket, make_response("success", "封地创建成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_fief_list(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    fiefs = get_user_fief_list(user_id)
    await send_message(websocket, make_response("success", "封地列表", fiefs))


async def handle_fief_detail(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    result, err = get_fief_detail(fief_id)
    if err:
        await send_message(websocket, make_response("error", err, ""))
        return

    await send_message(websocket, make_response("success", "封地详情", result))


async def handle_fief_detail_by_town(websocket, client_id, msg):
    data = msg.get("data", {})
    user_id = (data.get("user_id") or "").strip()
    town_id = data.get("town_id")

    if not user_id:
        await send_message(websocket, make_response("error", "缺少用户ID", ""))
        return

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    result, err = get_fief_by_user_and_town(user_id, town_id)
    if err:
        await send_message(websocket, make_response("error", err, ""))
        return

    await send_message(websocket, make_response("success", "封地详情", result))


async def handle_fief_building_detail(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    result, err = get_fief_building_detail(fief_id, row, col)
    if err:
        await send_message(websocket, make_response("error", err, ""))
        return

    await send_message(websocket, make_response("success", "建筑详情", result))


@require_town_peace
async def handle_fief_build(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")
    building_type = (data.get("building_type") or "").strip()

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    if not building_type:
        await send_message(websocket, make_response("error", "缺少建筑类型", ""))
        return

    from data.global_data import fief_cache
    fief = fief_cache.get(fief_id)
    user_id = fief["user_id"] if fief else "?"
    res_before = user_resource_cache.get(user_id, {})
    logger.info(f"[BUILD] 请求: fief_id={fief_id}, row={row}, col={col}, type={building_type}, user_id={user_id}")
    logger.info(f"[BUILD] 操作前资源: wood={res_before.get('wood')}, grain={res_before.get('grain')}, iron={res_before.get('iron')}")

    success, result = await build_building(fief_id, row, col, building_type)

    res_after = user_resource_cache.get(user_id, {})
    logger.info(f"[BUILD] 操作后资源: wood={res_after.get('wood')}, grain={res_after.get('grain')}, iron={res_after.get('iron')}")
    if success:
        logger.info(f"[BUILD] 返回: success, cost={result.get('cost')}")
        await send_message(websocket, make_response("success", "建造开始", result))
    else:
        logger.info(f"[BUILD] 返回: error, msg={result}")
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_upgrade(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    from data.global_data import fief_cache
    fief = fief_cache.get(fief_id)
    user_id = fief["user_id"] if fief else "?"
    res_before = user_resource_cache.get(user_id, {})
    logger.info(f"[UPGRADE] 请求: fief_id={fief_id}, row={row}, col={col}, user_id={user_id}")
    logger.info(f"[UPGRADE] 操作前资源: wood={res_before.get('wood')}, grain={res_before.get('grain')}, iron={res_before.get('iron')}")

    success, result = await upgrade_building(fief_id, row, col)

    res_after = user_resource_cache.get(user_id, {})
    logger.info(f"[UPGRADE] 操作后资源: wood={res_after.get('wood')}, grain={res_after.get('grain')}, iron={res_after.get('iron')}")
    if success:
        logger.info(f"[UPGRADE] 返回: success, cost={result.get('cost')}")
        await send_message(websocket, make_response("success", "升级开始", result))
    else:
        logger.info(f"[UPGRADE] 返回: error, msg={result}")
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_cancel_build(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    success, result = await cancel_build(fief_id, row, col)
    if success:
        await send_message(websocket, make_response("success", "取消成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_demolish(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    success, result = await demolish_building(fief_id, row, col)
    if success:
        await send_message(websocket, make_response("success", "拆除成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_upgrade_all_same(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    building_type = (data.get("building_type") or "").strip()

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if not building_type:
        await send_message(websocket, make_response("error", "缺少建筑类型", ""))
        return

    success, result = await upgrade_all_same_type(fief_id, building_type)
    if success:
        await send_message(websocket, make_response("success", "一键升级开始", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_unlock_grid(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    success, result = await unlock_grid(fief_id, row, col)
    if success:
        await send_message(websocket, make_response("success", "网格解锁成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_train_troop(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    row = data.get("row")
    col = data.get("col")
    troop_name = (data.get("troop_name") or "").strip()
    count = data.get("count", 0)

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is None or col is None:
        await send_message(websocket, make_response("error", "缺少网格坐标", ""))
        return

    if not troop_name:
        await send_message(websocket, make_response("error", "缺少兵种名称", ""))
        return

    if not isinstance(count, int) or count <= 0 or count > 100:
        await send_message(websocket, make_response("error", "训练数量无效（1-100）", ""))
        return

    success, result = await train_troop(fief_id, row, col, troop_name, count)
    if success:
        await send_message(websocket, make_response("success", "训练开始", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_train_troop_all(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    troop_name = (data.get("troop_name") or "").strip()
    count = data.get("count", 0)

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if not troop_name:
        await send_message(websocket, make_response("error", "缺少兵种名称", ""))
        return

    if not isinstance(count, int) or count <= 0 or count > 100:
        await send_message(websocket, make_response("error", "训练数量无效（1-100）", ""))
        return

    success, result = await train_troop_all(fief_id, troop_name, count)
    if success:
        await send_message(websocket, make_response("success", "一键训练开始", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_fief_train_speedup(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    barrack_type = data.get("barrack_type")
    row = data.get("row")
    col = data.get("col")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if row is not None and col is not None:
        if not isinstance(row, int) or not isinstance(col, int):
            await send_message(websocket, make_response("error", "坐标必须为整数", ""))
            return
        success, result = await speedup_training(fief_id, row=row, col=col)
    else:
        if not barrack_type:
            await send_message(websocket, make_response("error", "多兵营加速必须指定兵营类型", ""))
            return
        success, result = await speedup_training(fief_id, barrack_type=barrack_type)

    if success:
        await send_message(websocket, make_response("success", "秒训完成", result))
    else:
        await send_message(websocket, make_response("error", result, ""))


@require_town_peace
async def handle_fief_abandon(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    success, result = await abandon_fief(fief_id)
    if success:
        await send_message(websocket, make_response("success", result, ""))
    else:
        await send_message(websocket, make_response("error", result, ""))


async def handle_fief_buildable_list(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    result, err = get_buildable_list(fief_id)
    if err:
        await send_message(websocket, make_response("error", err, ""))
        return

    await send_message(websocket, make_response("success", "可建造建筑列表", result))


async def handle_fief_income(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    result, err = get_fief_income(fief_id)
    if err:
        await send_message(websocket, make_response("error", err, ""))
        return

    await send_message(websocket, make_response("success", "封地收益", result))


@require_town_peace
async def handle_fief_rename(websocket, client_id, msg):
    data = msg.get("data", {})
    fief_id = data.get("fief_id")
    new_name = (data.get("name") or "").strip()

    if not fief_id:
        await send_message(websocket, make_response("error", "缺少封地ID", ""))
        return

    if not new_name:
        await send_message(websocket, make_response("error", "缺少封地名称", ""))
        return

    success, result = await rename_fief(fief_id, new_name)
    if success:
        await send_message(websocket, make_response("success", "封地改名成功", result))
    else:
        await send_message(websocket, make_response("error", result, ""))
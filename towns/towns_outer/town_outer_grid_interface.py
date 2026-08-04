import asyncio
from core.connection import send_message
from message.protocol import make_response
from data.global_data import clients, town_outer_grid_cache, troop_cache, user_nation_cache
from towns.towns_outer.town_outer_grid_core import get_outer_grid
from general.general_utils import get_general_info


async def handle_outer_grid_info(websocket, client_id, msg):
    data = msg.get("data", {})
    town_id = data.get("town_id")

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    result = get_outer_grid(town_id)
    if result is None:
        await send_message(websocket, make_response("error", "该城池外城网格数据不存在", ""))
        return

    await send_message(websocket, make_response("success", "外城网格数据", result))


async def handle_town_troop_list(websocket, client_id, msg):
    data = msg.get("data", {})
    town_id = data.get("town_id")

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    user_id = clients.get(client_id, {}).get("user_id")
    grid = town_outer_grid_cache.get(town_id)
    if grid is None:
        await send_message(websocket, make_response("error", "该城池外城网格数据不存在", ""))
        return

    troop_ids = set()
    troop_positions = {}  # 反向索引: troop_id → (r, c)，避免清理时再次遍历361格
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            for tid in grid[r][c]:
                troop_ids.add(tid)
                troop_positions[tid] = (r, c)

    troops = []
    invalid_ids = []

    for tid in troop_ids:
        troop = troop_cache.get(tid)
        if troop is None:
            invalid_ids.append(tid)
            continue
        if troop.get("pos") != town_id:
            invalid_ids.append(tid)
            continue
        troop_data = dict(troop)
        troop_data["nation_id"] = user_nation_cache.get(troop.get("user_id"), 1)
        general = get_general_info(troop.get("general_id"))
        if general:
            troop_data["general"] = {
                "hero_name": general.get("hero_name"),
                "level": general.get("level"),
                "force": general.get("force"),
                "intelligence": general.get("intelligence"),
                "charisma": general.get("charisma"),
            }
        else:
            troop_data["general"] = None
        troops.append(troop_data)

    from legion.legion_assembly import get_assembly_flag_for_town
    from data.global_data import legion_member_cache
    if user_id:
        member = legion_member_cache.get(user_id)
        if member:
            assembly_plan_id = get_assembly_flag_for_town(member["legion_id"], town_id)
            if assembly_plan_id:
                for t in troops:
                    tid = t.get("id")
                    from legion.legion_assembly import get_assembly_flag_for_troop
                    flag = get_assembly_flag_for_troop(tid)
                    t["assembly_plan_id"] = flag if flag == assembly_plan_id else None
            else:
                for t in troops:
                    t["assembly_plan_id"] = None
        else:
            for t in troops:
                t["assembly_plan_id"] = None
    else:
        for t in troops:
            t["assembly_plan_id"] = None

    # 兜底清理：将pos不匹配或已不存在的部队从网格中移除，防止脏数据累积
    if invalid_ids:
        from towns.towns_outer.town_outer_grid_core import remove_troop_from_grid
        import logging
        _logger = logging.getLogger("36ji-server")
        for tid in invalid_ids:
            pos = troop_positions.get(tid)
            if pos is None:
                continue
            r, c = pos
            if tid in grid[r][c]:
                grid[r][c].remove(tid)
            _troop = troop_cache.get(tid)
            _reason = "部队不存在" if not _troop else f"pos不匹配(pos={_troop.get('pos')}, 期望={town_id})"
            _logger.warning(
                f"[网格数据校验] 移除无效部队 {tid} 于城池 {town_id} 格子({r},{c})，原因: {_reason}"
            )
            # 异步清理DB，不阻塞响应
            asyncio.ensure_future(remove_troop_from_grid(town_id, tid, r, c))

    await send_message(websocket, make_response("success", "城池部队列表", {
        "town_id": town_id,
        "troops": troops,
        "count": len(troops),
    }))
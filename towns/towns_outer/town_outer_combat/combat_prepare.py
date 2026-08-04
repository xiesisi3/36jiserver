import asyncio
import copy
import logging

from server_timer.server_timer_core import get_uptime_ms
from data.global_data import (
    towns_cache, troop_cache, troops_arrived_at_town,
    user_nation_cache, town_outer_grid_cache,
)
from towns.towns_outer.town_outer_grid_core import (
    DIRECTION_GRID_POS, _calculate_gate_positions,
    GRID_ROWS, GRID_COLS,
)
from towns.towns_outer.town_outer_combat.combat_move import (
    is_troop_alive, get_troop_owner,
)
from towns.towns_outer.town_outer_combat.combat_db import (
    insert_combat_history, update_combat_history,
)
from towns.towns_outer.town_outer_combat.combat_settlement import settle_combat
from towns.towns_outer.town_outer_combat.militia import generate_militia_troops, cleanup_militia_troops
from towns.towns_db import update_town_status, update_town_owner, update_town_attrs
from troop.troop_db import update_troop
from core.connection import broadcast
from message.protocol import make_response

logger = logging.getLogger("36ji-server")

PRELOAD_DURATION_MS = 30 * 1000


def _get_town_defenders(town_id):
    grid = town_outer_grid_cache.get(town_id)
    if not grid:
        return []

    defenders = []
    total_in_grid = 0
    for r in range(len(grid)):
        for c in range(len(grid[r])):
            for tid in grid[r][c]:
                total_in_grid += 1
                troop = troop_cache.get(tid)
                if troop and is_troop_alive(troop) and troop.get("status") == 1:
                    troop_copy = copy.deepcopy(troop)
                    troop_copy["troop_id"] = tid
                    troop_copy["grid_pos"] = [r, c]
                    defenders.append(troop_copy)
    return defenders


def _get_arriving_troops(town_id, now_ms=None, cutoff_ms=None):
    arriving = []
    arrived_ids = troops_arrived_at_town.get(town_id, [])
    for tid in list(arrived_ids):
        troop = troop_cache.get(tid)
        if troop and is_troop_alive(troop):
            troop_copy = copy.deepcopy(troop)
            troop_copy["troop_id"] = tid
            gx = troop_copy.get("grid_x")
            gy = troop_copy.get("grid_y")
            troop_copy["grid_pos"] = [gx, gy] if gx is not None and gy is not None else None
            arriving.append(troop_copy)
    return arriving


def _get_and_clear_arriving_troops(town_id):
    arriving = []
    arrived_ids = troops_arrived_at_town.get(town_id, [])
    for tid in list(arrived_ids):
        troop = troop_cache.get(tid)
        if troop and is_troop_alive(troop):
            troop_copy = copy.deepcopy(troop)
            troop_copy["troop_id"] = tid
            gx = troop_copy.get("grid_x")
            gy = troop_copy.get("grid_y")
            troop_copy["grid_pos"] = [gx, gy] if gx is not None and gy is not None else None
            arriving.append(troop_copy)
        arrived_ids.remove(tid)
    return arriving


def _assign_gate_positions(troops, town_id):
    gate_positions = _calculate_gate_positions(town_id)
    if not gate_positions:
        gate_positions = {(9, 9)}

    gate_list = list(gate_positions)
    troops_without_pos = [t for t in troops if t.get("grid_pos") is None]
    for i, troop in enumerate(troops_without_pos):
        troop["grid_pos"] = list(gate_list[i % len(gate_list)])


def _collect_all_battle_troops(town_id, now_ms, include_arriving=True):
    defenders = _get_town_defenders(town_id)
    arriving = []
    if include_arriving:
        arriving = _get_arriving_troops(town_id)
    all_troops = defenders + arriving
    _assign_gate_positions(all_troops, town_id)
    return all_troops, defenders, arriving


async def _cleanup_town_grid(town_id, defenders):
    grid = town_outer_grid_cache.get(town_id)
    if grid is None:
        return

    valid_positions = {}
    for t in defenders:
        pos = t.get("grid_pos")
        if pos and len(pos) == 2:
            key = (pos[0], pos[1])
            valid_positions.setdefault(key, set()).add(t["troop_id"])

    from towns.towns_outer.town_outer_grid_db import update_grid_cell
    dirty_count = 0
    removed_count = 0
    added_count = 0

    for x in range(GRID_ROWS):
        for y in range(GRID_COLS):
            valid_ids = valid_positions.get((x, y), set())
            cell = grid[x][y]
            current_ids = set(cell) if cell else set()
            if current_ids != valid_ids:
                removed_count += len(current_ids - valid_ids)
                added_count += len(valid_ids - current_ids)
                dirty_count += 1
                new_cell = list(valid_ids)
                grid[x][y] = new_cell
                await update_grid_cell(town_id, x, y, new_cell)

    if dirty_count > 0:
        pass


async def enter_battle_preparation(town_id):
    """
    进入战斗准备阶段（30秒预加载）。
    在此阶段：
    1. 根据民心生成民兵（义勇军/连弩），写入DB+cache
    2. 收集防守方（status=1的驻守部队）和已到达的进攻方（troops_arrived_at_town中的部队）
    3. 民兵排在最前（优先被攻击），然后是守军，最后是进攻方
    4. 清理城池网格，以所有参战部队的grid_pos为准重写grid
    5. 分配城门位置给没有grid_pos的部队
    6. 将所有参战部队存入fight_round_vars，等待预加载结束后开始第一回合
    7. 取消该城池的所有集结计划（战斗即刻触发取消）

    关键设计：进攻方在行军到达时已被写入grid（server_timer中add_troop_to_grid），
    此处通过_get_and_clear_arriving_troops将其纳入all_troops，确保_cleanup_town_grid
    保留其grid位置，从而使handle_town_troop_list在准备阶段能返回完整的部队列表。
    start_first_round中再次调用_get_and_clear_arriving_troops只会拿到预加载期间新到达的部队。
    """
    from legion.legion_assembly import cancel_plans_at_town
    asyncio.create_task(cancel_plans_at_town(town_id, "集结点发生战斗，集结计划自动取消"))
    now_ms = get_uptime_ms()
    preload_end_ms = now_ms + PRELOAD_DURATION_MS

    # 生成民兵（基于民心，仅在战斗准备阶段生成，服务器恢复时不走此路径）
    # 民兵先写入DB和cache，grid由后续 _cleanup_town_grid 统一处理
    town = towns_cache.get(town_id)
    militia_troops = await generate_militia_troops(town_id, town)

    defenders = _get_town_defenders(town_id)
    # 获取已到达的进攻方部队（触发战斗的部队），同时清理troops_arrived_at_town
    # 这样start_first_round中再次调用时只会拿到预加载期间新到达的部队
    arriving = _get_and_clear_arriving_troops(town_id)
    # 民兵排最前，优先被攻击（进攻方默认先攻击位置靠前的部队）
    all_troops = militia_troops + defenders + arriving

    await _cleanup_town_grid(town_id, all_troops)
    _assign_gate_positions(all_troops, town_id)

    participant_ids = [t["troop_id"] for t in all_troops]

    history_id = await insert_combat_history({
        "town_id": town_id,
        "start_time": now_ms,
        "participants": participant_ids,
        "is_finished": 0,
    })

    from data.global_data import fight_round_vars
    fight_round_vars[town_id] = {
        "round_num": 0,
        "is_active": False,
        "start_time": 0,
        "estimated_end_time": 0,
        "preload_start_ms": now_ms,
        "preload_end_ms": preload_end_ms,
        "history_id": history_id,
        "_battle_troops": all_troops,
        "_defenders": militia_troops + defenders,
        "_arriving": arriving,
        "_militia_troops": militia_troops,
    }

    for troop in all_troops:
        tid = troop["troop_id"]
        if tid in troop_cache:
            troop_cache[tid]["status"] = 3
            await update_troop(tid, {"status": 3})

    # 进攻方部队的pos和dest在server_timer中已设置，此处确保缓存一致
    for troop in arriving:
        tid = troop["troop_id"]
        if tid in troop_cache:
            troop_cache[tid]["status"] = 3
            troop_cache[tid]["pos"] = town_id
            troop_cache[tid]["dest"] = None

    towns_cache[town_id]["status"] = 1
    await update_town_status(town_id, 1)

    await broadcast(make_response("success", "城池战斗准备消息", {
        "type": "town_combat_notify",
        "town_id": town_id,
        "state": "preparing",
        "round_num": 0,
        "preload_start_ms": now_ms,
        "preload_end_ms": preload_end_ms,
    }))

    logger.info(f"城池 {town_id} 进入战斗预加载阶段，预加载结束时间: {preload_end_ms}ms, 民兵: {len(militia_troops)}支, 守军: {len(defenders)}支, 进攻方: {len(arriving)}支")


def check_combat_end(town_id, battle_troops, next_round_troops):
    town = towns_cache.get(town_id)
    if not town:
        return True, None, "城池不存在"

    town_owner = town.get("owner")

    all_troops = battle_troops + next_round_troops

    alive_by_owner = {}
    for troop in all_troops:
        alive = is_troop_alive(troop)
        owner = get_troop_owner(troop, user_nation_cache)
        if alive:
            if owner is not None:
                alive_by_owner[owner] = alive_by_owner.get(owner, 0) + 1

    if not alive_by_owner:
        return True, town_owner, "全军覆没"

    if len(alive_by_owner) == 1:
        winner = list(alive_by_owner.keys())[0]
        if winner == town_owner:
            return True, town_owner, "防御成功"
        else:
            return True, winner, "占领"

    return False, None, None


async def _change_town_owner(town_id, new_owner):
    towns_cache[town_id]["owner"] = new_owner
    from towns.towns_db import update_town_owner
    await update_town_owner(town_id, new_owner)
    logger.info(f"城池 {town_id} 归属变更: {new_owner}")

    from fief.fief_core import destroy_fiefs_by_town
    await destroy_fiefs_by_town(town_id)


async def finish_combat(town_id, winner, victory_type):
    towns_cache[town_id]["status"] = 3
    await update_town_status(town_id, 3)

    original_town_owner = towns_cache[town_id].get("owner")

    if victory_type == "占领" and winner is not None:
        await _change_town_owner(town_id, winner)
        towns_cache[town_id]["stability"] = 0
        towns_cache[town_id]["defense"] = 0
        towns_cache[town_id]["traffic"] = 0
        towns_cache[town_id]["popular_support"] = 0
        await update_town_attrs(town_id, {
            "stability": 0,
            "defense": 0,
            "traffic": 0,
            "popular_support": 0,
        })

    now_ms = get_uptime_ms()
    end_prepare_duration = PRELOAD_DURATION_MS
    end_prepare_ms = now_ms + end_prepare_duration

    from data.global_data import fight_round_vars
    frv = fight_round_vars.get(town_id, {})
    history_id = frv.get("history_id")
    total_rounds = frv.get("round_num", 0)

    if history_id:
        await update_combat_history(history_id, {
            "end_time": now_ms,
            "winner": winner,
            "victory_type": victory_type,
            "total_rounds": total_rounds,
            "is_finished": 1,
        })

    # 存活部队状态更新：驻守、pos设为目标城池、清空目标
    battle_troops = frv.get("_battle_troops", [])
    # 清理民兵部队（义勇军/连弩），战斗结束后全部销毁
    # 民兵是临时部队，无论战斗胜负，战斗结束后都不保留
    await cleanup_militia_troops(town_id, battle_troops)
    for troop in battle_troops:
        tid = troop["troop_id"]
        user_id = str(troop.get("user_id", ""))
        general_id = troop.get("general_id")
        # 跳过民兵部队（已在上方 cleanup_militia_troops 中删除）
        # 义勇军 general_id=-10002，连弩 general_id=-10005
        if general_id in (-10002, -10005):
            continue
        # 更新部队：status=1(驻守), pos=目标城池, 清空目标
        if tid in troop_cache:
            troop_cache[tid]["status"] = 1
            troop_cache[tid]["pos"] = town_id
            troop_cache[tid]["dest"] = None
        await update_troop(tid, {
            "status": 1,
            "pos": town_id,
            "dest": None,
        })
        # 更新玩家武将状态为驻守（山贼武将不处理）
        if user_id != "0" and general_id:
            from general.general_utils import get_general_info
            from general.general_db import update_general
            general = get_general_info(general_id)
            if general:
                general["status"] = 1
                await update_general(general_id, {"status": 1})
                logger.info(f"[战斗结束] 城池{town_id} 武将 {general_id} (user_id={user_id}) 最终状态: "
                            f"level={general.get('level')}, exp={general.get('exp')}, "
                            f"skill_points={general.get('skill_points')}, status=1")

    # 更新外城网格数据：根据存活部队最终坐标重建网格
    grid = town_outer_grid_cache.get(town_id)
    if grid:
        for x in range(GRID_ROWS):
            for y in range(GRID_COLS):
                grid[x][y] = []
        for troop in battle_troops:
            # 跳过民兵部队（已在 cleanup_militia_troops 中从grid删除）
            # 义勇军 general_id=-10002，连弩 general_id=-10005
            if troop.get("general_id") in (-10002, -10005):
                continue
            grid_pos = troop.get("grid_pos")
            if grid_pos and len(grid_pos) == 2:
                gx, gy = grid_pos[0], grid_pos[1]
                if 0 <= gx < GRID_ROWS and 0 <= gy < GRID_COLS:
                    grid[gx][gy].append(troop["troop_id"])
        from towns.towns_outer.town_outer_grid_db import update_grid
        await update_grid(town_id, grid)

    if town_id in fight_round_vars:
        fight_round_vars[town_id]["is_active"] = False
        fight_round_vars[town_id]["end_prepare_ms"] = end_prepare_ms
        fight_round_vars[town_id]["winner"] = winner
        fight_round_vars[town_id]["victory_type"] = victory_type

    await broadcast(make_response("fight_end_prepare", "城池战斗结束准备消息", {
        "type": "town_combat_notify",
        "town_id": town_id,
        "state": "ending",
        "winner": winner,
        "victory_type": victory_type,
        "end_prepare_ms": end_prepare_ms,
    }))

    logger.info(f"城池 {town_id} 进入结束准备状态: {victory_type}, 胜利方: {winner}")

    if history_id:
        await settle_combat(town_id, history_id, winner, victory_type, original_town_owner)


async def resume_battle_preparation(town_id, history_id, battle_troops, round_num=0):
    now_ms = get_uptime_ms()
    preload_end_ms = now_ms + PRELOAD_DURATION_MS

    from data.global_data import fight_round_vars
    fight_round_vars[town_id] = {
        "round_num": round_num,
        "is_active": False,
        "start_time": 0,
        "estimated_end_time": 0,
        "preload_start_ms": now_ms,
        "preload_end_ms": preload_end_ms,
        "history_id": history_id,
        "_battle_troops": battle_troops,
        "_defenders": battle_troops,
        "_arriving": [],
    }

    for troop in battle_troops:
        tid = troop["troop_id"]
        if tid in troop_cache:
            troop_cache[tid]["status"] = 3
            troop_cache[tid]["pos"] = town_id
            troop_cache[tid]["dest"] = None
            await update_troop(tid, {"status": 3, "pos": town_id, "dest": None})

    towns_cache[town_id]["status"] = 1
    await update_town_status(town_id, 1)

    await broadcast(make_response("success", "城池战斗准备消息", {
        "type": "town_combat_notify",
        "town_id": town_id,
        "state": "preparing",
        "round_num": 0,
        "preload_start_ms": now_ms,
        "preload_end_ms": preload_end_ms,
    }))

    logger.info(f"城池 {town_id} 战斗恢复预加载，history_id={history_id}, 部队: {len(battle_troops)}支, preload_end_ms={preload_end_ms}ms")
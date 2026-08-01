# 行军核心逻辑
# 目标查询、预览、出征执行（含批量）

import math
import logging

from core.connection import send_message
from message.protocol import make_response
from message.combat_guard import require_town_peace
from data.global_data import (
    clients, towns_cache, troop_cache, user_nation_cache,
    user_resource_cache, generals_cache,
)
from general.general_db import update_general
from general.general_core import sync_cache_update
from server_timer.server_timer_core import get_uptime_ms
from troop.troop_march_constants import (
    GOLD_PER_ACCEL_30,
    GOLD_PER_ACCEL_50,
    ACCEL_FACTOR_30,
    ACCEL_FACTOR_50,
    ACCEL_FACTOR_NONE,
)
from troop.troop_march_utils import (
    get_march_targets,
    dijkstra_shortest_path,
    get_troop_min_speed,
    calculate_travel_time_seconds,
    calculate_march_food,
    get_gate_position,
    calc_batch_time_range,
    can_troops_arrive_at_time,
)
from troop.troop_march_db import (
    batch_update_troop_march_status,
)
from towns.towns_outer.town_outer_grid_core import (
    remove_troop_from_grid,
)

logger = logging.getLogger('36ji-server')


def _get_user_id(client_id):
    return clients.get(client_id, {}).get("user_id")


def _get_user_nation(user_id):
    return user_nation_cache.get(user_id)


def _get_accel_factor(accel_level):
    if accel_level == 30:
        return ACCEL_FACTOR_30
    elif accel_level == 50:
        return ACCEL_FACTOR_50
    return ACCEL_FACTOR_NONE


def _get_gold_cost(accel_level, troop_count):
    if accel_level == 30:
        return GOLD_PER_ACCEL_30 * troop_count
    elif accel_level == 50:
        return GOLD_PER_ACCEL_50 * troop_count
    return 0


def _get_total_gold_cost(troop_accels):
    """从 per-troop accel 列表计算总黄金消耗"""
    total = 0
    for ta in troop_accels:
        a = ta.get("accel", 0)
        if a == 30:
            total += GOLD_PER_ACCEL_30
        elif a == 50:
            total += GOLD_PER_ACCEL_50
    return total


async def handle_march_targets(websocket, client_id, msg):
    """查询可出征目标城池列表"""
    user_id = _get_user_id(client_id)
    if not user_id:
        await _send_error(websocket, "未登录")
        return

    nation_id = _get_user_nation(user_id)
    if not nation_id:
        await _send_error(websocket, "未选择国家")
        return

    data = msg.get("data", {})
    source_town_id = data.get("town_id")
    if not source_town_id:
        await _send_error(websocket, "缺少出发城池ID")
        return

    if source_town_id not in towns_cache:
        await _send_error(websocket, "出发城池不存在")
        return

    targets = get_march_targets(nation_id, source_town_id)

    from core.connection import send_message
    from message.protocol import make_response
    await send_message(websocket, make_response("success", "可出征目标城池", {
        "source_town_id": source_town_id,
        "targets": targets,
        "count": len(targets),
    }))


async def handle_march_preview(websocket, client_id, msg):
    """预览行军信息（时间、粮食消耗、金币消耗）

    请求参数:
        source_town_id: 出发城池
        target_town_id: 目标城池
        troop_ids: 部队ID列表
        accel: 加速档位 (0/30/50)，普通模式使用，所有部队统一加速
        custom_arrive_time: 自定义到达相对毫秒数（None=普通模式）精确模式使用
        troop_accels: [{troop_id, accel}] 精确到达模式下每支部队的独立加速，不传则全部无加速
    """
    user_id = _get_user_id(client_id)
    if not user_id:
        await _send_error(websocket, "未登录")
        return

    data = msg.get("data", {})
    source_town_id = data.get("source_town_id")
    target_town_id = data.get("target_town_id")
    troop_ids = data.get("troop_ids", [])
    accel = data.get("accel", 0)
    custom_arrive_time = data.get("custom_arrive_time")
    troop_accels = data.get("troop_accels")

    if not source_town_id or not target_town_id:
        await _send_error(websocket, "缺少出发或目标城池ID")
        return

    if not troop_ids or not isinstance(troop_ids, list):
        await _send_error(websocket, "缺少部队ID列表")
        return

    if source_town_id not in towns_cache or target_town_id not in towns_cache:
        await _send_error(websocket, "城池不存在")
        return

    total_distance, path = dijkstra_shortest_path(source_town_id, target_town_id)
    if total_distance is None:
        await _send_error(websocket, "路径不存在")
        return

    source_town = towns_cache[source_town_id]
    target_town = towns_cache[target_town_id]
    source_traffic = source_town.get("traffic", 10000)
    target_traffic = target_town.get("traffic", 10000)

    troops = []
    errors = []
    for tid in troop_ids:
        troop = troop_cache.get(tid)
        if not troop:
            errors.append(f"部队 {tid} 不存在")
            continue
        if troop.get("user_id") != user_id:
            errors.append(f"部队 {tid} 不属于当前用户")
            continue
        if troop.get("status") != 1:
            errors.append(f"部队 {tid} 状态异常，无法出征")
            continue
        if troop.get("pos") != source_town_id:
            errors.append(f"部队 {tid} 不在出发城池")
            continue
        troops.append(troop)

    if errors:
        await _send_error(websocket, "; ".join(errors))
        return

    troop_count = len(troops)
    if troop_count == 0:
        await _send_error(websocket, "无有效部队")
        return

    is_custom = bool(custom_arrive_time)
    accel_factors = {}
    gold_cost = 0

    if is_custom and troop_accels:
        for ta in troop_accels:
            tid = ta.get("troop_id")
            a = ta.get("accel", 0)
            if a not in (0, 30, 50):
                await _send_error(websocket, f"部队 {tid} 无效的加速档位 {a}")
                return
            accel_factors[tid] = _get_accel_factor(a)
        gold_cost = _get_total_gold_cost(troop_accels)
    elif is_custom:
        for tid in troop_ids:
            accel_factors[tid] = ACCEL_FACTOR_NONE
        gold_cost = 0
    else:
        accel_factor = _get_accel_factor(accel)
        for tid in troop_ids:
            accel_factors[tid] = accel_factor
        gold_cost = _get_gold_cost(accel, troop_count)

    now_ms = get_uptime_ms()

    if is_custom:
        target_time_ms = now_ms + int(custom_arrive_time)

    troop_previews = []
    for troop in troops:
        tid = troop.get("id")
        team = troop.get("team", [])
        min_speed = get_troop_min_speed(team)
        travel_seconds = calculate_travel_time_seconds(
            total_distance, min_speed, source_traffic, target_traffic
        )
        factor = accel_factors.get(tid, 1.0)
        accelerated_seconds = math.ceil(travel_seconds * factor)
        march_food = calculate_march_food(team, total_distance)

        if is_custom:
            depart_time_ms = target_time_ms - accelerated_seconds * 1000
            arrive_time_ms = target_time_ms
        else:
            depart_time_ms = now_ms
            arrive_time_ms = now_ms + accelerated_seconds * 1000

        preview = {
            "troop_id": tid,
            "min_speed": min_speed,
            "travel_seconds": travel_seconds,
            "accelerated_seconds": accelerated_seconds,
            "march_food": march_food,
            "depart_time": depart_time_ms,
            "arrive_time": arrive_time_ms,
        }
        if is_custom:
            preview["accel"] = next((ta.get("accel", 0) for ta in (troop_accels or []) if ta.get("troop_id") == tid), 0)
            preview["accel_factor"] = factor
        troop_previews.append(preview)

    result = {
        "source_town_id": source_town_id,
        "target_town_id": target_town_id,
        "total_distance": total_distance,
        "path_towns": path,
        "source_traffic": source_traffic,
        "target_traffic": target_traffic,
        "troop_count": troop_count,
        "gold_cost": gold_cost,
        "troops": troop_previews,
    }

    if is_custom:
        result["earliest_arrive"] = None
        result["earliest_arrive_relative"] = None
        result["latest_arrive"] = None
        result["latest_arrive_relative"] = None
        result["custom_arrive_time"] = custom_arrive_time
        result["server_time_ms"] = now_ms
        result["troop_accels"] = troop_accels or []

        earliest, latest = calc_batch_time_range(
            troops, source_town_id, target_town_id, accel_factors
        )
        if earliest is not None:
            result["earliest_arrive"] = earliest
            result["earliest_arrive_relative"] = max(0, earliest - now_ms)
            result["latest_arrive"] = latest
            result["latest_arrive_relative"] = max(0, latest - now_ms)

        can_arrive, arrive_errors = can_troops_arrive_at_time(
            troops, source_town_id, target_town_id, target_time_ms, accel_factors
        )
        result["can_arrive"] = can_arrive
        if not can_arrive:
            result["arrive_errors"] = arrive_errors
    else:
        result["accel"] = accel
        result["accel_factor"] = accel_factor

    from core.connection import send_message
    from message.protocol import make_response
    await send_message(websocket, make_response("success", "行军预览", result))


@require_town_peace
async def handle_march_dispatch(websocket, client_id, msg):
    """执行出征（含批量）

    请求参数:
        source_town_id: 出发城池
        target_town_id: 目标城池
        troop_ids: 部队ID列表
        accel: 加速档位 (0/30/50)，普通模式使用，所有部队统一加速
        custom_arrive_time: 自定义到达相对毫秒数（None=普通模式同时出发）
        troop_accels: [{troop_id, accel}] 精确到达模式下每支部队的独立加速，不传则全部无加速
        client_gold_cost: 客户端显示的黄金消耗，服务端校验一致性
    """
    user_id = _get_user_id(client_id)
    if not user_id:
        await _send_error(websocket, "未登录")
        return

    data = msg.get("data", {})
    source_town_id = data.get("source_town_id")
    target_town_id = data.get("target_town_id")
    troop_ids = data.get("troop_ids", [])
    accel = data.get("accel", 0)
    custom_arrive_time = data.get("custom_arrive_time")
    client_gold_cost = data.get("client_gold_cost")
    troop_accels = data.get("troop_accels")

    if source_town_id == target_town_id:
        await _send_error(websocket, "出发和目标城池不能相同")
        return

    if not troop_ids or not isinstance(troop_ids, list):
        await _send_error(websocket, "缺少部队ID列表")
        return

    if source_town_id not in towns_cache or target_town_id not in towns_cache:
        await _send_error(websocket, "城池不存在")
        return

    nation_id = _get_user_nation(user_id)
    targets = get_march_targets(nation_id, source_town_id)
    target_ids = {t["town_id"] for t in targets}
    if target_town_id not in target_ids:
        await _send_error(websocket, "目标城池不可出征")
        return

    is_custom = bool(custom_arrive_time)

    if not is_custom and accel not in (0, 30, 50):
        await _send_error(websocket, "无效的加速档位")
        return

    total_distance, path = dijkstra_shortest_path(source_town_id, target_town_id)
    if total_distance is None:
        await _send_error(websocket, "路径不存在")
        return

    source_town = towns_cache[source_town_id]
    target_town = towns_cache[target_town_id]
    source_traffic = source_town.get("traffic", 10000)
    target_traffic = target_town.get("traffic", 10000)

    troops = []
    errors = []
    for tid in troop_ids:
        troop = troop_cache.get(tid)
        if not troop:
            errors.append(f"部队 {tid} 不存在")
            continue
        if troop.get("user_id") != user_id:
            errors.append(f"部队 {tid} 不属于当前用户")
            continue
        if troop.get("status") != 1:
            errors.append(f"部队 {tid} 状态异常，无法出征")
            continue
        if troop.get("pos") != source_town_id:
            errors.append(f"部队 {tid} 不在出发城池")
            continue
        troops.append(troop)

    if errors:
        await _send_error(websocket, "; ".join(errors))
        return

    troop_count = len(troops)
    if troop_count == 0:
        await _send_error(websocket, "无有效部队")
        return

    accel_factors = {}
    gold_cost = 0

    now_ms = get_uptime_ms()

    if is_custom:
        target_time_ms = now_ms + int(custom_arrive_time)

        if troop_accels:
            for ta in troop_accels:
                tid = ta.get("troop_id")
                a = ta.get("accel", 0)
                if a not in (0, 30, 50):
                    await _send_error(websocket, f"部队 {tid} 无效的加速档位 {a}")
                    return
                accel_factors[tid] = _get_accel_factor(a)
            gold_cost = _get_total_gold_cost(troop_accels)
        else:
            for tid in troop_ids:
                accel_factors[tid] = ACCEL_FACTOR_NONE
            gold_cost = 0

        can_arrive, arrive_errors = can_troops_arrive_at_time(
            troops, source_town_id, target_town_id, target_time_ms, accel_factors
        )
        if not can_arrive:
            await _send_error(websocket, "; ".join(arrive_errors))
            return

        if troop_accels:
            for ta in troop_accels:
                tid = ta.get("troop_id")
                a = ta.get("accel", 0)
                if a > 0:
                    troop_no_accel = [t for t in troops if t.get("id") == tid]
                    if troop_no_accel:
                        no_accel_factors = {tid: ACCEL_FACTOR_NONE}
                        can_no_accel, _ = can_troops_arrive_at_time(
                            troop_no_accel, source_town_id, target_town_id, target_time_ms, no_accel_factors
                        )
                        if can_no_accel:
                            await _send_error(websocket, f"部队 {tid} 无需加速即可在指定时间到达，请取消加速")
                            return
    else:
        if accel > 0:
            all_times = []
            for troop in troops:
                team = troop.get("team", [])
                min_speed = get_troop_min_speed(team)
                travel_seconds = calculate_travel_time_seconds(
                    total_distance, min_speed, source_traffic, target_traffic
                )
                all_times.append(travel_seconds)
        accel_factor = _get_accel_factor(accel)
        for tid in troop_ids:
            accel_factors[tid] = accel_factor
        gold_cost = _get_gold_cost(accel, troop_count)
        target_time_ms = None

    if client_gold_cost is not None and int(client_gold_cost) != gold_cost:
        await _send_error(websocket, f"黄金消耗不一致，客户端显示 {client_gold_cost}，服务端计算 {gold_cost}")
        return

    if gold_cost > 0:
        user_res = user_resource_cache.get(user_id)
        if not user_res:
            await _send_error(websocket, "用户资源不存在")
            return
        current_gold = user_res.get("gold", 0)
        if current_gold < gold_cost:
            await _send_error(websocket, f"黄金不足，需要 {gold_cost}，当前 {current_gold}")
            return

    gate_x, gate_y = get_gate_position(source_town_id, target_town_id, path)

    troop_updates_db = []
    troop_results = []
    total_march_food = 0

    for troop in troops:
        tid = troop.get("id")
        team = troop.get("team", [])
        min_speed = get_troop_min_speed(team)
        travel_seconds = calculate_travel_time_seconds(
            total_distance, min_speed, source_traffic, target_traffic
        )
        factor = accel_factors.get(tid, 1.0)
        accelerated_seconds = math.ceil(travel_seconds * factor)
        march_food = calculate_march_food(team, total_distance)

        current_food = troop.get("food", 0)
        if current_food < march_food:
            errors.append(f"部队 {tid} 粮食不足，需要 {march_food}，当前 {current_food}")
            continue

        new_food = current_food - march_food

        if is_custom:
            depart_time_ms = now_ms
            arrive_time_ms = target_time_ms
        else:
            depart_time_ms = now_ms
            arrive_time_ms = now_ms + accelerated_seconds * 1000

        # 测试阶段特殊处理：统一将到达时间设为20秒后
        arrive_time_ms = now_ms + 20000

        troop_updates_db.append((
            tid, 2, target_town_id, depart_time_ms, arrive_time_ms, gate_x, gate_y, new_food
        ))
        troop_results.append({
            "troop_id": tid,
            "depart_time": depart_time_ms,
            "arrive_time": arrive_time_ms,
            "march_food": march_food,
            "remaining_food": new_food,
            "accelerated_seconds": accelerated_seconds,
        })
        total_march_food += march_food

    if errors:
        await _send_error(websocket, "; ".join(errors))
        return

    if gold_cost > 0:
        user_resource_cache[user_id]["gold"] -= gold_cost

    for tid, status, dest, dep_time, arr_time, gx, gy, new_food in troop_updates_db:
        troop = troop_cache[tid]
        logger.info(
            f"[出征] 部队 {tid} 出征前: grid_x={troop.get('grid_x')}, "
            f"grid_y={troop.get('grid_y')}, status={troop.get('status')}, "
            f"pos={troop.get('pos')}, 目标城门=({gx},{gy}), dest={dest}"
        )
        troop["status"] = status
        troop["dest"] = dest
        troop["dep_time"] = dep_time
        troop["arrive_time"] = arr_time
        troop["food"] = new_food

        old_gx = troop.get("grid_x")
        old_gy = troop.get("grid_y")
        if old_gx is not None and old_gy is not None:
            await remove_troop_from_grid(source_town_id, tid, old_gx, old_gy)

        troop["gate_x"] = gx
        troop["gate_y"] = gy

        logger.info(
            f"[出征] 部队 {tid} 出征后: grid_x={troop.get('grid_x')}, "
            f"grid_y={troop.get('grid_y')}, gate_x={gx}, gate_y={gy}, status={troop.get('status')}, "
            f"dest={troop.get('dest')}, dep_time={troop.get('dep_time')}, "
            f"arrive_time={troop.get('arrive_time')}"
        )

    from core.database import get_pool
    pool = get_pool()
    async with pool.acquire() as txn_conn:
        await txn_conn.begin()
        try:
            await batch_update_troop_march_status(troop_updates_db, conn=txn_conn)

            if gold_cost > 0:
                from user_resource.user_resource_db import update_user_resource_field
                await update_user_resource_field(user_id, "gold", user_resource_cache[user_id]["gold"], conn=txn_conn)

            for tid, status, dest, dep_time, arr_time, gx, gy, new_food in troop_updates_db:
                troop = troop_cache[tid]
                general_id = troop.get("general_id")
                if general_id:
                    await update_general(general_id, {"status": 2, "dest": dest, "pos": source_town_id}, conn=txn_conn)
                    sync_cache_update(general_id, {"status": 2, "dest": dest, "pos": source_town_id})

            await txn_conn.commit()
            logger.info(f"[出征] 事务提交成功，{len(troop_updates_db)} 支部队出征")
        except Exception as e:
            await txn_conn.rollback()
            logger.exception(f"[出征] 事务回滚: {e}")
            await _send_error(websocket, "出征失败，请重试")
            return

    response_data = {
        "source_town_id": source_town_id,
        "target_town_id": target_town_id,
        "total_distance": total_distance,
        "path_towns": path,
        "gold_cost": gold_cost,
        "total_march_food": total_march_food,
        "is_custom_arrive": is_custom,
        "troops": troop_results,
    }

    if is_custom:
        response_data["troop_accels"] = troop_accels or []
    else:
        response_data["accel"] = accel
        response_data["accel_factor"] = accel_factor

    from core.connection import send_message
    from message.protocol import make_response
    await send_message(websocket, make_response("success", "出征成功", response_data))


async def _send_error(websocket, message):
    from core.connection import send_message
    from message.protocol import make_response
    await send_message(websocket, make_response("error", message, ""))
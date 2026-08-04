import math
import logging
import asyncio

from data.global_data import (
    clients, towns_cache, troop_cache, user_nation_cache,
    legion_cache, legion_member_cache,
    assembly_plans, assembly_troop_lock,
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
from troop.troop_march_constants import (
    ACCEL_FACTOR_30,
    ACCEL_FACTOR_50,
    ACCEL_FACTOR_NONE,
)
from troop.troop_march_db import (
    batch_update_troop_march_status,
)
from towns.towns_outer.town_outer_grid_core import (
    remove_troop_from_grid,
)
from troop.troop_utils import calculate_total_troops
from general.general_db import update_general
from general.general_core import sync_cache_update
from notification.notification_core import publish_system_message
from core.connection import send_to_user
from message.protocol import make_response
from server_timer.server_timer_core import get_uptime_ms

logger = logging.getLogger('36ji-server')

ROLE_LEADER = 1
ROLE_VICE = 2
ROLE_MEMBER = 3

MAX_PLANS_PER_LEGION = 4
MAX_PLAN_DURATION = 6 * 3600

_plan_id_counter = 0


def _next_plan_id():
    global _plan_id_counter
    _plan_id_counter += 1
    return _plan_id_counter


def _get_accel_factor(accel_level):
    if accel_level == 30:
        return ACCEL_FACTOR_30
    elif accel_level == 50:
        return ACCEL_FACTOR_50
    return ACCEL_FACTOR_NONE


def _get_user_nation(user_id):
    return user_nation_cache.get(user_id)


async def _cancel_plan_internal(plan, reason, notify_all=True):
    plan_id = plan["plan_id"]
    freed_troops = list(plan["participants"].keys())

    for tid in freed_troops:
        assembly_troop_lock.pop(tid, None)

    assembly_plans.pop(plan_id, None)

    if notify_all:
        notified = set()
        for tid in freed_troops:
            uid = plan["participants"][tid]["user_id"]
            notified.add(uid)
        commander_uid = plan["commander_user_id"]
        notified.add(commander_uid)

        town = towns_cache.get(plan["town_id"], {})
        town_name = town.get("name", "未知城池")

        for uid in notified:
            await publish_system_message(
                uid, "", "集结计划取消",
                f"集结于「{town_name}」的计划「{plan['title']}」已取消：{reason}",
                category="系统", msg_type=1,
            )
            await _push_assembly_update(uid)

    logger.info(f"集结计划 {plan_id} 已取消，释放 {len(freed_troops)} 支部队，原因: {reason}")


async def _push_assembly_update(user_id):
    await send_to_user(user_id, make_response("assembly_update", "集结状态变更", {}))


def create_assembly(user_id, town_id, title, remark, end_time, main_min, main_max, fodder_min, fodder_max):
    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    if member["role"] not in (ROLE_LEADER, ROLE_VICE):
        return False, "只有军团长或副军团长才能创建集结计划"

    legion_id = member["legion_id"]

    legion_plan_count = sum(1 for p in assembly_plans.values() if p["legion_id"] == legion_id)
    if legion_plan_count >= MAX_PLANS_PER_LEGION:
        return False, f"军团最多同时存在 {MAX_PLANS_PER_LEGION} 个集结计划"

    for p in assembly_plans.values():
        if p["commander_user_id"] == user_id:
            return False, "你已有一个进行中的集结计划，请先取消后再创建"

    now = get_uptime_ms()
    if end_time <= now:
        return False, "集结结束时间必须大于当前时间"

    if end_time - now > MAX_PLAN_DURATION * 1000:
        return False, f"集结时间最多 {MAX_PLAN_DURATION // 3600} 小时"

    for p in assembly_plans.values():
        if p["legion_id"] == legion_id and p["town_id"] == town_id:
            return False, "该城池已有本军团的集结计划，无法重复创建"

    if town_id not in towns_cache:
        return False, "城池不存在"

    if not title or not title.strip():
        return False, "集结标题不能为空"

    title = title.strip()

    if main_min < 0 or main_max < main_min:
        return False, "主力部队人数限制无效"
    if fodder_min < 0 or fodder_max < fodder_min:
        return False, "炮灰部队人数限制无效"

    plan_id = _next_plan_id()
    plan = {
        "plan_id": plan_id,
        "legion_id": legion_id,
        "town_id": town_id,
        "commander_user_id": user_id,
        "title": title,
        "remark": remark or "",
        "end_time": end_time,
        "created_at": now,
        "requirements": {
            "主力": {"min_troops": main_min, "max_troops": main_max},
            "炮灰": {"min_troops": fodder_min, "max_troops": fodder_max},
        },
        "participants": {},
    }
    assembly_plans[plan_id] = plan
    logger.info(f"集结计划 {plan_id} 创建成功，军团 {legion_id}，城池 {town_id}，指挥 {user_id}")
    return True, plan


def cancel_assembly(user_id, plan_id):
    plan = assembly_plans.get(plan_id)
    if plan is None:
        return False, "集结计划不存在"

    if plan["commander_user_id"] != user_id:
        return False, "只有计划创建者才能取消"

    asyncio.create_task(_cancel_plan_internal(plan, "指挥主动取消"))
    return True, {"plan_id": plan_id, "message": "集结计划已取消"}


def update_assembly(user_id, plan_id, main_min, main_max, fodder_min, fodder_max):
    plan = assembly_plans.get(plan_id)
    if plan is None:
        return False, "集结计划不存在"

    if plan["commander_user_id"] != user_id:
        return False, "只有计划创建者才能修改"

    if main_min < 0 or main_max < main_min:
        return False, "主力部队人数限制无效"
    if fodder_min < 0 or fodder_max < fodder_min:
        return False, "炮灰部队人数限制无效"

    plan["requirements"]["主力"]["min_troops"] = main_min
    plan["requirements"]["主力"]["max_troops"] = main_max
    plan["requirements"]["炮灰"]["min_troops"] = fodder_min
    plan["requirements"]["炮灰"]["max_troops"] = fodder_max
    return True, plan


def get_assembly_list(user_id):
    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    legion_id = member["legion_id"]
    plans = [p for p in assembly_plans.values() if p["legion_id"] == legion_id]

    result = []
    for plan in plans:
        town = towns_cache.get(plan["town_id"], {})
        result.append({
            "plan_id": plan["plan_id"],
            "town_id": plan["town_id"],
            "town_name": town.get("name", "未知城池"),
            "commander_user_id": plan["commander_user_id"],
            "title": plan["title"],
            "remark": plan["remark"],
            "end_time": plan["end_time"],
            "created_at": plan["created_at"],
            "requirements": plan["requirements"],
            "participant_count": len(plan["participants"]),
        })
    return True, result


def get_assembly_detail(user_id, plan_id):
    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    plan = assembly_plans.get(plan_id)
    if plan is None:
        return False, "集结计划不存在"

    if plan["legion_id"] != member["legion_id"]:
        return False, "无权查看该集结计划"

    town = towns_cache.get(plan["town_id"], {})
    is_commander = (plan["commander_user_id"] == user_id)

    result = {
        "plan_id": plan["plan_id"],
        "town_id": plan["town_id"],
        "town_name": town.get("name", "未知城池"),
        "commander_user_id": plan["commander_user_id"],
        "title": plan["title"],
        "remark": plan["remark"],
        "end_time": plan["end_time"],
        "created_at": plan["created_at"],
        "requirements": plan["requirements"],
        "participant_count": len(plan["participants"]),
    }

    if is_commander:
        participants_detail = []
        for tid, pinfo in plan["participants"].items():
            troop = troop_cache.get(tid)
            if troop:
                participants_detail.append({
                    "troop_id": tid,
                    "user_id": pinfo["user_id"],
                    "role_type": pinfo["role_type"],
                    "joined_at": pinfo["joined_at"],
                    "general_id": troop.get("general_id"),
                    "team": troop.get("team", []),
                    "food": troop.get("food", 0),
                    "total_troops": calculate_total_troops(troop.get("team", [])),
                    "target_type": troop.get("target_type", "nearest"),
                })
        result["participants"] = participants_detail

        summary = {"主力": 0, "炮灰": 0, "主力_troops": 0, "炮灰_troops": 0}
        for tid, pinfo in plan["participants"].items():
            troop = troop_cache.get(tid)
            if troop:
                total = calculate_total_troops(troop.get("team", []))
                if pinfo["role_type"] == "主力":
                    summary["主力"] += 1
                    summary["主力_troops"] += total
                else:
                    summary["炮灰"] += 1
                    summary["炮灰_troops"] += total
        result["summary"] = summary
    else:
        my_troops = []
        for tid, pinfo in plan["participants"].items():
            if pinfo["user_id"] == user_id:
                troop = troop_cache.get(tid)
                if troop:
                    my_troops.append({
                        "troop_id": tid,
                        "role_type": pinfo["role_type"],
                        "joined_at": pinfo["joined_at"],
                        "general_id": troop.get("general_id"),
                        "team": troop.get("team", []),
                        "food": troop.get("food", 0),
                        "total_troops": calculate_total_troops(troop.get("team", [])),
                        "target_type": troop.get("target_type", "nearest"),
                    })
        result["my_troops"] = my_troops

    return True, result


def join_assembly(user_id, plan_id, troops):
    member = legion_member_cache.get(user_id)
    if member is None:
        return False, "你不在军团中"

    plan = assembly_plans.get(plan_id)
    if plan is None:
        return False, "集结计划不存在"

    if plan["legion_id"] != member["legion_id"]:
        return False, "无权参与该集结计划"

    now = get_uptime_ms()
    if now >= plan["end_time"]:
        return False, "集结计划已结束"

    if not troops or not isinstance(troops, list):
        return False, "请指定参与的部队"

    reqs = plan["requirements"]
    joined = []
    errors = []

    for item in troops:
        tid = item.get("troop_id")
        role_type = item.get("role_type", "").strip()

        if not tid:
            errors.append("缺少部队ID")
            continue

        if role_type not in ("主力", "炮灰"):
            errors.append(f"部队 {tid} 角色类型无效，必须是 主力 或 炮灰")
            continue

        if tid in assembly_troop_lock:
            errors.append(f"部队 {tid} 已在其他集结计划中")
            continue

        if tid in plan["participants"]:
            errors.append(f"部队 {tid} 已参与本集结计划")
            continue

        troop = troop_cache.get(tid)
        if troop is None:
            errors.append(f"部队 {tid} 不存在")
            continue

        if troop.get("user_id") != user_id:
            errors.append(f"部队 {tid} 不属于你")
            continue

        if troop.get("status") != 1:
            errors.append(f"部队 {tid} 状态异常，无法参与集结，仅驻守状态可参与")
            continue

        if troop.get("pos") != plan["town_id"]:
            errors.append(f"部队 {tid} 不在集结城池")
            continue

        total_troops = calculate_total_troops(troop.get("team", []))
        req = reqs[role_type]
        if total_troops < req["min_troops"]:
            errors.append(f"部队 {tid} 兵力 {total_troops} 不足，{role_type}最少 {req['min_troops']} 人")
            continue
        if total_troops > req["max_troops"]:
            errors.append(f"部队 {tid} 兵力 {total_troops} 超出，{role_type}最多 {req['max_troops']} 人")
            continue

        plan["participants"][tid] = {
            "user_id": user_id,
            "role_type": role_type,
            "joined_at": now,
        }
        assembly_troop_lock[tid] = plan_id
        joined.append(tid)

    if errors:
        return False, "; ".join(errors)

    if not joined:
        return False, "无有效部队加入"

    return True, {"plan_id": plan_id, "joined_troops": joined, "message": f"成功加入 {len(joined)} 支部队"}


def leave_assembly(user_id, plan_id, troop_ids):
    plan = assembly_plans.get(plan_id)
    if plan is None:
        return False, "集结计划不存在"

    if not troop_ids or not isinstance(troop_ids, list):
        return False, "请指定要退出的部队"

    left = []
    errors = []

    for tid in troop_ids:
        if tid not in plan["participants"]:
            errors.append(f"部队 {tid} 不在本集结计划中")
            continue

        pinfo = plan["participants"][tid]
        if pinfo["user_id"] != user_id:
            errors.append(f"部队 {tid} 不属于你")
            continue

        plan["participants"].pop(tid, None)
        assembly_troop_lock.pop(tid, None)
        left.append(tid)

    if errors:
        return False, "; ".join(errors)

    if not left:
        return False, "无有效部队退出"

    return True, {"plan_id": plan_id, "left_troops": left, "message": f"成功退出 {len(left)} 支部队"}


async def dispatch_assembly(user_id, plan_id, target_town_id, troop_ids, accel, custom_arrive_time, troop_accels):
    plan = assembly_plans.get(plan_id)
    if plan is None:
        return False, "集结计划不存在"

    if plan["commander_user_id"] != user_id:
        return False, "只有计划创建者才能指挥出征"

    if not troop_ids or not isinstance(troop_ids, list):
        return False, "请指定出征部队"

    source_town_id = plan["town_id"]

    if source_town_id == target_town_id:
        return False, "出发和目标城池不能相同"

    if source_town_id not in towns_cache or target_town_id not in towns_cache:
        return False, "城池不存在"

    nation_id = _get_user_nation(user_id)
    targets = get_march_targets(nation_id, source_town_id)
    target_ids = {t["town_id"] for t in targets}
    if target_town_id not in target_ids:
        return False, "目标城池不可出征"

    is_custom = bool(custom_arrive_time)

    if not is_custom and accel not in (0, 30, 50):
        return False, "无效的加速档位"

    total_distance, path = dijkstra_shortest_path(source_town_id, target_town_id)
    if total_distance is None:
        return False, "路径不存在"

    source_town = towns_cache[source_town_id]
    target_town = towns_cache[target_town_id]
    source_traffic = source_town.get("traffic", 10000)
    target_traffic = target_town.get("traffic", 10000)

    troops = []
    errors = []
    for tid in troop_ids:
        if tid not in plan["participants"]:
            errors.append(f"部队 {tid} 不在本集结计划中")
            continue

        troop = troop_cache.get(tid)
        if not troop:
            errors.append(f"部队 {tid} 不存在")
            continue

        if troop.get("status") != 1:
            errors.append(f"部队 {tid} 状态异常，无法出征")
            continue

        if troop.get("pos") != source_town_id:
            errors.append(f"部队 {tid} 不在集结城池")
            continue

        troops.append(troop)

    if errors:
        return False, "; ".join(errors)

    troop_count = len(troops)
    if troop_count == 0:
        return False, "无有效部队"

    accel_factors = {}
    now_ms = get_uptime_ms()

    if is_custom:
        target_time_ms = now_ms + int(custom_arrive_time)

        if troop_accels:
            for ta in troop_accels:
                tid = ta.get("troop_id")
                a = ta.get("accel", 0)
                if a not in (0, 30, 50):
                    return False, f"部队 {tid} 无效的加速档位 {a}"
                accel_factors[tid] = _get_accel_factor(a)
        else:
            for tid in troop_ids:
                accel_factors[tid] = ACCEL_FACTOR_NONE

        can_arrive, arrive_errors = can_troops_arrive_at_time(
            troops, source_town_id, target_town_id, target_time_ms, accel_factors
        )
        if not can_arrive:
            return False, "; ".join(arrive_errors)
    else:
        accel_factor = _get_accel_factor(accel)
        for tid in troop_ids:
            accel_factors[tid] = accel_factor
        target_time_ms = None

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
        return False, "; ".join(errors)

    for tid, status, dest, dep_time, arr_time, gx, gy, new_food in troop_updates_db:
        troop = troop_cache[tid]
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

        plan["participants"].pop(tid, None)
        assembly_troop_lock.pop(tid, None)

    from core.database import get_pool
    pool = get_pool()
    async with pool.acquire() as txn_conn:
        await txn_conn.begin()
        try:
            await batch_update_troop_march_status(troop_updates_db, conn=txn_conn)

            for tid, status, dest, dep_time, arr_time, gx, gy, new_food in troop_updates_db:
                troop = troop_cache[tid]
                general_id = troop.get("general_id")
                if general_id:
                    await update_general(general_id, {"status": 2, "dest": dest, "pos": source_town_id}, conn=txn_conn)
                    sync_cache_update(general_id, {"status": 2, "dest": dest, "pos": source_town_id})

            await txn_conn.commit()
            logger.info(f"[集结出征] 事务提交成功，{len(troop_updates_db)} 支部队出征，计划 {plan_id}")
        except Exception as e:
            await txn_conn.rollback()
            logger.exception(f"[集结出征] 事务回滚: {e}")
            return False, "出征失败，请重试"

    response_data = {
        "plan_id": plan_id,
        "source_town_id": source_town_id,
        "target_town_id": target_town_id,
        "total_distance": total_distance,
        "path_towns": path,
        "total_march_food": total_march_food,
        "is_custom_arrive": is_custom,
        "troops": troop_results,
        "remaining_troops": len(plan["participants"]),
    }
    return True, response_data


async def cancel_plans_at_town(town_id, reason):
    to_cancel = [p for p in assembly_plans.values() if p["town_id"] == town_id]
    for plan in to_cancel:
        await _cancel_plan_internal(plan, reason)


async def cancel_expired_plans():
    now = get_uptime_ms()
    expired = [p for p in assembly_plans.values() if p["end_time"] <= now]
    for plan in expired:
        await _cancel_plan_internal(plan, "集结时间已到")


def get_assembly_flag_for_town(legion_id, town_id):
    for plan in assembly_plans.values():
        if plan["legion_id"] == legion_id and plan["town_id"] == town_id:
            return plan["plan_id"]
    return None


def get_assembly_flag_for_troop(troop_id):
    return assembly_troop_lock.get(troop_id)
import logging
from server_timer.server_timer_core import get_uptime_ms
from data.global_data import (
    troop_cache, fief_cache, fief_troop_cache,
    generals_cache, user_resource_cache, town_outer_grid_cache,
)
from data.troop_data import TROOP_DATA
from troop.troop_db import (
    create_tables, get_all_troops, get_troop_by_id,
    get_troop_by_general_id, insert_troop, delete_troop, update_troop as update_troop_db,
)
from troop.troop_utils import (
    get_general_max_troop_count, calculate_max_carry_food, calculate_total_troops,
)
from general.general_db import update_general
from server_timer.server_timer_core import get_uptime_ms
from general.general_core import sync_cache_update
from general.general_utils import get_general_info
from user_resource.user_resource_db import update_user_resource_field
from fief.fief_db import upsert_fief_troop, delete_fief_troop
from towns.towns_outer.town_outer_grid_core import (
    add_troop_to_grid, remove_troop_from_grid, move_troop_on_grid,
)

logger = logging.getLogger('36ji-server')

VALID_TROOP_NAMES = {t["兵种名称"] for t in TROOP_DATA}

VALID_TARGET_TYPES = ("nearest", "highest_attack", "lowest_attack", "most_food", "most_troops", "fewest_troops")


async def init_troops():
    await create_tables()

    rows = await get_all_troops()
    troop_cache.clear()
    for row in rows:
        troop_cache[row["id"]] = dict(row)

    from troop.troop_march_utils import get_gate_position
    for troop_id, troop in troop_cache.items():
        if troop.get("status") == 2 and troop.get("dest") is not None:
            pos = troop.get("pos")
            dest = troop.get("dest")
            if pos is not None and "gate_x" not in troop:
                gate_x, gate_y = get_gate_position(pos, dest, [pos, dest])
                troop["gate_x"] = gate_x
                troop["gate_y"] = gate_y

    logger.info(f"部队模块初始化完成: {len(troop_cache)} 支部队")


def _get_fief_by_user_and_town(user_id, town_id):
    for fid, fief in fief_cache.items():
        if fief["user_id"] == user_id and fief["town_id"] == town_id:
            return fid, fief
    return None, None


def _validate_team(team):
    if not isinstance(team, list) or len(team) != 5:
        return False, "team 必须是长度为5的数组"
    for i, slot in enumerate(team):
        if slot is None:
            continue
        if not isinstance(slot, dict):
            return False, f"team[{i}] 格式错误"
        name = slot.get("兵种名称", "").strip()
        count = slot.get("数量", 0)
        if not name:
            return False, f"team[{i}] 缺少兵种名称"
        if name not in VALID_TROOP_NAMES:
            return False, f"team[{i}] 兵种名称 '{name}' 不存在"
        if not isinstance(count, int) or count <= 0:
            return False, f"team[{i}] 数量必须为正整数"
    return True, None


def _aggregate_team_troops(team):
    result = {}
    for slot in team:
        if slot is None:
            continue
        name = slot["兵种名称"]
        count = slot["数量"]
        result[name] = result.get(name, 0) + count
    return result


async def create_troop(user_id, general_id, town_id, team, food=0, grid_x=10, grid_y=9, target_type="nearest"):
    if not user_id or not general_id or not town_id:
        return False, "缺少必要参数"

    valid, err = _validate_team(team)
    if not valid:
        return False, err

    total_troops = calculate_total_troops(team)
    if total_troops <= 0:
        return False, "team 至少需要一个有效兵力"

    user_generals = generals_cache.get(user_id, [])
    general = next((g for g in user_generals if g["id"] == general_id), None)
    if general is None:
        return False, "武将不存在或不属于该用户"

    if general.get("status") != 0:
        return False, "武将当前状态无法编组"

    max_troops = get_general_max_troop_count(general)
    if total_troops > max_troops:
        return False, f"兵力超出上限，当前 {total_troops}，上限 {max_troops}"

    max_food = calculate_max_carry_food(team)
    if food > max_food:
        return False, f"粮食超出上限，当前 {food}，上限 {max_food}"

    for tid, t in troop_cache.items():
        if t["general_id"] == general_id:
            return False, "该武将已绑定部队"

    fief_id, fief = _get_fief_by_user_and_town(user_id, town_id)
    if fief_id is None:
        return False, "该城池没有封地"

    if food > 0:
        resource = user_resource_cache.get(user_id)
        if resource is None:
            return False, "用户资源不存在"
        if resource.get("grain", 0) < food:
            return False, "粮食不足"

    required = _aggregate_team_troops(team)
    current_troops = fief_troop_cache.get(fief_id, [])
    current_map = {t["troop_name"]: t["count"] for t in current_troops}

    for name, need in required.items():
        if current_map.get(name, 0) < need:
            return False, f"封地 {name} 不足，需要 {need}，当前 {current_map.get(name, 0)}"

    for name, need in required.items():
        new_count = current_map[name] - need
        if new_count > 0:
            await upsert_fief_troop(fief_id, name, new_count)
        else:
            await delete_fief_troop(fief_id, name)

    if fief_id in fief_troop_cache:
        for t in fief_troop_cache[fief_id]:
            if t["troop_name"] in required:
                t["count"] -= required[t["troop_name"]]
        fief_troop_cache[fief_id] = [
            t for t in fief_troop_cache[fief_id] if t["count"] > 0
        ]

    if food > 0:
        new_grain = resource["grain"] - food
        await update_user_resource_field(user_id, "grain", new_grain)
        if user_id in user_resource_cache:
            user_resource_cache[user_id]["grain"] = new_grain

    now = get_uptime_ms()
    data = {
        "user_id": user_id,
        "general_id": general_id,
        "team": team,
        "food": food,
        "status": 1,
        "pos": town_id,
        "dest": None,
        "dep_time": 0,
        "arrive_time": 0,
        "grid_x": grid_x,
        "grid_y": grid_y,
        "target_type": target_type,
    }
    troop_id = await insert_troop(data)
    data["id"] = troop_id
    data["create_time"] = now
    data["update_time"] = now
    troop_cache[troop_id] = data

    await update_general(general_id, {"status": 1, "pos": town_id})
    sync_cache_update(general_id, {"status": 1, "pos": town_id})

    await add_troop_to_grid(town_id, troop_id, grid_x, grid_y)

    return True, {
        "troop_id": troop_id,
        "general_id": general_id,
        "team": team,
        "food": food,
        "pos": town_id,
        "grid_x": grid_x,
        "grid_y": grid_y,
    }


async def dismiss_troop(user_id, troop_id):
    troop = troop_cache.get(troop_id)
    if troop is None:
        return False, "部队不存在"

    if troop["user_id"] != user_id:
        return False, "部队不属于该用户"

    pos = troop["pos"]
    fief_id, fief = _get_fief_by_user_and_town(user_id, pos)
    if fief_id is None:
        return False, "该城池没有封地，无法取消编组"

    returned = _aggregate_team_troops(troop["team"])
    current_troops = fief_troop_cache.get(fief_id, [])
    current_map = {t["troop_name"]: t["count"] for t in current_troops}

    for name, count in returned.items():
        new_count = current_map.get(name, 0) + count
        await upsert_fief_troop(fief_id, name, new_count)
        current_map[name] = new_count

    if fief_id in fief_troop_cache:
        fief_troop_cache[fief_id] = [
            {"troop_name": name, "count": count}
            for name, count in current_map.items() if count > 0
        ]
    else:
        fief_troop_cache[fief_id] = [
            {"troop_name": name, "count": count}
            for name, count in returned.items()
        ]

    general_id = troop["general_id"]
    food = troop.get("food", 0)

    if food > 0:
        resource = user_resource_cache.get(user_id, {})
        new_grain = resource.get("grain", 0) + food
        await update_user_resource_field(user_id, "grain", new_grain)
        if user_id in user_resource_cache:
            user_resource_cache[user_id]["grain"] = new_grain

    if general_id is not None and general_id > 0:
        await update_general(general_id, {"status": 0, "pos": None})
        sync_cache_update(general_id, {"status": 0, "pos": None})

    await delete_troop(troop_id)
    del troop_cache[troop_id]

    grid_x = troop.get("grid_x", 9)
    grid_y = troop.get("grid_y", 10)
    await remove_troop_from_grid(pos, troop_id, grid_x, grid_y)

    return True, {
        "troop_id": troop_id,
        "general_id": general_id,
        "returned_troops": [
            {"troop_name": name, "count": count}
            for name, count in returned.items()
        ],
        "returned_food": food,
    }


async def update_troop(user_id, troop_id, team, food, target_type=None):
    troop = troop_cache.get(troop_id)
    if troop is None:
        return False, "部队不存在"

    if troop["user_id"] != user_id:
        return False, "部队不属于该用户"

    status = troop.get("status", 0)
    if status == 3:
        return False, "部队正在战斗中，无法修改"

    if status not in (1, 2):
        return False, "部队当前状态无法修改"

    if target_type is not None and target_type not in VALID_TARGET_TYPES:
        return False, f"无效的目标类型: {target_type}，有效值为 {VALID_TARGET_TYPES}"

    valid, err = _validate_team(team)
    if not valid:
        return False, err

    total_troops = calculate_total_troops(team)
    if total_troops <= 0:
        return False, "team 至少需要一个有效兵力"

    general_id = troop["general_id"]
    if general_id is None or general_id <= 0:
        return False, "部队武将信息异常"

    general = get_general_info(general_id)
    if general is None:
        return False, "武将不存在"

    max_troops = get_general_max_troop_count(general)
    if total_troops > max_troops:
        return False, f"兵力超出上限，当前 {total_troops}，上限 {max_troops}"

    old_team = troop.get("team", [])
    new_aggregated = _aggregate_team_troops(team)
    old_aggregated = _aggregate_team_troops(old_team)
    is_same_composition = (new_aggregated == old_aggregated)
    old_food = troop.get("food", 0)
    food_changed = (food != old_food)

    # 情况A：兵种种类和数量不变，且粮食不变，仅调整槽位分布/攻击目标
    # 适用于驻守中(status=1)和行进中(status=2)
    if is_same_composition and not food_changed:
        now = get_uptime_ms()
        updates = {"team": team}
        if target_type is not None:
            updates["target_type"] = target_type
        await update_troop_db(troop_id, updates)
        troop["team"] = team
        if target_type is not None:
            troop["target_type"] = target_type
        troop["update_time"] = now

        return True, {
            "troop_id": troop_id,
            "team": team,
            "food": troop["food"],
            "target_type": troop.get("target_type", "nearest"),
            "food_delta": 0,
            "troop_deltas": {},
        }

    # 情况B：兵种种类或数量有变化，或粮食有变化
    if status == 2:
        return False, "行军中的部队兵种种类和粮食无法改变"

    # 驻守中(status=1)，需要封地资源检查
    max_food = calculate_max_carry_food(team)
    if food > max_food:
        return False, f"粮食超出上限，当前 {food}，上限 {max_food}"

    pos = troop["pos"]
    fief_id, fief = _get_fief_by_user_and_town(user_id, pos)
    if fief_id is None:
        return False, "该城池没有封地"

    food_delta = food - old_food

    if food_delta > 0:
        resource = user_resource_cache.get(user_id)
        if resource is None:
            return False, "用户资源不存在"
        if resource.get("grain", 0) < food_delta:
            return False, f"粮食不足，需要额外 {food_delta}，当前 {resource.get('grain', 0)}"
        new_grain = resource["grain"] - food_delta
        await update_user_resource_field(user_id, "grain", new_grain)
        if user_id in user_resource_cache:
            user_resource_cache[user_id]["grain"] = new_grain
    elif food_delta < 0:
        resource = user_resource_cache.get(user_id, {})
        new_grain = resource.get("grain", 0) + abs(food_delta)
        await update_user_resource_field(user_id, "grain", new_grain)
        if user_id in user_resource_cache:
            user_resource_cache[user_id]["grain"] = new_grain

    new_required = new_aggregated
    old_required = old_aggregated

    current_troops = fief_troop_cache.get(fief_id, [])
    current_map = {t["troop_name"]: t["count"] for t in current_troops}

    all_names = set(list(new_required.keys()) + list(old_required.keys()))
    troop_deltas = {}
    for name in all_names:
        new_count = new_required.get(name, 0)
        old_count = old_required.get(name, 0)
        delta = new_count - old_count
        troop_deltas[name] = delta

        if delta > 0:
            if current_map.get(name, 0) < delta:
                return False, f"封地 {name} 不足，需要额外 {delta}，当前 {current_map.get(name, 0)}"

    for name, delta in troop_deltas.items():
        if delta != 0:
            new_count = current_map.get(name, 0) - delta
            if new_count > 0:
                await upsert_fief_troop(fief_id, name, new_count)
            else:
                await delete_fief_troop(fief_id, name)

    if fief_id in fief_troop_cache:
        for name, delta in troop_deltas.items():
            if delta != 0:
                for t in fief_troop_cache[fief_id]:
                    if t["troop_name"] == name:
                        t["count"] -= delta
        fief_troop_cache[fief_id] = [
            t for t in fief_troop_cache[fief_id] if t["count"] > 0
        ]

    now = get_uptime_ms()
    updates = {
        "team": team,
        "food": food,
    }
    if target_type is not None:
        updates["target_type"] = target_type
    await update_troop_db(troop_id, updates)
    troop["team"] = team
    troop["food"] = food
    if target_type is not None:
        troop["target_type"] = target_type
    troop["update_time"] = now

    return True, {
        "troop_id": troop_id,
        "team": team,
        "food": food,
        "target_type": troop.get("target_type", "nearest"),
        "food_delta": food_delta,
        "troop_deltas": {k: v for k, v in troop_deltas.items() if v != 0},
    }


def get_user_troop_list(user_id):
    result = []
    for tid, troop in troop_cache.items():
        if troop["user_id"] == user_id:
            result.append(dict(troop))
    return result


def get_troop_detail(troop_id):
    return troop_cache.get(troop_id)


async def move_troop(user_id, troop_id, new_grid_x, new_grid_y):
    troop = troop_cache.get(troop_id)
    if troop is None:
        return False, "部队不存在"

    if troop["user_id"] != user_id:
        return False, "部队不属于该用户"

    if troop.get("status") != 1:
        return False, "部队当前状态无法移动"

    old_grid_x = troop.get("grid_x")
    old_grid_y = troop.get("grid_y")
    town_id = troop.get("pos")

    if old_grid_x is None or old_grid_y is None or town_id is None:
        return False, "部队坐标或城池信息缺失"

    success, err = await move_troop_on_grid(
        town_id, troop_id, old_grid_x, old_grid_y, new_grid_x, new_grid_y
    )
    if not success:
        return False, err

    await update_troop_db(troop_id, {"grid_x": new_grid_x, "grid_y": new_grid_y})
    troop["grid_x"] = new_grid_x
    troop["grid_y"] = new_grid_y

    return True, {
        "troop_id": troop_id,
        "from_grid": (old_grid_x, old_grid_y),
        "to_grid": (new_grid_x, new_grid_y),
    }


async def swap_troops(user_id, troop_id_a, team_a, food_a, troop_id_b, team_b, food_b):
    if troop_id_a == troop_id_b:
        return False, "不能与同一支部队交换"

    troop_a = troop_cache.get(troop_id_a)
    troop_b = troop_cache.get(troop_id_b)

    if troop_a is None or troop_b is None:
        return False, "部队不存在"

    if troop_a["user_id"] != user_id or troop_b["user_id"] != user_id:
        return False, "部队不属于该用户"

    if troop_a.get("status") != 1 or troop_b.get("status") != 1:
        return False, "部队当前状态无法交换"

    if troop_a["pos"] != troop_b["pos"]:
        return False, "两支部队不在同一城池"

    valid_a, err_a = _validate_team(team_a)
    if not valid_a:
        return False, f"部队A: {err_a}"

    valid_b, err_b = _validate_team(team_b)
    if not valid_b:
        return False, f"部队B: {err_b}"

    total_a = calculate_total_troops(team_a)
    total_b = calculate_total_troops(team_b)
    if total_a == 0 and total_b == 0:
        return False, "交换后双方不能同时为空"

    old_aggregate = _aggregate_team_troops(troop_a["team"])
    old_b = _aggregate_team_troops(troop_b["team"])
    for name, count in old_b.items():
        old_aggregate[name] = old_aggregate.get(name, 0) + count

    new_aggregate = _aggregate_team_troops(team_a)
    new_b = _aggregate_team_troops(team_b)
    for name, count in new_b.items():
        new_aggregate[name] = new_aggregate.get(name, 0) + count

    if old_aggregate != new_aggregate:
        return False, "交换前后兵力不一致"

    old_total_food = troop_a.get("food", 0) + troop_b.get("food", 0)
    new_total_food = food_a + food_b
    if old_total_food != new_total_food:
        return False, "交换前后粮草不一致"

    town_id = troop_a["pos"]

    if total_a > 0:
        general_a = get_general_info(troop_a["general_id"])
        if general_a is None:
            return False, "部队A武将不存在"
        max_troops_a = get_general_max_troop_count(general_a)
        if total_a > max_troops_a:
            return False, f"部队A兵力超出上限，当前 {total_a}，上限 {max_troops_a}"
        max_food_a = calculate_max_carry_food(team_a)
        if food_a > max_food_a:
            return False, f"部队A粮草超出上限，当前 {food_a}，上限 {max_food_a}"

    if total_b > 0:
        general_b = get_general_info(troop_b["general_id"])
        if general_b is None:
            return False, "部队B武将不存在"
        max_troops_b = get_general_max_troop_count(general_b)
        if total_b > max_troops_b:
            return False, f"部队B兵力超出上限，当前 {total_b}，上限 {max_troops_b}"
        max_food_b = calculate_max_carry_food(team_b)
        if food_b > max_food_b:
            return False, f"部队B粮草超出上限，当前 {food_b}，上限 {max_food_b}"

    now = get_uptime_ms()
    result = {}

    if total_a == 0:
        general_id_a = troop_a["general_id"]
        grid_x_a = troop_a.get("grid_x")
        grid_y_a = troop_a.get("grid_y")

        await delete_troop(troop_id_a)
        del troop_cache[troop_id_a]

        await update_general(general_id_a, {"status": 0, "pos": None})
        sync_cache_update(general_id_a, {"status": 0, "pos": None})

        if grid_x_a is not None and grid_y_a is not None:
            await remove_troop_from_grid(town_id, troop_id_a, grid_x_a, grid_y_a)

        result["troop_a"] = {"troop_id": troop_id_a, "dismissed": True, "general_id": general_id_a}

        await update_troop_db(troop_id_b, {"team": team_b, "food": food_b})
        troop_b["team"] = team_b
        troop_b["food"] = food_b
        troop_b["update_time"] = now

        result["troop_b"] = {
            "troop_id": troop_id_b,
            "general_id": troop_b["general_id"],
            "team": team_b,
            "food": food_b,
        }

    elif total_b == 0:
        general_id_b = troop_b["general_id"]
        grid_x_b = troop_b.get("grid_x")
        grid_y_b = troop_b.get("grid_y")

        await delete_troop(troop_id_b)
        del troop_cache[troop_id_b]

        await update_general(general_id_b, {"status": 0, "pos": None})
        sync_cache_update(general_id_b, {"status": 0, "pos": None})

        if grid_x_b is not None and grid_y_b is not None:
            await remove_troop_from_grid(town_id, troop_id_b, grid_x_b, grid_y_b)

        result["troop_b"] = {"troop_id": troop_id_b, "dismissed": True, "general_id": general_id_b}

        await update_troop_db(troop_id_a, {"team": team_a, "food": food_a})
        troop_a["team"] = team_a
        troop_a["food"] = food_a
        troop_a["update_time"] = now

        result["troop_a"] = {
            "troop_id": troop_id_a,
            "general_id": troop_a["general_id"],
            "team": team_a,
            "food": food_a,
        }

    else:
        await update_troop_db(troop_id_a, {"team": team_a, "food": food_a})
        troop_a["team"] = team_a
        troop_a["food"] = food_a
        troop_a["update_time"] = now

        await update_troop_db(troop_id_b, {"team": team_b, "food": food_b})
        troop_b["team"] = team_b
        troop_b["food"] = food_b
        troop_b["update_time"] = now

        result["troop_a"] = {
            "troop_id": troop_id_a,
            "general_id": troop_a["general_id"],
            "team": team_a,
            "food": food_a,
        }
        result["troop_b"] = {
            "troop_id": troop_id_b,
            "general_id": troop_b["general_id"],
            "team": team_b,
            "food": food_b,
        }

    return True, result
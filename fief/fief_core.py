import math
import time
import logging
from data.global_data import (
    fief_cache, fief_troop_cache, fief_income_accumulated,
    towns_cache, user_resource_cache, nation_cache, user_nation_cache,
    fief_item_effects_cache,
)
from data.fief_building_config import (
    BUILDING_CONFIG, BUILDABLE_BUILDINGS, RESOURCE_BUILDINGS,
    BARRACK_BUILDINGS, BARRACK_TROOP_MAP,
    GRID_COLS, GRID_ROWS, INVALID_CELLS,
    DEFAULT_FIEF_BUILDINGS, MAX_FIEF_PER_USER,
)
from data.fief_building_level_data import BUILDING_LEVEL_DATA
from data.troop_data import TROOP_DATA, TROOP_DATA1
from fief.fief_db import (
    create_tables, get_all_fiefs, get_all_fief_troops,
    insert_fief, update_fief_grid_data, update_fief_name, delete_fief,
    upsert_fief_troop, delete_fief_troops, insert_fief_destroy_log,
)
from user_resource.user_resource_db import update_user_resource_field
from server_timer.server_timer_core import get_uptime_ms
from core.connection import broadcast
from message.protocol import make_response

logger = logging.getLogger('36ji-server')


def _create_empty_grid():
    grid = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            unlocked = _is_basic_cell(row, col)
            grid.append({
                "has_building": False,
                "type": "空地",
                "level": 0,
                "desc": "",
                "unlocked": unlocked,
                "is_building": False,
                "build_remain_time": 0,
                "build_start_time": 0,
                "is_training": False,
                "train_remain_time": 0,
                "train_start_time": 0,
                "train_single_time": 0,
                "training_troop_name": "",
                "training_troop_count": 0,
            })
    return grid


def _grid_index(row, col):
    return row * GRID_COLS + col


def _get_cell(grid_data, row, col):
    return grid_data[_grid_index(row, col)]


def _is_basic_cell(row, col):
    return 1 <= row <= 4 and 1 <= col <= 4


def _is_extended_cell(row, col):
    if _is_basic_cell(row, col):
        return False
    if (row, col) in INVALID_CELLS:
        return False
    return 0 <= row < GRID_ROWS and 0 <= col < GRID_COLS


def _is_valid_cell(row, col):
    return (row, col) not in INVALID_CELLS


def _find_lord_hall(grid_data):
    for cell in grid_data:
        if cell["type"] == "城主府" and cell["has_building"] and not cell["is_building"]:
            return cell
    return None


def _find_military_platform(grid_data):
    for cell in grid_data:
        if cell["type"] == "军乐台" and cell["has_building"] and not cell["is_building"]:
            return cell
    return None


def _count_building_type(grid_data, building_type):
    count = 0
    for cell in grid_data:
        if cell["type"] == building_type and cell["has_building"]:
            count += 1
    return count


def _get_lord_hall_effect(grid_data):
    cell = _find_lord_hall(grid_data)
    if cell and cell["has_building"]:
        level = cell["level"]
        if level > 0:
            return BUILDING_LEVEL_DATA["城主府"][level]["专属效果值"]
    return 0.0


def _calculate_actual_build_time(original_time, lord_hall_effect):
    if lord_hall_effect >= 1.0:
        return 0
    return max(1, int(original_time * (1.0 - lord_hall_effect)))


def _calculate_actual_train_time(original_time, grid_data, barrack_row, barrack_col):
    military_platform = _find_military_platform(grid_data)
    platform_effect = 0.0
    if military_platform:
        level = military_platform["level"]
        if level > 0:
            platform_effect = BUILDING_LEVEL_DATA["军乐台"][level]["专属效果值"]

    barrack_cell = _get_cell(grid_data, barrack_row, barrack_col)
    barrack_effect = 0.0
    if barrack_cell["has_building"] and barrack_cell["level"] > 0:
        barrack_effect = BUILDING_LEVEL_DATA[barrack_cell["type"]][barrack_cell["level"]]["专属效果值"]

    actual_time = original_time * (1.0 - platform_effect) * (1.0 - barrack_effect)
    return max(1, int(actual_time))


def _calculate_fief_income(grid_data, fief_id=None):
    income = {"wood": 0.0, "grain": 0.0, "iron": 0.0, "copper": 0.0}

    forest_coef = 1.0
    fertile_coef = 1.0
    mine_coef = 1.0
    pearl_bonus = 0.0

    if fief_id:
        fief = fief_cache.get(fief_id)
        if fief:
            town = towns_cache.get(fief.get("town_id"))
            if town:
                # 灵珠加成：只有城池等级≤3才生效，且通过缓存获取该玩家在该城池的bonus
                if town.get("level", 1) <= 3:
                    pearl_bonus = fief_item_effects_cache.get(
                        (fief["user_id"], fief.get("town_id")), 0.0
                    )
                forest_coef = float(town.get("forest", 1.0)) + pearl_bonus
                fertile_coef = float(town.get("fertile", 1.0)) + pearl_bonus
                mine_coef = float(town.get("mine", 1.0)) + pearl_bonus

    for cell in grid_data:
        if cell["has_building"] and not cell["is_building"] and cell["type"] in RESOURCE_BUILDINGS:
            level = cell["level"]
            if level > 0:
                effect = BUILDING_LEVEL_DATA[cell["type"]][level]["专属效果值"]
                if cell["type"] == "林场":
                    income["wood"] += effect * forest_coef
                elif cell["type"] == "农场":
                    income["grain"] += effect * 1.1 * fertile_coef
                elif cell["type"] == "矿场":
                    income["iron"] += effect * 1.2 * mine_coef
                elif cell["type"] == "民户":
                    income["copper"] += effect
    return income


def _can_build(count, max_count):
    if max_count == -1:
        return True
    return count < max_count


def _validate_user_nation_town(user_id, town_id):
    town = towns_cache.get(town_id)
    if not town:
        return False, "城池不存在"

    town_owner = town.get("owner", 1)
    if town_owner == 1:
        return False, "该城池归属山贼集团，无法创建封地"

    user_nation = _get_user_nation_id(user_id)
    if not user_nation:
        return False, "用户未选择国家"

    if user_nation != town_owner:
        return False, "该城池不属于你的国家"

    return True, town_owner


async def _check_fief_limit(user_id):
    from tech.tech_core import get_fief_limit, ensure_tech
    await ensure_tech(user_id)
    limit = get_fief_limit(user_id)
    count = sum(1 for f in fief_cache.values() if f["user_id"] == user_id)
    return count < limit, count, limit


def _check_same_town(user_id, town_id):
    for f in fief_cache.values():
        if f["user_id"] == user_id and f["town_id"] == town_id:
            return True
    return False


def _get_user_nation_id(user_id):
    return user_nation_cache.get(user_id)


def _get_l1_towns_for_nation(nation_id):
    l1_towns = []
    for town_id, town in towns_cache.items():
        if town.get("level") == 1 and town.get("owner") == nation_id:
            l1_towns.append({
                "town_id": town_id,
                "name": town["name"],
                "pos_x": town["pos_x"],
                "pos_y": town["pos_y"],
            })
    return l1_towns


async def init_fiefs():
    await create_tables()

    rows = await get_all_fiefs()
    fief_cache.clear()
    for row in rows:
        fief_cache[row["id"]] = dict(row)

    troop_rows = await get_all_fief_troops()
    fief_troop_cache.clear()
    for row in troop_rows:
        fid = row["fief_id"]
        if fid not in fief_troop_cache:
            fief_troop_cache[fid] = []
        fief_troop_cache[fid].append({
            "troop_name": row["troop_name"],
            "count": row["count"],
        })

    fief_income_accumulated.clear()
    for fid in fief_cache:
        fief_income_accumulated[fid] = {"wood": 0.0, "grain": 0.0, "iron": 0.0, "copper": 0.0}

    logger.info(f"封地模块初始化完成: {len(fief_cache)} 个封地, {len(fief_troop_cache)} 个封地有兵力")


def get_initial_l1_towns(user_id):
    nation_id = _get_user_nation_id(user_id)
    if not nation_id:
        return None, "用户未选择国家"
    towns = _get_l1_towns_for_nation(nation_id)
    return towns, None


def get_user_fief_list(user_id):
    result = []
    for fid, fief in fief_cache.items():
        if fief["user_id"] == user_id:
            town = towns_cache.get(fief["town_id"])
            result.append({
                "fief_id": fid,
                "town_id": fief["town_id"],
                "town_name": town["name"] if town else "",
                "fief_name": fief.get("name", ""),
                "nation_id": fief["nation_id"],
                "create_time": str(fief["create_time"]) if fief["create_time"] else "",
            })
    return result


def get_fief_detail(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return None, "封地不存在"

    income = _calculate_fief_income(fief["grid_data"], fief_id)
    troops = fief_troop_cache.get(fief_id, [])

    return {
        "fief_id": fief_id,
        "user_id": fief["user_id"],
        "town_id": fief["town_id"],
        "nation_id": fief["nation_id"],
        "name": fief.get("name", ""),
        "grid_data": fief["grid_data"],
        "income": income,
        "troops": troops,
    }, None


def get_fief_by_user_and_town(user_id, town_id):
    for fid, fief in fief_cache.items():
        if fief["user_id"] == user_id and fief["town_id"] == town_id:
            return get_fief_detail(fid)
    return None, "该城池没有封地"


def get_fief_building_detail(fief_id, row, col):
    fief = fief_cache.get(fief_id)
    if not fief:
        return None, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return None, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return None, "无效的网格坐标"

    cell = _get_cell(fief["grid_data"], row, col)
    return {
        "fief_id": fief_id,
        "row": row,
        "col": col,
        "cell": cell,
    }, None


async def create_initial_fief(user_id, town_id):
    valid, nation_or_msg = _validate_user_nation_town(user_id, town_id)
    if not valid:
        return False, nation_or_msg
    nation_id = nation_or_msg

    if _check_same_town(user_id, town_id):
        return False, "该城池已存在封地"

    within_limit, count, limit = await _check_fief_limit(user_id)
    if not within_limit:
        return False, f"封地数量已达上限({limit}个)，请升级列土封疆科技"

    grid_data = _create_empty_grid()
    for row, col, building_type, level in DEFAULT_FIEF_BUILDINGS:
        idx = _grid_index(row, col)
        config = BUILDING_CONFIG[building_type]
        grid_data[idx]["has_building"] = True
        grid_data[idx]["type"] = building_type
        grid_data[idx]["level"] = level
        grid_data[idx]["desc"] = config["desc"]

    town = towns_cache.get(town_id, {})
    fief_name = f"{town.get('name', '')}封地" if town.get("name") else "封地"
    fief_id = await insert_fief(user_id, town_id, nation_id, grid_data, fief_name)
    fief_cache[fief_id] = {
        "id": fief_id,
        "user_id": user_id,
        "town_id": town_id,
        "nation_id": nation_id,
        "name": fief_name,
        "grid_data": grid_data,
        "create_time": str(time.strftime("%Y-%m-%d %H:%M:%S")),
        "update_time": str(time.strftime("%Y-%m-%d %H:%M:%S")),
    }
    fief_troop_cache[fief_id] = []
    fief_income_accumulated[fief_id] = {"wood": 0.0, "grain": 0.0, "iron": 0.0, "copper": 0.0}

    for troop in TROOP_DATA1:
        name = troop["兵种名称"]
        count = troop["数量"]
        await upsert_fief_troop(fief_id, name, count)
        fief_troop_cache[fief_id].append({"troop_name": name, "count": count})

    return True, {"fief_id": fief_id, "grid_data": grid_data}


async def create_fief(user_id, town_id):
    valid, nation_or_msg = _validate_user_nation_town(user_id, town_id)
    if not valid:
        return False, nation_or_msg
    nation_id = nation_or_msg

    if _check_same_town(user_id, town_id):
        return False, "该城池已存在封地"

    within_limit, count, limit = await _check_fief_limit(user_id)
    if not within_limit:
        return False, f"封地数量已达上限({limit}个)，请升级列土封疆科技"

    grid_data = _create_empty_grid()
    town = towns_cache.get(town_id, {})
    fief_name = f"{town.get('name', '')}封地" if town.get("name") else "封地"
    fief_id = await insert_fief(user_id, town_id, nation_id, grid_data, fief_name)
    fief_cache[fief_id] = {
        "id": fief_id,
        "user_id": user_id,
        "town_id": town_id,
        "nation_id": nation_id,
        "name": fief_name,
        "grid_data": grid_data,
        "create_time": str(time.strftime("%Y-%m-%d %H:%M:%S")),
        "update_time": str(time.strftime("%Y-%m-%d %H:%M:%S")),
    }
    fief_troop_cache[fief_id] = []
    fief_income_accumulated[fief_id] = {"wood": 0.0, "grain": 0.0, "iron": 0.0, "copper": 0.0}

    return True, {"fief_id": fief_id, "grid_data": grid_data}


async def build_building(fief_id, row, col, building_type):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return False, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return False, "无效的网格坐标"

    if building_type not in BUILDABLE_BUILDINGS:
        return False, "无效的建筑类型"

    if building_type == "空地":
        return False, "不能建造空地"

    grid_data = fief["grid_data"]
    cell = _get_cell(grid_data, row, col)

    if not cell["unlocked"]:
        return False, "该网格未解锁"

    if cell["has_building"] or cell["is_building"]:
        return False, "该网格已有建筑或正在建造"

    if building_type == "城主府":
        if _count_building_type(grid_data, "城主府") >= 1:
            return False, "城主府只能建造一个"
    else:
        if not _find_lord_hall(grid_data):
            return False, "需要先建造城主府"

    config = BUILDING_CONFIG[building_type]
    current_count = _count_building_type(grid_data, building_type)
    if not _can_build(current_count, config["max_count"]):
        return False, f"{building_type}已达到最大数量({config['max_count']})"

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    level_data = BUILDING_LEVEL_DATA[building_type][1]
    wood_cost = level_data["所需木材"]
    grain_cost = level_data["所需粮食"]
    iron_cost = level_data["所需铁矿"]

    if user_resource["wood"] < wood_cost:
        return False, "木材不足"
    if user_resource["grain"] < grain_cost:
        return False, "粮食不足"
    if user_resource["iron"] < iron_cost:
        return False, "铁矿不足"

    lord_hall_effect = _get_lord_hall_effect(grid_data)
    actual_time = _calculate_actual_build_time(level_data["所需时间"], lord_hall_effect)

    user_resource["wood"] -= wood_cost
    user_resource["grain"] -= grain_cost
    user_resource["iron"] -= iron_cost
    await update_user_resource_field(user_id, "wood", user_resource["wood"])
    await update_user_resource_field(user_id, "grain", user_resource["grain"])
    await update_user_resource_field(user_id, "iron", user_resource["iron"])

    now = get_uptime_ms() // 1000
    idx = _grid_index(row, col)
    grid_data[idx]["type"] = building_type
    grid_data[idx]["level"] = 0
    grid_data[idx]["desc"] = config["desc"]
    grid_data[idx]["is_building"] = True
    grid_data[idx]["build_remain_time"] = actual_time
    grid_data[idx]["build_start_time"] = now

    await update_fief_grid_data(fief_id, grid_data)

    return True, {"cell": grid_data[idx], "cost": {"wood": wood_cost, "grain": grain_cost, "iron": iron_cost}}


async def upgrade_building(fief_id, row, col):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return False, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return False, "无效的网格坐标"

    grid_data = fief["grid_data"]
    cell = _get_cell(grid_data, row, col)

    if not cell["has_building"]:
        return False, "该网格没有建筑"

    if cell["is_building"]:
        return False, "该建筑正在建造/升级中"

    if cell["is_training"]:
        return False, "该兵营正在训练中"

    building_type = cell["type"]
    if building_type == "空地":
        return False, "空地无法升级"

    config = BUILDING_CONFIG[building_type]
    current_level = cell["level"]
    if current_level >= config["max_level"]:
        return False, "建筑已满级"

    next_level = current_level + 1
    level_data = BUILDING_LEVEL_DATA[building_type][next_level]
    wood_cost = level_data["所需木材"]
    grain_cost = level_data["所需粮食"]
    iron_cost = level_data["所需铁矿"]

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    if user_resource["wood"] < wood_cost:
        return False, "木材不足"
    if user_resource["grain"] < grain_cost:
        return False, "粮食不足"
    if user_resource["iron"] < iron_cost:
        return False, "铁矿不足"

    lord_hall_effect = _get_lord_hall_effect(grid_data)
    actual_time = _calculate_actual_build_time(level_data["所需时间"], lord_hall_effect)

    user_resource["wood"] -= wood_cost
    user_resource["grain"] -= grain_cost
    user_resource["iron"] -= iron_cost
    await update_user_resource_field(user_id, "wood", user_resource["wood"])
    await update_user_resource_field(user_id, "grain", user_resource["grain"])
    await update_user_resource_field(user_id, "iron", user_resource["iron"])

    now = get_uptime_ms() // 1000
    idx = _grid_index(row, col)
    grid_data[idx]["is_building"] = True
    grid_data[idx]["build_remain_time"] = actual_time
    grid_data[idx]["build_start_time"] = now

    await update_fief_grid_data(fief_id, grid_data)

    return True, {"cell": grid_data[idx], "cost": {"wood": wood_cost, "grain": grain_cost, "iron": iron_cost}}


async def cancel_build(fief_id, row, col):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return False, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return False, "无效的网格坐标"

    grid_data = fief["grid_data"]
    cell = _get_cell(grid_data, row, col)

    if not cell["is_building"]:
        return False, "该建筑没有在建造/升级中"

    building_type = cell["type"]
    is_building_new = not cell["has_building"]

    if is_building_new:
        target_level = 0
    else:
        target_level = cell["level"]

    if target_level == 0:
        level_data = BUILDING_LEVEL_DATA[building_type][1]
    else:
        level_data = BUILDING_LEVEL_DATA[building_type][target_level]

    wood_return = level_data["所需木材"] // 2
    grain_return = level_data["所需粮食"] // 2
    iron_return = level_data["所需铁矿"] // 2

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if user_resource:
        user_resource["wood"] += wood_return
        user_resource["grain"] += grain_return
        user_resource["iron"] += iron_return
        await update_user_resource_field(user_id, "wood", user_resource["wood"])
        await update_user_resource_field(user_id, "grain", user_resource["grain"])
        await update_user_resource_field(user_id, "iron", user_resource["iron"])

    idx = _grid_index(row, col)
    if is_building_new:
        grid_data[idx] = {
            "has_building": False,
            "type": "空地",
            "level": 0,
            "desc": "",
            "unlocked": cell["unlocked"],
            "is_building": False,
            "build_remain_time": 0,
            "build_start_time": 0,
            "is_training": False,
            "train_remain_time": 0,
            "train_start_time": 0,
            "train_single_time": 0,
            "training_troop_name": "",
            "training_troop_count": 0,
        }
    else:
        grid_data[idx]["is_building"] = False
        grid_data[idx]["build_remain_time"] = 0
        grid_data[idx]["build_start_time"] = 0

    await update_fief_grid_data(fief_id, grid_data)

    return True, {
        "cell": grid_data[idx],
        "returned": {"wood": wood_return, "grain": grain_return, "iron": iron_return}
    }


async def demolish_building(fief_id, row, col):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return False, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return False, "无效的网格坐标"

    grid_data = fief["grid_data"]
    cell = _get_cell(grid_data, row, col)

    if not cell["has_building"]:
        return False, "该网格没有建筑"

    if cell["is_building"]:
        return False, "该建筑正在建造/升级中，请先取消"

    if cell["is_training"]:
        return False, "该兵营正在训练中，无法拆除"

    building_type = cell["type"]
    config = BUILDING_CONFIG[building_type]
    if not config["can_demolish"]:
        return False, f"{building_type}不可拆除"

    current_level = cell["level"]
    total_wood = 0
    total_grain = 0
    total_iron = 0
    for lv in range(1, current_level + 1):
        ld = BUILDING_LEVEL_DATA[building_type][lv]
        total_wood += ld["所需木材"]
        total_grain += ld["所需粮食"]
        total_iron += ld["所需铁矿"]

    wood_return = total_wood // 2
    grain_return = total_grain // 2
    iron_return = total_iron // 2

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if user_resource:
        user_resource["wood"] += wood_return
        user_resource["grain"] += grain_return
        user_resource["iron"] += iron_return
        await update_user_resource_field(user_id, "wood", user_resource["wood"])
        await update_user_resource_field(user_id, "grain", user_resource["grain"])
        await update_user_resource_field(user_id, "iron", user_resource["iron"])

    idx = _grid_index(row, col)
    grid_data[idx] = {
        "has_building": False,
        "type": "空地",
        "level": 0,
        "desc": "",
        "unlocked": cell["unlocked"],
        "is_building": False,
        "build_remain_time": 0,
        "build_start_time": 0,
        "is_training": False,
        "train_remain_time": 0,
        "train_start_time": 0,
        "train_single_time": 0,
        "training_troop_name": "",
        "training_troop_count": 0,
    }

    await update_fief_grid_data(fief_id, grid_data)

    return True, {
        "cell": grid_data[idx],
        "returned": {"wood": wood_return, "grain": grain_return, "iron": iron_return}
    }


async def upgrade_all_same_type(fief_id, building_type):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if building_type not in BUILDABLE_BUILDINGS or building_type == "空地":
        return False, "无效的建筑类型"

    config = BUILDING_CONFIG[building_type]
    grid_data = fief["grid_data"]
    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    cells_to_upgrade = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell = _get_cell(grid_data, row, col)
            if (cell["type"] == building_type and cell["has_building"]
                    and not cell["is_building"] and not cell["is_training"]
                    and cell["level"] < config["max_level"]):
                cells_to_upgrade.append((row, col, cell["level"]))

    cells_to_upgrade.sort(key=lambda x: x[2])

    lord_hall_effect = _get_lord_hall_effect(grid_data)
    now = get_uptime_ms() // 1000
    upgraded = []
    total_cost = {"wood": 0, "grain": 0, "iron": 0}

    for row, col, current_level in cells_to_upgrade:
        next_level = current_level + 1
        level_data = BUILDING_LEVEL_DATA[building_type][next_level]
        wood_cost = level_data["所需木材"]
        grain_cost = level_data["所需粮食"]
        iron_cost = level_data["所需铁矿"]

        if (user_resource["wood"] < total_cost["wood"] + wood_cost
                or user_resource["grain"] < total_cost["grain"] + grain_cost
                or user_resource["iron"] < total_cost["iron"] + iron_cost):
            break

        total_cost["wood"] += wood_cost
        total_cost["grain"] += grain_cost
        total_cost["iron"] += iron_cost

        actual_time = _calculate_actual_build_time(level_data["所需时间"], lord_hall_effect)

        idx = _grid_index(row, col)
        grid_data[idx]["is_building"] = True
        grid_data[idx]["build_remain_time"] = actual_time
        grid_data[idx]["build_start_time"] = now
        upgraded.append({"row": row, "col": col, "from_level": current_level, "to_level": next_level})

    if not upgraded:
        return False, "没有可升级的建筑或资源不足"

    user_resource["wood"] -= total_cost["wood"]
    user_resource["grain"] -= total_cost["grain"]
    user_resource["iron"] -= total_cost["iron"]
    await update_user_resource_field(user_id, "wood", user_resource["wood"])
    await update_user_resource_field(user_id, "grain", user_resource["grain"])
    await update_user_resource_field(user_id, "iron", user_resource["iron"])

    await update_fief_grid_data(fief_id, grid_data)

    return True, {"upgraded": upgraded, "total_cost": total_cost}


async def unlock_grid(fief_id, row, col):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return False, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return False, "无效的网格坐标"

    if _is_basic_cell(row, col):
        return False, "基础网格无需解锁"

    grid_data = fief["grid_data"]
    cell = _get_cell(grid_data, row, col)

    if cell["unlocked"]:
        return False, "该网格已解锁"

    unlocked_count = 0
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            if _is_extended_cell(r, c) and _get_cell(grid_data, r, c)["unlocked"]:
                unlocked_count += 1

    if unlocked_count < 4:
        gold_cost = 50
    elif unlocked_count < 8:
        gold_cost = 100
    elif unlocked_count < 12:
        gold_cost = 200
    else:
        gold_cost = 500

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    if user_resource["gold"] < gold_cost:
        return False, f"黄金不足，需要{gold_cost}黄金"

    user_resource["gold"] -= gold_cost
    await update_user_resource_field(user_id, "gold", user_resource["gold"])

    idx = _grid_index(row, col)
    grid_data[idx]["unlocked"] = True

    await update_fief_grid_data(fief_id, grid_data)

    return True, {"cell": grid_data[idx], "gold_cost": gold_cost}


async def train_troop(fief_id, row, col, troop_name, count):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
        return False, "网格坐标越界"

    if not _is_valid_cell(row, col):
        return False, "无效的网格坐标"

    grid_data = fief["grid_data"]
    cell = _get_cell(grid_data, row, col)

    if not cell["has_building"]:
        return False, "该网格没有建筑"

    if cell["is_building"]:
        return False, "该建筑正在建造/升级中"

    if cell["is_training"]:
        return False, "该兵营正在训练中"

    building_type = cell["type"]
    if building_type not in BARRACK_BUILDINGS:
        return False, "该建筑不是兵营，无法训练"

    troop_data = None
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            troop_data = t
            break
    if not troop_data:
        return False, "无效的兵种名称"

    if troop_data["兵种系列"] != BARRACK_TROOP_MAP[building_type]:
        return False, f"{building_type}只能训练{BARRACK_TROOP_MAP[building_type]}兵种"

    if count <= 0:
        return False, "训练数量必须大于0"

    if count > 100:
        return False, "单次训练数量不能超过100"

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    wood_per = troop_data["训练耗费木材"]
    grain_per = troop_data["训练耗费粮食"]
    iron_per = troop_data["训练耗费铁矿"]
    time_per = troop_data["训练耗费时间（秒）"]

    total_wood = wood_per * count
    total_grain = grain_per * count
    total_iron = iron_per * count

    if user_resource["wood"] < total_wood:
        return False, "木材不足"
    if user_resource["grain"] < total_grain:
        return False, "粮食不足"
    if user_resource["iron"] < total_iron:
        return False, "铁矿不足"

    actual_train_time = _calculate_actual_train_time(time_per, grid_data, row, col)
    total_train_time = actual_train_time * count

    user_resource["wood"] -= total_wood
    user_resource["grain"] -= total_grain
    user_resource["iron"] -= total_iron
    await update_user_resource_field(user_id, "wood", user_resource["wood"])
    await update_user_resource_field(user_id, "grain", user_resource["grain"])
    await update_user_resource_field(user_id, "iron", user_resource["iron"])

    dev_score = _calc_development_score(total_wood, total_grain, total_iron)
    from mission.mission_core import add_development_score
    await add_development_score(user_id, dev_score)

    now = get_uptime_ms() // 1000
    idx = _grid_index(row, col)
    grid_data[idx]["is_training"] = True
    grid_data[idx]["train_remain_time"] = total_train_time
    grid_data[idx]["train_start_time"] = now
    grid_data[idx]["train_single_time"] = actual_train_time
    grid_data[idx]["training_troop_name"] = troop_name
    grid_data[idx]["training_troop_count"] = count

    await update_fief_grid_data(fief_id, grid_data)

    return True, {
        "cell": grid_data[idx],
        "cost": {"wood": total_wood, "grain": total_grain, "iron": total_iron},
        "troop_name": troop_name,
        "count": count,
        "single_time": actual_train_time,
        "total_time": total_train_time,
    }


async def train_troop_all(fief_id, troop_name, count):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    if count <= 0:
        return False, "训练数量必须大于0"

    if count > 100:
        return False, "单次训练数量不能超过100"

    troop_data = None
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            troop_data = t
            break
    if not troop_data:
        return False, "无效的兵种名称"

    troop_series = troop_data["兵种系列"]
    matching_barrack_type = None
    for barrack_type, series in BARRACK_TROOP_MAP.items():
        if series == troop_series:
            matching_barrack_type = barrack_type
            break

    if not matching_barrack_type:
        return False, "没有匹配的兵营类型"

    grid_data = fief["grid_data"]
    barracks = []
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cell = _get_cell(grid_data, row, col)
            if (cell["has_building"] and not cell["is_building"]
                    and cell["type"] == matching_barrack_type
                    and not cell["is_training"]):
                barracks.append((row, col, cell))

    if not barracks:
        return False, f"没有可用的{matching_barrack_type}"

    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    wood_per = troop_data["训练耗费木材"]
    grain_per = troop_data["训练耗费粮食"]
    iron_per = troop_data["训练耗费铁矿"]
    time_per = troop_data["训练耗费时间（秒）"]

    barrack_count = len(barracks)
    total_wood = wood_per * count * barrack_count
    total_grain = grain_per * count * barrack_count
    total_iron = iron_per * count * barrack_count

    if user_resource["wood"] < total_wood:
        return False, "木材不足"
    if user_resource["grain"] < total_grain:
        return False, "粮食不足"
    if user_resource["iron"] < total_iron:
        return False, "铁矿不足"

    user_resource["wood"] -= total_wood
    user_resource["grain"] -= total_grain
    user_resource["iron"] -= total_iron
    await update_user_resource_field(user_id, "wood", user_resource["wood"])
    await update_user_resource_field(user_id, "grain", user_resource["grain"])
    await update_user_resource_field(user_id, "iron", user_resource["iron"])

    dev_score = _calc_development_score(total_wood, total_grain, total_iron)
    from mission.mission_core import add_development_score
    await add_development_score(user_id, dev_score)

    now = get_uptime_ms() // 1000
    trained = []
    for row, col, cell in barracks:
        actual_train_time = _calculate_actual_train_time(time_per, grid_data, row, col)
        total_train_time = actual_train_time * count

        idx = _grid_index(row, col)
        grid_data[idx]["is_training"] = True
        grid_data[idx]["train_remain_time"] = total_train_time
        grid_data[idx]["train_start_time"] = now
        grid_data[idx]["train_single_time"] = actual_train_time
        grid_data[idx]["training_troop_name"] = troop_name
        grid_data[idx]["training_troop_count"] = count
        trained.append({"row": row, "col": col})

    await update_fief_grid_data(fief_id, grid_data)

    return True, {
        "trained": trained,
        "barrack_count": barrack_count,
        "troop_name": troop_name,
        "count_per": count,
        "total_count": count * barrack_count,
        "cost": {"wood": total_wood, "grain": total_grain, "iron": total_iron},
    }


async def speedup_training(fief_id, barrack_type=None, row=None, col=None):
    """秒训：使用黄金加速完成兵营训练
    :param fief_id: 封地ID
    :param barrack_type: 兵营类型（"步兵营"/"弓兵营"/"骑兵营"），多兵营加速时必传
    :param row: 指定行（单个兵营加速时传）
    :param col: 指定列（单个兵营加速时传）
    """
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    grid_data = fief["grid_data"]
    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return False, "用户资源不存在"

    now = get_uptime_ms() // 1000

    if row is not None and col is not None:
        if row < 0 or row >= GRID_ROWS or col < 0 or col >= GRID_COLS:
            return False, "网格坐标越界"
        if not _is_valid_cell(row, col):
            return False, "无效的网格坐标"
        cell = _get_cell(grid_data, row, col)
        if not cell["has_building"]:
            return False, "该网格没有建筑"
        if cell["type"] not in BARRACK_BUILDINGS:
            return False, "该建筑不是兵营"
        if not cell["is_training"]:
            return False, "该兵营没有在训练"
        targets = [(row, col, cell)]
    else:
        if not barrack_type:
            return False, "多兵营加速必须指定兵营类型"
        if barrack_type not in BARRACK_BUILDINGS:
            return False, f"无效的兵营类型: {barrack_type}"
        targets = []
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                cell = _get_cell(grid_data, r, c)
                if cell["has_building"] and cell["type"] == barrack_type and cell["is_training"]:
                    targets.append((r, c, cell))

    if not targets:
        return False, "没有正在训练中的兵营"

    total_gold = 0
    speedup_list = []
    for r, c, cell in targets:
        elapsed = now - cell["train_start_time"]
        if elapsed < 0:
            elapsed = 0
        remain = max(0, cell["train_remain_time"] - elapsed)
        hours = max(1, math.ceil(remain / 3600))
        gold = hours * 8
        total_gold += gold
        speedup_list.append({
            "row": r, "col": c,
            "troop_name": cell["training_troop_name"],
            "count": cell["training_troop_count"],
            "gold_cost": gold,
        })

    if user_resource.get("gold", 0) < total_gold:
        return False, f"黄金不足，需要 {total_gold}，当前 {user_resource.get('gold', 0)}"

    user_resource["gold"] -= total_gold
    await update_user_resource_field(user_id, "gold", user_resource["gold"])

    summary = {}
    for item in speedup_list:
        r, c = item["row"], item["col"]
        troop_name = item["troop_name"]
        count = item["count"]
        cell = _get_cell(grid_data, r, c)

        if fief_id not in fief_troop_cache:
            fief_troop_cache[fief_id] = []
        found = False
        for t in fief_troop_cache[fief_id]:
            if t["troop_name"] == troop_name:
                t["count"] += count
                found = True
                break
        if not found:
            fief_troop_cache[fief_id].append({"troop_name": troop_name, "count": count})

        summary[troop_name] = summary.get(troop_name, 0) + count

        cell["is_training"] = False
        cell["train_remain_time"] = 0
        cell["train_start_time"] = 0
        cell["train_single_time"] = 0
        cell["training_troop_name"] = ""
        cell["training_troop_count"] = 0

    await update_fief_grid_data(fief_id, grid_data)
    for troop_name, count in summary.items():
        await upsert_fief_troop(fief_id, troop_name, count)

    return True, {
        "speedup": speedup_list,
        "total_gold": total_gold,
        "summary": summary,
    }


async def abandon_fief(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    await delete_fief(fief_id)
    await delete_fief_troops(fief_id)

    if fief_id in fief_cache:
        del fief_cache[fief_id]
    if fief_id in fief_troop_cache:
        del fief_troop_cache[fief_id]
    if fief_id in fief_income_accumulated:
        del fief_income_accumulated[fief_id]

    # 删除该玩家在该城池的灵珠效果（封地被放弃后灵珠失效）
    _delete_pearl_effect(fief["user_id"], fief["town_id"])

    return True, "封地已放弃"


async def destroy_fiefs_by_town(town_id):
    fiefs_to_destroy = [
        (fid, fief) for fid, fief in fief_cache.items()
        if fief["town_id"] == town_id
    ]

    if not fiefs_to_destroy:
        return

    destroyed_users = []
    for fief_id, fief in fiefs_to_destroy:
        user_id = fief["user_id"]
        await insert_fief_destroy_log(
            user_id=user_id,
            town_id=fief["town_id"],
            nation_id=fief["nation_id"],
            fief_name=fief.get("name", ""),
            grid_data=fief["grid_data"],
            destroy_reason="城池沦陷",
        )

        await delete_fief_troops(fief_id)
        if fief_id in fief_troop_cache:
            del fief_troop_cache[fief_id]

        await delete_fief(fief_id)
        if fief_id in fief_cache:
            del fief_cache[fief_id]
        if fief_id in fief_income_accumulated:
            del fief_income_accumulated[fief_id]

        # 删除该玩家在该城池的灵珠效果（封地被摧毁后灵珠失效）
        _delete_pearl_effect(fief["user_id"], fief["town_id"])

        destroyed_users.append(user_id)
        logger.info(f"封地摧毁: fief_id={fief_id}, user_id={user_id}, town_id={town_id}")

    await broadcast(make_response("success", "封地摧毁通知", {
        "type": "fief_destroy_notify",
        "town_id": town_id,
        "destroyed_users": destroyed_users,
        "destroy_reason": "城池沦陷",
    }))


def get_buildable_list(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return None, "封地不存在"

    grid_data = fief["grid_data"]
    result = []
    for building_type in BUILDABLE_BUILDINGS:
        if building_type == "空地":
            continue
        config = BUILDING_CONFIG[building_type]
        current_count = _count_building_type(grid_data, building_type)
        can_build = _can_build(current_count, config["max_count"])
        result.append({
            "type": building_type,
            "desc": config["desc"],
            "max_count": config["max_count"] if config["max_count"] != -1 else "无限制",
            "current_count": current_count,
            "can_build": can_build,
            "can_demolish": config["can_demolish"],
            "max_level": config["max_level"],
        })
    return result, None


def get_fief_income(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return None, "封地不存在"

    income = _calculate_fief_income(fief["grid_data"], fief_id)
    return income, {"fief_id": fief_id, "hourly_income": income}, None


def _calc_development_score(wood, grain, iron):
    """计算发展分：ceil((wood/1.5 + grain + iron*2) / 100)"""
    return math.ceil((wood / 1.5 + grain + iron * 2) / 100)


async def _check_and_complete_builds(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return

    grid_data = fief["grid_data"]
    now = get_uptime_ms() // 1000
    changed = False

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            idx = _grid_index(row, col)
            cell = grid_data[idx]
            if cell["is_building"]:
                elapsed = now - cell["build_start_time"]
                if elapsed >= 0:
                    new_remain = cell["build_remain_time"] - elapsed
                    if new_remain <= 0:
                        building_type = cell["type"]
                        completed_level = 1
                        if not cell["has_building"]:
                            cell["has_building"] = True
                            cell["level"] = 1
                        else:
                            cell["level"] += 1
                            completed_level = cell["level"]
                        level_data = BUILDING_LEVEL_DATA.get(building_type, {}).get(completed_level)
                        if level_data:
                            dev_score = _calc_development_score(
                                level_data["所需木材"],
                                level_data["所需粮食"],
                                level_data["所需铁矿"],
                            )
                            from mission.mission_core import add_development_score
                            await add_development_score(fief["user_id"], dev_score)
                        cell["is_building"] = False
                        cell["build_remain_time"] = 0
                        cell["build_start_time"] = 0
                        changed = True
                    else:
                        cell["build_remain_time"] = new_remain
                        cell["build_start_time"] = now
                        changed = True

    return changed


def _check_and_complete_training(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return

    grid_data = fief["grid_data"]
    now = get_uptime_ms() // 1000
    changed = False

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            idx = _grid_index(row, col)
            cell = grid_data[idx]
            if cell["is_training"]:
                if cell["train_single_time"] <= 0:
                    continue
                elapsed = now - cell["train_start_time"]
                if elapsed < 0:
                    continue

                troops_completed = elapsed // cell["train_single_time"]
                if troops_completed <= 0:
                    new_remain = cell["train_remain_time"] - elapsed
                    cell["train_remain_time"] = max(0, new_remain)
                    cell["train_start_time"] = now
                    changed = True
                    if cell["train_remain_time"] <= 0:
                        troops_completed = cell["training_troop_count"]
                    else:
                        continue

                if troops_completed >= cell["training_troop_count"]:
                    troops_completed = cell["training_troop_count"]

                troop_name = cell["training_troop_name"]
                if fief_id not in fief_troop_cache:
                    fief_troop_cache[fief_id] = []

                found = False
                for t in fief_troop_cache[fief_id]:
                    if t["troop_name"] == troop_name:
                        t["count"] += troops_completed
                        found = True
                        break
                if not found:
                    fief_troop_cache[fief_id].append({
                        "troop_name": troop_name,
                        "count": troops_completed,
                    })

                remaining = cell["training_troop_count"] - troops_completed
                if remaining <= 0:
                    cell["is_training"] = False
                    cell["train_remain_time"] = 0
                    cell["train_start_time"] = 0
                    cell["train_single_time"] = 0
                    cell["training_troop_name"] = ""
                    cell["training_troop_count"] = 0
                else:
                    new_remain = remaining * cell["train_single_time"] - (elapsed - troops_completed * cell["train_single_time"])
                    cell["train_remain_time"] = max(1, new_remain)
                    cell["train_start_time"] = now
                    cell["training_troop_count"] = remaining

                changed = True

    return changed


def _check_and_apply_income(fief_id, minutes_elapsed):
    fief = fief_cache.get(fief_id)
    if not fief:
        return

    if fief_id not in fief_income_accumulated:
        fief_income_accumulated[fief_id] = {"wood": 0.0, "grain": 0.0, "iron": 0.0, "copper": 0.0}

    if minutes_elapsed <= 0:
        return

    income = _calculate_fief_income(fief["grid_data"], fief_id)
    user_id = fief["user_id"]
    user_resource = user_resource_cache.get(user_id)
    if not user_resource:
        return

    acc = fief_income_accumulated[fief_id]
    acc["wood"] += income["wood"] * minutes_elapsed / 60.0
    acc["grain"] += income["grain"] * minutes_elapsed / 60.0
    acc["iron"] += income["iron"] * minutes_elapsed / 60.0
    acc["copper"] += income["copper"] * minutes_elapsed / 60.0

    changed = False
    if acc["wood"] >= 1.0:
        add_wood = int(acc["wood"])
        acc["wood"] -= add_wood
        user_resource["wood"] += add_wood
        changed = True

    if acc["grain"] >= 1.0:
        add_grain = int(acc["grain"])
        acc["grain"] -= add_grain
        user_resource["grain"] += add_grain
        changed = True

    if acc["iron"] >= 1.0:
        add_iron = int(acc["iron"])
        acc["iron"] -= add_iron
        user_resource["iron"] += add_iron
        changed = True

    if acc["copper"] >= 1.0:
        add_copper = int(acc["copper"])
        acc["copper"] -= add_copper
        user_resource["copper"] += add_copper
        changed = True

    return changed


async def sync_fief_data_to_db(fief_id):
    fief = fief_cache.get(fief_id)
    if not fief:
        return
    await update_fief_grid_data(fief_id, fief["grid_data"])

    if fief_id in fief_troop_cache:
        for t in fief_troop_cache[fief_id]:
            await upsert_fief_troop(fief_id, t["troop_name"], t["count"])


async def rename_fief(fief_id, new_name):
    new_name = new_name.strip()
    if not new_name:
        return False, "封地名称不能为空"

    fief = fief_cache.get(fief_id)
    if not fief:
        return False, "封地不存在"

    await update_fief_name(fief_id, new_name)
    fief_cache[fief_id]["name"] = new_name

    return True, {"fief_id": fief_id, "name": new_name}


# ==================== 灵珠效果辅助函数 ====================


def _delete_pearl_effect(user_id, town_id):
    """删除玩家的灵珠效果（从缓存中移除，异步写入数据库）"""
    import asyncio
    from legion.legion_db import delete_fief_item_effect

    cache_key = (user_id, town_id)
    if cache_key in fief_item_effects_cache:
        del fief_item_effects_cache[cache_key]
        # 异步删除数据库记录
        asyncio.create_task(delete_fief_item_effect(user_id, town_id))
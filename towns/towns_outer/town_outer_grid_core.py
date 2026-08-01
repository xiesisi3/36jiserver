import random
import asyncio
import logging
from server_timer.server_timer_core import get_uptime_ms
from data.global_data import (
    towns_cache, roads_cache, troop_cache,
    town_outer_grid_cache,
)
from towns.towns_outer.town_outer_grid_db import (
    create_table, get_all_grids, get_grid_count,
    batch_insert_grids, update_grid_cell, update_grid,
    delete_all_grids,
)
from general.general_utils import BANDIT_HERO_TEMPLATES
from troop.troop_db import insert_troop
from combat.combat_utils import recalc_troop_food

logger = logging.getLogger('36ji-server')

# 按城池粒度的网格操作锁，防止并发修改网格时产生读-改-写竞态
# 例如：两个客户端同时从同一城池出征，remove_troop_from_grid 的 update_grid_cell
# 从DB读到旧数据后写回，可能覆盖另一个请求的写入，导致已出征部队残留网格中
_grid_locks = {}

def _get_grid_lock(town_id):
    if town_id not in _grid_locks:
        _grid_locks[town_id] = asyncio.Lock()
    return _grid_locks[town_id]

GRID_ROWS = 19
GRID_COLS = 19

DIRECTION_GRID_POS = {
    "左上": (2, 2),
    "上": (2, 9),
    "右上": (2, 16),
    "右": (9, 16),
    "右下": (16, 16),
    "下": (16, 9),
    "左下": (16, 2),
    "左": (9, 2),
}

FORBIDDEN_POSITIONS = {
    (2, 2), (9, 2), (16, 2),
    (2, 9), (9, 9), (16, 9),
    (2, 16), (9, 16), (16, 16),
}


def _create_empty_grid():
    return [[[] for _ in range(GRID_COLS)] for _ in range(GRID_ROWS)]


def _calculate_gate_positions(town_id):
    gate_positions = set()
    town = towns_cache.get(town_id)
    if not town:
        return gate_positions

    for road in roads_cache.values():
        if road["start_town_id"] == town_id:
            other_id = road["end_town_id"]
        elif road["end_town_id"] == town_id:
            other_id = road["start_town_id"]
        else:
            continue

        other_town = towns_cache.get(other_id)
        if not other_town:
            continue

        dx = other_town["pos_x"] - town["pos_x"]
        dy = other_town["pos_y"] - town["pos_y"]

        if dx == 0 and dy == 0:
            continue

        angle = 0
        if dx != 0 or dy != 0:
            import math
            angle = math.atan2(-dy, dx) * 180 / math.pi
            if angle < 0:
                angle += 360

        if 22.5 <= angle < 67.5:
            direction = "右上"
        elif 67.5 <= angle < 112.5:
            direction = "上"
        elif 112.5 <= angle < 157.5:
            direction = "左上"
        elif 157.5 <= angle < 202.5:
            direction = "左"
        elif 202.5 <= angle < 247.5:
            direction = "左下"
        elif 247.5 <= angle < 292.5:
            direction = "下"
        elif 292.5 <= angle < 337.5:
            direction = "右下"
        else:
            direction = "右"

        if direction in DIRECTION_GRID_POS:
            gate_positions.add(DIRECTION_GRID_POS[direction])

    return gate_positions


def _generate_fixed_troop_data_by_level(level):
    if level == 1:
        return []

    if level == 2:
        archer_team = [
            {"兵种名称": "弓箭手", "数量": 20},
            {"兵种名称": "弓箭手", "数量": 20},
            {"兵种名称": "弓箭手", "数量": 20},
            None, None,
        ]
        light_infantry_team = [
            {"兵种名称": "轻步兵", "数量": 20},
            {"兵种名称": "轻步兵", "数量": 20},
            {"兵种名称": "轻步兵", "数量": 20},
            None, None,
        ]
        mix_team = [
            {"兵种名称": "轻步兵", "数量": 20},
            {"兵种名称": "弓箭手", "数量": 20},
            {"兵种名称": "轻骑兵", "数量": 20},
            None, None,
        ]
        light_cavalry_team = [
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
            None,
        ]
        result = []
        for _ in range(6):
            result.append({"hero_panel_id": 10001, "food": 99999, "team": archer_team.copy()})
        for _ in range(6):
            result.append({"hero_panel_id": 10001, "food": 99999, "team": light_infantry_team.copy()})
        for _ in range(12):
            result.append({"hero_panel_id": 10001, "food": 99999, "team": mix_team.copy()})
        result.append({"hero_panel_id": 10002, "food": 99999, "team": light_cavalry_team.copy()})
        return result

    if level == 3:
        light_cavalry_team = [
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
            {"兵种名称": "轻骑兵", "数量": 30},
        ]
        archer_team = [
            {"兵种名称": "弓箭手", "数量": 30},
            {"兵种名称": "弓箭手", "数量": 30},
            {"兵种名称": "弓箭手", "数量": 30},
            {"兵种名称": "弓箭手", "数量": 30},
            {"兵种名称": "弓箭手", "数量": 30},
        ]
        light_infantry_team = [
            {"兵种名称": "轻步兵", "数量": 30},
            {"兵种名称": "轻步兵", "数量": 30},
            {"兵种名称": "轻步兵", "数量": 30},
            {"兵种名称": "轻步兵", "数量": 30},
            {"兵种名称": "轻步兵", "数量": 30},
        ]
        mix_team = [
            {"兵种名称": "轻步兵", "数量": 20},
            {"兵种名称": "轻骑兵", "数量": 100},
            {"兵种名称": "弓箭手", "数量": 100},
            {"兵种名称": "轻步兵", "数量": 100},
            None,
        ]
        heavy_cavalry_team = [
            {"兵种名称": "重骑兵", "数量": 50},
            {"兵种名称": "重骑兵", "数量": 150},
            {"兵种名称": "重骑兵", "数量": 150},
            {"兵种名称": "重骑兵", "数量": 150},
            None,
        ]
        result = []
        for _ in range(5):
            result.append({"hero_panel_id": 10002, "food": 99999, "team": light_cavalry_team.copy()})
        for _ in range(5):
            result.append({"hero_panel_id": 10002, "food": 99999, "team": archer_team.copy()})
        for _ in range(5):
            result.append({"hero_panel_id": 10002, "food": 99999, "team": light_infantry_team.copy()})
        for _ in range(12):
            result.append({"hero_panel_id": 10002, "food": 99999, "team": mix_team.copy()})
        result.append({"hero_panel_id": 10003, "food": 99999, "team": heavy_cavalry_team.copy()})
        return result

    if level == 4:
        strong_archer_team = [
            {"兵种名称": "强弓手", "数量": 20},
            {"兵种名称": "强弓手", "数量": 20},
            {"兵种名称": "强弓手", "数量": 20},
            {"兵种名称": "强弓手", "数量": 20},
            {"兵种名称": "强弓手", "数量": 20},
        ]
        heavy_cavalry_team = [
            {"兵种名称": "重骑兵", "数量": 20},
            {"兵种名称": "重骑兵", "数量": 20},
            {"兵种名称": "重骑兵", "数量": 20},
            {"兵种名称": "重骑兵", "数量": 20},
            {"兵种名称": "重骑兵", "数量": 20},
        ]
        heavy_infantry_team = [
            {"兵种名称": "重步兵", "数量": 20},
            {"兵种名称": "重步兵", "数量": 20},
            {"兵种名称": "重步兵", "数量": 20},
            {"兵种名称": "重步兵", "数量": 20},
            {"兵种名称": "重步兵", "数量": 20},
        ]
        mix_team = [
            {"兵种名称": "重步兵", "数量": 100},
            {"兵种名称": "重骑兵", "数量": 150},
            {"兵种名称": "强弓手", "数量": 150},
            {"兵种名称": "重步兵", "数量": 150},
            None,
        ]
        tiger_cavalry_team = [
            {"兵种名称": "虎豹骑", "数量": 50},
            {"兵种名称": "虎豹骑", "数量": 250},
            {"兵种名称": "虎豹骑", "数量": 250},
            {"兵种名称": "虎豹骑", "数量": 250},
            None,
        ]
        result = []
        for _ in range(4):
            result.append({"hero_panel_id": 10003, "food": 99999, "team": strong_archer_team.copy()})
        for _ in range(4):
            result.append({"hero_panel_id": 10003, "food": 99999, "team": heavy_cavalry_team.copy()})
        for _ in range(4):
            result.append({"hero_panel_id": 10003, "food": 99999, "team": heavy_infantry_team.copy()})
        for _ in range(12):
            result.append({"hero_panel_id": 10004, "food": 99999, "team": mix_team.copy()})
        result.append({"hero_panel_id": 10004, "food": 99999, "team": tiger_cavalry_team.copy()})
        return result

    if level == 5:
        mix_team = [
            {"兵种名称": "禁卫军", "数量": 100},
            {"兵种名称": "虎豹骑", "数量": 150},
            {"兵种名称": "弩骑兵", "数量": 150},
            {"兵种名称": "禁卫军", "数量": 150},
            None,
        ]
        chariot_team = [
            {"兵种名称": "战车", "数量": 250},
            {"兵种名称": "战车", "数量": 250},
            {"兵种名称": "战车", "数量": 250},
            {"兵种名称": "战车", "数量": 250},
            None,
        ]
        result = []
        for _ in range(20):
            result.append({"hero_panel_id": 10004, "food": 99999, "team": mix_team.copy()})
        result.append({"hero_panel_id": 10005, "food": 99999, "team": chariot_team.copy()})
        return result

    if level == 6:
        elite_mix_team = [
            {"兵种名称": "羽林军", "数量": 150},
            {"兵种名称": "帝国铁骑", "数量": 150},
            {"兵种名称": "战车", "数量": 150},
            {"兵种名称": "羽林军", "数量": 150},
            {"兵种名称": "帝国铁骑", "数量": 150},
        ]
        chariot_team = [
            {"兵种名称": "战车", "数量": 300},
            {"兵种名称": "战车", "数量": 300},
            {"兵种名称": "战车", "数量": 300},
            {"兵种名称": "战车", "数量": 300},
            {"兵种名称": "战车", "数量": 300},
        ]
        result = []
        for _ in range(20):
            result.append({"hero_panel_id": 10005, "food": 99999, "team": elite_mix_team.copy()})
        for _ in range(3):
            result.append({"hero_panel_id": 10005, "food": 99999, "team": chariot_team.copy()})
        return result

    return []


def _generate_random_troop_data_by_level(level):
    if level == 1:
        return []

    level_core_params = {
        2: {"total_troops": 1560, "troop_count": 25},
        3: {"total_troops": 6590, "troop_count": 28},
        4: {"total_troops": 8600, "troop_count": 25},
        5: {"total_troops": 12000, "troop_count": 21},
        6: {"total_troops": 15000, "troop_count": 23},
    }
    from data.troop_data import TROOP_DATA

    troop_level_map = {
        "一": [t for t in TROOP_DATA if t["兵种等级"] == "一"],
        "二": [t for t in TROOP_DATA if t["兵种等级"] == "二"],
        "三": [t for t in TROOP_DATA if t["兵种等级"] == "三"],
        "四": [t for t in TROOP_DATA if t["兵种等级"] == "四"],
    }

    hero_panel_config = {
        2: {"main_panel_id": 10001, "special_panel_id": 10002},
        3: {"main_panel_id": 10002, "special_panel_id": 10003},
        4: {"main_panel_id": 10003, "special_panel_id": 10004},
        5: {"main_panel_id": 10004, "special_panel_id": 10005},
        6: {"main_panel_id": 10005, "special_panel_id": 10005},
    }

    troop_level_config = {
        2: {"main_level": "一", "special_level": None, "special_num": 0},
        3: {"main_level": "一", "special_level": "二", "special_num": 1},
        4: {"main_level": "二", "special_level": "三", "special_num": 1},
        5: {"main_level": "三", "special_level": "四", "special_num": 2},
        6: {"main_level": "四", "special_level": "四", "special_num": 4},
    }

    core_params = level_core_params[level]
    base_total = core_params["total_troops"]
    base_count = core_params["troop_count"]

    random_total = random.randint(int(base_total * 0.9), int(base_total * 1.1))
    random_troop_count = random.randint(int(base_count * 0.9), int(base_count * 1.1))

    config = troop_level_config[level]
    hero_config = hero_panel_config[level]

    random_troop_list = []
    allocated_total = 0
    special_generated_num = 0
    base_per_troop = random_total / random_troop_count

    for i in range(random_troop_count):
        is_special = False
        if config["special_level"] and special_generated_num < config["special_num"]:
            remaining_troops = random_troop_count - i
            if remaining_troops == (config["special_num"] - special_generated_num):
                is_special = True

        if is_special:
            troop_pool = troop_level_map[config["special_level"]]
            special_generated_num += 1
            hero_panel_id = hero_config["special_panel_id"]
        else:
            troop_pool = troop_level_map[config["main_level"]]
            hero_panel_id = hero_config["main_panel_id"]

        if not troop_pool:
            troop_pool = troop_level_map["一"]

        max_per_troop = 600 if level < 5 else float('inf')
        if i == random_troop_count - 1:
            troop_total = random_total - allocated_total
            troop_total = max(troop_total, 500)
            if level < 5:
                troop_total = min(troop_total, max_per_troop)
            if level == 2:
                troop_total = min(240, troop_total)
        else:
            troop_total = random.randint(
                max(int(base_per_troop * 0.5), 1),
                min(int(base_per_troop * 1.5), max_per_troop)
            )

        allocated_total += troop_total

        troop_positions = [None] * 5
        if level == 2:
            pos_count = 4
        else:
            full_pos = random.random() <= 0.3
            pos_count = 5 if full_pos else random.randint(3, 4)
        pos_indexes = random.sample(range(5), pos_count)

        base_per_pos = troop_total / pos_count
        pos_troops = []
        for j in range(pos_count):
            pos_troop = random.randint(int(base_per_pos * 0.8), int(base_per_pos * 1.2))
            pos_troops.append(pos_troop)
        pos_troops[-1] = troop_total - sum(pos_troops[:-1])
        pos_troops[-1] = max(pos_troops[-1], 1)

        for j, idx in enumerate(pos_indexes):
            random_troop = random.choice(troop_pool)
            troop_positions[idx] = {
                "兵种名称": random_troop["兵种名称"],
                "数量": pos_troops[j],
            }

        random_troop_list.append({
            "hero_panel_id": hero_panel_id,
            "food": 99999,
            "team": troop_positions,
        })

    return random_troop_list


def _distribute_troop_to_positions(troop_data_list):
    available_positions = [
        (x, y) for x in range(GRID_ROWS) for y in range(GRID_COLS)
        if (x, y) not in FORBIDDEN_POSITIONS
    ]

    result = []
    for troop_data in troop_data_list:
        grid_pos = random.choice(available_positions)
        data = troop_data.copy()
        data["grid_pos"] = grid_pos
        data["create_time"] = get_uptime_ms()
        result.append(data)
    return result


async def _create_bandit_troop(town_id, troop_data, grid):
    bandit_general_id = -troop_data["hero_panel_id"]
    if bandit_general_id not in BANDIT_HERO_TEMPLATES:
        return None

    now = get_uptime_ms()
    team = troop_data["team"]
    grid_x, grid_y = troop_data["grid_pos"]

    troop_dict = {
        "user_id": "0",
        "general_id": bandit_general_id,
        "team": team,
        "food": troop_data.get("food", 99999),
        "status": 1,
        "pos": town_id,
        "dest": None,
        "dep_time": 0,
        "arrive_time": 0,
        "grid_x": grid_x,
        "grid_y": grid_y,
        "target_type": "nearest",
    }
    # 按兵种可携带粮食上限带满粮食
    recalc_troop_food(troop_dict)
    troop_id = await insert_troop(troop_dict)
    troop_dict["id"] = troop_id
    troop_dict["create_time"] = now
    troop_dict["update_time"] = now
    troop_cache[troop_id] = troop_dict

    grid[grid_x][grid_y].append(troop_id)
    return troop_id


async def init_outer_grid():
    await create_table()

    count = await get_grid_count()
    if count > 0:
        rows = await get_all_grids()
        town_outer_grid_cache.clear()
        stale_count = 0
        troops_by_town_pos = {}
        for tid, troop in troop_cache.items():
            if troop.get("status") == 1:
                pos = str(troop.get("pos", ""))
                troops_by_town_pos.setdefault(pos, []).append(tid)
        for row in rows:
            grid = row["grid"]
            town_id = row["town_id"]
            town_stale = False
            for x in range(GRID_ROWS):
                for y in range(GRID_COLS):
                    cell = grid[x][y]
                    if cell:
                        valid_ids = [tid for tid in cell if tid in troop_cache]
                        if len(valid_ids) != len(cell):
                            stale_count += len(cell) - len(valid_ids)
                            grid[x][y] = valid_ids
                            town_stale = True
            town_outer_grid_cache[town_id] = grid
            grid_troop_set = set()
            for x in range(GRID_ROWS):
                for y in range(GRID_COLS):
                    for tid in (grid[x][y] or []):
                        grid_troop_set.add(tid)
            added_missing_count = 0
            for tid in troops_by_town_pos.get(str(town_id), []):
                if tid in grid_troop_set:
                    continue
                gx = troop_cache.get(tid, {}).get("grid_x")
                gy = troop_cache.get(tid, {}).get("grid_y")
                if gx is None or gy is None or not (0 <= gx < GRID_ROWS and 0 <= gy < GRID_COLS):
                    continue
                if grid[gx][gy] is None:
                    grid[gx][gy] = []
                grid[gx][gy].append(tid)
                grid_troop_set.add(tid)
                added_missing_count += 1
                town_stale = True
            if added_missing_count > 0:
                logger.info(f"外城网格 城池{town_id} 补录了 {added_missing_count} 支缺失的驻守部队")
            if town_stale:
                await update_grid(town_id, grid)
        if stale_count > 0:
            logger.info(f"外城网格发现 {stale_count} 个过期部队引用")
            if len(troop_cache) == 0:
                logger.info("部队数据为空，清空外城网格重新初始化")
                town_outer_grid_cache.clear()
                await delete_all_grids()
            else:
                logger.info(f"外城网格模块初始化完成: {len(town_outer_grid_cache)} 个城池 (从数据库加载)")
                return
        else:
            logger.info(f"外城网格模块初始化完成: {len(town_outer_grid_cache)} 个城池 (从数据库加载)")
            return

    logger.info("外城网格无数据，开始初始化...")

    grid_insert_list = []
    bandit_town_count = 0
    bandit_troop_count = 0

    for town_id, town in towns_cache.items():
        grid = _create_empty_grid()

        if town.get("owner") == 1:
            level = town.get("level", 1)
            if level == 1:
                pass
            else:
                if random.random() <= 0.7:
                    troop_data_list = _generate_fixed_troop_data_by_level(level)
                else:
                    troop_data_list = _generate_random_troop_data_by_level(level)

                troop_data_with_pos = _distribute_troop_to_positions(troop_data_list)

                for td in troop_data_with_pos:
                    tid = await _create_bandit_troop(town_id, td, grid)
                    if tid:
                        bandit_troop_count += 1

                bandit_town_count += 1

        grid_insert_list.append({
            "town_id": town_id,
            "grid": grid,
        })
        town_outer_grid_cache[town_id] = grid

    await batch_insert_grids(grid_insert_list)
    logger.info(
        f"外城网格初始化完成: {len(town_outer_grid_cache)} 个城池, "
        f"{bandit_town_count} 个山贼城池, {bandit_troop_count} 支山贼部队"
    )


def get_outer_grid(town_id):
    grid = town_outer_grid_cache.get(town_id)
    if grid is None:
        return None
    gate_positions = _calculate_gate_positions(town_id)
    return {
        "town_id": town_id,
        "grid": grid,
        "gate_positions": list(gate_positions),
        "center": (9, 9),
    }


async def add_troop_to_grid(town_id, troop_id, grid_x, grid_y):
    async with _get_grid_lock(town_id):
        grid = town_outer_grid_cache.get(town_id)
        if grid is None:
            return False
        grid[grid_x][grid_y].append(troop_id)
        await update_grid_cell(town_id, grid_x, grid_y, grid[grid_x][grid_y], grid=grid)
        return True


async def remove_troop_from_grid(town_id, troop_id, grid_x, grid_y):
    async with _get_grid_lock(town_id):
        grid = town_outer_grid_cache.get(town_id)
        if grid is None:
            return False
        cell = grid[grid_x][grid_y]
        if troop_id in cell:
            cell.remove(troop_id)
            await update_grid_cell(town_id, grid_x, grid_y, cell, grid=grid)
        return True


def _cleanup_duplicate_troops(grid, troop_id):
    dirty = []
    for x in range(GRID_ROWS):
        for y in range(GRID_COLS):
            if troop_id in grid[x][y]:
                grid[x][y].remove(troop_id)
                dirty.append((x, y))
    return dirty


async def move_troop_on_grid(town_id, troop_id, old_x, old_y, new_x, new_y):
    async with _get_grid_lock(town_id):
        grid = town_outer_grid_cache.get(town_id)
        if grid is None:
            return False, "外城网格数据不存在"

        if not (0 <= new_x < GRID_ROWS and 0 <= new_y < GRID_COLS):
            return False, "目标坐标超出网格范围"

        if (new_x, new_y) == (9, 9):
            return False, "不能移动到城中心"

        gate_positions = _calculate_gate_positions(town_id)
        if (new_x, new_y) in gate_positions:
            return False, "不能移动到城门位置"

        if grid[new_x][new_y]:
            other_ids = [tid for tid in grid[new_x][new_y] if tid != troop_id]
            if other_ids:
                return False, "目标网格已有部队"

        dirty = _cleanup_duplicate_troops(grid, troop_id)
        grid[new_x][new_y].append(troop_id)
        if (new_x, new_y) not in dirty:
            dirty.append((new_x, new_y))

    for x, y in dirty:
        await update_grid_cell(town_id, x, y, grid[x][y], grid=grid)

    return True, None
import random
import logging
from data.global_data import towns_cache, nation_cache, user_resource_cache, player_name_index, user_nation_cache
from nations.nation_db import (
    create_tables,
    truncate_nations,
    insert_nations,
    get_all_nations,
    get_nation_count,
    batch_update_town_owners,
    insert_user_nation,
    get_all_user_nations,
)
from user_resource.user_resource_core import set_player_name
from general.general_utils import hero_panel_to_general, INITIAL_GENERAL_PANEL
from general.general_db import insert_general
from general.general_core import sync_cache_insert

logger = logging.getLogger('36ji-server')

NATION_NAMES = {
    1: "山贼集团",
    2: "秦",
    3: "汉",
    4: "唐",
    5: "明",
}

MAP_WIDTH = 3840
MAP_HEIGHT = 2160
CIRCLE_RADIUS = 22
NAME_HEIGHT = 28
MIN_SPACING = 60
MARGIN = 50

CELL_WIDTH = CIRCLE_RADIUS * 2 + MIN_SPACING
CELL_HEIGHT = CIRCLE_RADIUS * 2 + NAME_HEIGHT + MIN_SPACING
COLS = (MAP_WIDTH - MARGIN * 2) // CELL_WIDTH
ROWS = (MAP_HEIGHT - MARGIN * 2) // CELL_HEIGHT

INITIAL_CITY_POSITIONS = {
    "左上": {"center": (0, 5), "others": [(0, 4), (0, 6), (1, 5)]},
    "右上": {"center": (0, COLS - 6), "others": [(0, COLS - 7), (0, COLS - 5), (1, COLS - 6)]},
    "左下": {"center": (ROWS - 1, 5), "others": [(ROWS - 1, 4), (ROWS - 1, 6), (ROWS - 2, 5)]},
    "右下": {"center": (ROWS - 1, COLS - 6), "others": [(ROWS - 1, COLS - 7), (ROWS - 1, COLS - 5), (ROWS - 2, COLS - 6)]},
}


def _position_to_grid_index(px, py):
    col = (px - MARGIN - CELL_WIDTH // 2) / CELL_WIDTH
    row = (py - MARGIN - CELL_HEIGHT // 2) / CELL_HEIGHT
    return round(row), round(col)


def _build_grid_map():
    grid_map = {}
    for town_id, town in towns_cache.items():
        row, col = _position_to_grid_index(town["pos_x"], town["pos_y"])
        grid_map[(row, col)] = town_id
    return grid_map


async def init_nations():
    await create_tables()

    count = await get_nation_count()
    if count > 0:
        rows = await get_all_nations()
        nation_cache.clear()
        for row in rows:
            nation_cache[row["id"]] = dict(row)
        logger.info(f"从数据库加载 {len(rows)} 个国家")
        return

    await truncate_nations()

    nation_ids = [2, 3, 4, 5]
    random.shuffle(nation_ids)
    positions = list(INITIAL_CITY_POSITIONS.keys())

    nations = [
        {"id": 1, "name": NATION_NAMES[1], "position": ""},
    ]
    for i, pos in enumerate(positions):
        nations.append({
            "id": nation_ids[i],
            "name": NATION_NAMES[nation_ids[i]],
            "position": pos,
        })

    await insert_nations(nations)

    rows = await get_all_nations()
    nation_cache.clear()
    for row in rows:
        nation_cache[row["id"]] = dict(row)

    grid_map = _build_grid_map()
    updates = []

    for i, pos in enumerate(positions):
        nation_id = nation_ids[i]
        group = INITIAL_CITY_POSITIONS[pos]
        all_cells = [group["center"]] + group["others"]
        for cell in all_cells:
            town_id = grid_map.get(cell)
            if town_id is not None:
                updates.append((nation_id, town_id))

    for town_id in towns_cache:
        if town_id not in [u[1] for u in updates]:
            updates.append((1, town_id))

    await batch_update_town_owners(updates)

    for nation_id, town_id in updates:
        if town_id in towns_cache:
            towns_cache[town_id]["owner"] = nation_id

    logger.info(f"国家初始化完成，共 {len(nation_cache)} 个国家")


def get_all_nations_from_cache():
    return list(nation_cache.values())


async def select_nation(user_id, nation_id, player_name, personality):
    if nation_id not in nation_cache:
        return False, "国家不存在"

    if user_id not in user_resource_cache:
        return False, "用户资源不存在"

    if user_resource_cache[user_id].get("player_name"):
        return False, "已选择过国家"

    success, msg = await set_player_name(user_id, player_name)
    if not success:
        return False, msg

    await insert_user_nation(user_id, nation_id)
    user_nation_cache[user_id] = nation_id

    panel = dict(INITIAL_GENERAL_PANEL)
    panel["英雄名称"] = player_name
    panel["性格"] = personality
    general_dict = hero_panel_to_general(panel, user_id)
    general_id = await insert_general(general_dict)
    general_dict["id"] = general_id
    sync_cache_insert(general_dict)
    logger.info(f"玩家 {player_name}({user_id}) 初始武将创建成功: general_id={general_id}, 性格={personality}")

    return True, "选择成功"


async def load_all_user_nations_to_cache():
    rows = await get_all_user_nations()
    user_nation_cache.clear()
    for row in rows:
        user_nation_cache[row["user_id"]] = row["nation_id"]
    logger.info(f"用户国家缓存加载完成，共 {len(user_nation_cache)} 条")
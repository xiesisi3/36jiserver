import random

from data.towns_name import PREFIX_CHARS, SUFFIX_CHARS
from data.global_data import towns_cache, mountain_cells
from towns.towns_db import (
    batch_insert_towns,
    get_all_towns,
    get_town_count,
    get_towns_in_viewport,
    get_town_by_id,
)

MAP_WIDTH = 3840
MAP_HEIGHT = 2160
CIRCLE_RADIUS = 22
NAME_HEIGHT = 28
MIN_SPACING = 60
MARGIN = 50
OFFSET_RANGE = 15

CELL_WIDTH = CIRCLE_RADIUS * 2 + MIN_SPACING
CELL_HEIGHT = CIRCLE_RADIUS * 2 + NAME_HEIGHT + MIN_SPACING


def generate_town_attributes(town_id):
    return {
        "owner": 1,
        "level": 1,
        "forest": 0.00,
        "fertile": 0.00,
        "mine": 0.00,
        "stability": 0,
        "defense": 0,
        "traffic": 0,
    }


def generate_town_name(used_names):
    while True:
        name = random.choice(PREFIX_CHARS) + random.choice(SUFFIX_CHARS) + "城"
        if name not in used_names:
            used_names.add(name)
            return name


def generate_towns():
    cols = (MAP_WIDTH - MARGIN * 2) // CELL_WIDTH
    rows = (MAP_HEIGHT - MARGIN * 2) // CELL_HEIGHT

    towns = []
    used_names = set()
    town_id = 1

    for row in range(rows):
        for col in range(cols):
            if (row, col) in mountain_cells:
                continue

            center_x = (
                MARGIN
                + col * CELL_WIDTH
                + CELL_WIDTH // 2
                + random.randint(-OFFSET_RANGE, OFFSET_RANGE)
            )
            center_y = (
                MARGIN
                + row * CELL_HEIGHT
                + CELL_HEIGHT // 2
                + random.randint(-OFFSET_RANGE, OFFSET_RANGE)
            )

            name = generate_town_name(used_names)

            name_rect_x = center_x - 40
            name_rect_y = center_y + CIRCLE_RADIUS + 4
            name_rect_w = 80
            name_rect_h = 20

            attrs = generate_town_attributes(town_id)
            town = {
                "id": town_id,
                "pos_x": center_x,
                "pos_y": center_y,
                "name": name,
                "name_rect_x": name_rect_x,
                "name_rect_y": name_rect_y,
                "name_rect_w": name_rect_w,
                "name_rect_h": name_rect_h,
                "status": 0,
                "create_time": None,
                **attrs,
            }
            towns.append(town)
            town_id += 1

    return towns


async def init_towns():
    count = await get_town_count()
    if count == 0:
        towns = generate_towns()
        await batch_insert_towns(towns)
        for t in towns:
            towns_cache[t["id"]] = t
        return towns
    else:
        rows = await get_all_towns()
        for row in rows:
            towns_cache[row["id"]] = row
        return list(towns_cache.values())


def get_town_by_id_from_cache(town_id):
    return towns_cache.get(town_id)


def get_all_towns_from_cache():
    return list(towns_cache.values())


def get_towns_in_viewport_from_cache(x1, y1, x2, y2):
    return [
        t
        for t in towns_cache.values()
        if x1 <= t["pos_x"] <= x2 and y1 <= t["pos_y"] <= y2
    ]
import random
import math
import logging

from data.global_data import (
    mountains_cache,
    rivers_cache,
    mountain_cells,
    core_region_bbox,
)
from terrain.terrain_utils import (
    position_to_grid,
    polygon_bbox,
)
from terrain.terrain_db import (
    truncate_mountains,
    truncate_rivers,
    get_mountain_count,
    get_river_count,
    batch_insert_mountains,
    batch_insert_rivers,
    get_all_mountains,
    get_all_rivers,
    update_mountain_vertices,
)

logger = logging.getLogger('36ji-server')

MAP_WIDTH = 3840
MAP_HEIGHT = 2160
CELL_WIDTH = 104
CELL_HEIGHT = 132
MARGIN = 50
RANDOM_OFFSET = 15

MOUNTAIN_NAMES = [
    "太行", "吕梁", "恒山", "华山", "衡山", "恒山", "嵩山", "泰山",
    "黄山", "庐山", "巫山", "峨眉", "青城", "武当", "衡山", "太行",
    "秦岭", "昆仑", "天山", "阴山", "燕山", "秦岭", "祁连", "贺兰",
    "阴山", "太行", "少室", "太白", "普陀", "五台", "九华", "青城",
]


def _generate_mountain_polygon(center_x, center_y, radius, num_sides):
    vertices = []
    angle_step = 2 * math.pi / num_sides
    for i in range(num_sides):
        base_angle = i * angle_step
        actual_radius = radius * random.uniform(0.8, 1.2)
        angle = base_angle + random.uniform(-0.15, 0.15)
        x = center_x + math.cos(angle) * actual_radius
        y = center_y + math.sin(angle) * actual_radius
        vertices.append((round(x), round(y)))
    return vertices


def _is_in_excluded_region(x, y):
    core_x1, core_y1, core_x2, core_y2 = core_region_bbox
    if core_x1 < x < core_x2 and core_y1 < y < core_y2:
        return True
    if x < 200 or x > MAP_WIDTH - 200 or y < 200 or y > MAP_HEIGHT - 200:
        return True
    return False


def _is_overlapping_river(bbox, rivers):
    bx1, by1, bx2, by2 = bbox
    for river in rivers:
        segs = river["segments"]
        for i in range(len(segs) - 1):
            rx1, ry1 = segs[i]
            rx2, ry2 = segs[i + 1]
            if (max(bx1, min(rx1, rx2)) < min(bx2, max(rx1, rx2)) and
                max(by1, min(ry1, ry2)) < min(by2, max(ry1, ry2))):
                return True
    return False


def _cell_to_pixel_bounds(r, c):
    x1 = MARGIN + c * CELL_WIDTH
    y1 = MARGIN + r * CELL_HEIGHT
    x2 = x1 + CELL_WIDTH
    y2 = y1 + CELL_HEIGHT
    return x1, y1, x2, y2


def _expand_mountain_to_cells(cells, size):
    min_r = min(r for r, c in cells)
    max_r = max(r for r, c in cells)
    min_c = min(c for r, c in cells)
    max_c = max(c for r, c in cells)

    x1, y1, _, _ = _cell_to_pixel_bounds(min_r, min_c)
    _, _, x2, y2 = _cell_to_pixel_bounds(max_r, max_c)

    if size == "small":
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        rx = (x2 - x1) // 2 + random.randint(4, 10)
        ry = (y2 - y1) // 2 + random.randint(4, 10)

        vertices = []
        num_sides = random.randint(8, 10)
        for i in range(num_sides):
            ang = 2 * math.pi * i / num_sides + random.uniform(-0.08, 0.08)
            rx_actual = rx * random.uniform(0.85, 1.10)
            ry_actual = ry * random.uniform(0.85, 1.10)
            px = cx + math.cos(ang) * rx_actual
            py = cy + math.sin(ang) * ry_actual
            px += random.uniform(-5, 5)
            py += random.uniform(-5, 5)
            vertices.append((round(px), round(py)))
    else:
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        rx = (x2 - x1) // 2 - random.randint(20, 30)
        ry = (y2 - y1) // 2 - random.randint(25, 35)

        vertices = []
        num_sides = 12
        for i in range(num_sides):
            ang = 2 * math.pi * i / num_sides
            rx_actual = rx * random.uniform(0.80, 1.10)
            ry_actual = ry * random.uniform(0.80, 1.10)
            px = cx + math.cos(ang) * rx_actual
            py = cy + math.sin(ang) * ry_actual
            px += random.uniform(-8, 8)
            py += random.uniform(-8, 8)
            vertices.append((round(px), round(py)))

    return vertices


def generate_mountains(rivers):
    quadrants = [
        ("左上", 200, 1300, 200, 700),
        ("右上", 2540, 3640, 200, 700),
        ("左下", 200, 1300, 1460, 1960),
        ("右下", 2540, 3640, 1460, 1960),
    ]

    mountains = []
    occupied = set()

    _ROWS = (MAP_HEIGHT - MARGIN * 2) // CELL_HEIGHT
    _COLS = (MAP_WIDTH - MARGIN * 2) // CELL_WIDTH

    _INITIAL_CITY_CELLS = [
        (0, 4), (0, 5), (0, 6), (1, 5),
        (0, _COLS - 5), (0, _COLS - 6), (0, _COLS - 7), (1, _COLS - 6),
        (_ROWS - 1, 4), (_ROWS - 1, 5), (_ROWS - 1, 6), (_ROWS - 2, 5),
        (_ROWS - 1, _COLS - 5), (_ROWS - 1, _COLS - 6), (_ROWS - 1, _COLS - 7), (_ROWS - 2, _COLS - 6),
    ]
    for (r, c) in _INITIAL_CITY_CELLS:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                occupied.add((r + dr, c + dc))

    for quad_name, x1, x2, y1, y2 in quadrants:
        for i in range(7):
            attempts = 0
            while attempts < 50:
                cx = random.randint(x1, x2)
                cy = random.randint(y1, y2)
                if _is_in_excluded_region(cx, cy):
                    attempts += 1
                    continue

                radius = random.randint(18, 25)
                vertices = _generate_mountain_polygon(cx, cy, radius, 6)
                bbox = polygon_bbox(vertices)
                if _is_overlapping_river(bbox, rivers):
                    attempts += 1
                    continue

                r0, c0 = position_to_grid(cx, cy, MARGIN, CELL_WIDTH, CELL_HEIGHT)
                cells = {(r0, c0)}

                if any((r, c) in occupied for (r, c) in cells):
                    attempts += 1
                    continue

                for (r, c) in cells:
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            occupied.add((r + dr, c + dc))

                name = f"{random.choice(MOUNTAIN_NAMES)}{quad_name}"
                mountains.append({
                    "name": name,
                    "cells": cells,
                    "vertices": vertices,
                    "size": "small",
                })
                break
            attempts += 1

    core_x1, core_y1, core_x2, core_y2 = 1400, 780, 2440, 1380
    center_corners = [
        (core_x1, core_y1),
        (core_x2, core_y1),
        (core_x1, core_y2),
        (core_x2, core_y2),
    ]

    for idx, (base_x, base_y) in enumerate(center_corners):
        sign_x = 1 if idx in (0, 2) else -1
        sign_y = 1 if idx in (0, 1) else -1
        placed = False
        for _ in range(50):
            cx = base_x + sign_x * random.randint(100, 200)
            cy = base_y + sign_y * random.randint(100, 200)
            radius = random.randint(18, 25)
            vertices = _generate_mountain_polygon(cx, cy, radius, 6)
            bbox = polygon_bbox(vertices)
            if _is_overlapping_river(bbox, rivers):
                continue
            r0, c0 = position_to_grid(cx, cy, MARGIN, CELL_WIDTH, CELL_HEIGHT)
            cells = {(r0, c0)}
            if any((r, c) in occupied for (r, c) in cells):
                continue
            for (r, c) in cells:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        occupied.add((r + dr, c + dc))
            radius = random.randint(18, 25)
            vertices = _generate_mountain_polygon(cx, cy, radius, 6)
            name = f"{random.choice(MOUNTAIN_NAMES)}中心"
            mountains.append({
                "name": name,
                "cells": cells,
                "vertices": vertices,
                "size": "small",
            })
            placed = True
            break
        if not placed:
            logging.getLogger('36ji-server').warning(
                f"中心山脉 {idx} 放置失败，该角已无可用格子"
            )

    return mountains


def generate_river_horizontal(y_center, x_start, x_end, center_x):
    segments = []
    x = x_start
    current_y = y_center
    segments.append((round(x), round(current_y)))

    while x < x_end:
        step_len = random.randint(30, 50)
        y_offset = random.randint(-20, 20)
        next_x = min(x + step_len, x_end)
        next_y = y_center + y_offset + random.randint(-10, 10)
        next_y = max(20, min(MAP_HEIGHT - 20, next_y))
        segments.append((round(next_x), round(next_y)))
        x = next_x

    return segments


def generate_river_vertical(x_center, y_start, y_end, center_y):
    segments = []
    y = y_start
    current_x = x_center
    segments.append((round(current_x), round(y)))

    while y < y_end:
        step_len = random.randint(30, 50)
        x_offset = random.randint(-20, 20)
        next_y = min(y + step_len, y_end)
        next_x = x_center + x_offset + random.randint(-10, 10)
        next_x = max(20, min(MAP_WIDTH - 20, next_x))
        segments.append((round(next_x), round(next_y)))
        y = next_y

    return segments


def generate_rivers():
    rivers = []

    rx1_w1 = int(0.3 * 960)
    rx2_w1 = int(0.8 * 960)
    ry_center = 1106
    rivers.append({
        "name": "西河一",
        "segments": generate_river_horizontal(ry_center, rx1_w1, rx2_w1, (rx1_w1 + rx2_w1) // 2),
    })

    rx1_w2 = int(1.2 * 960)
    rx2_w2 = int(1.7 * 960)
    rivers.append({
        "name": "西河二",
        "segments": generate_river_horizontal(ry_center, rx1_w2, rx2_w2, (rx1_w2 + rx2_w2) // 2),
    })

    rx1_e1 = int(2.3 * 960)
    rx2_e1 = int(2.8 * 960)
    rivers.append({
        "name": "东河一",
        "segments": generate_river_horizontal(ry_center, rx1_e1, rx2_e1, (rx1_e1 + rx2_e1) // 2),
    })

    rx1_e2 = int(3.2 * 960)
    rx2_e2 = int(3.7 * 960)
    rivers.append({
        "name": "东河二",
        "segments": generate_river_horizontal(ry_center, rx1_e2, rx2_e2, (rx1_e2 + rx2_e2) // 2),
    })

    ry1_n = int(0.3 * 1080)
    ry2_n = int(0.8 * 1080)
    rx_center = 1922
    rivers.append({
        "name": "北纵河",
        "segments": generate_river_vertical(rx_center, ry1_n, ry2_n, (ry1_n + ry2_n) // 2),
    })

    ry1_s = int(1.2 * 1080)
    ry2_s = int(1.7 * 1080)
    rivers.append({
        "name": "南纵河",
        "segments": generate_river_vertical(rx_center, ry1_s, ry2_s, (ry1_s + ry2_s) // 2),
    })

    return rivers


def parse_cells(cells_str):
    cells = set()
    if not cells_str:
        return cells
    for part in cells_str.split(";"):
        if not part:
            continue
        r, c = part.split(",")
        cells.add((int(r), int(c)))
    return cells


def parse_vertices(vertices_str):
    vertices = []
    if not vertices_str:
        return vertices
    for part in vertices_str.split(";"):
        if not part:
            continue
        x, y = part.split(",")
        vertices.append((int(x), int(y)))
    return vertices


def parse_segments(segments_str):
    segments = []
    if not segments_str:
        return segments
    for part in segments_str.split("|"):
        if not part:
            continue
        x, y = part.split(";")
        segments.append((int(x), int(y)))
    return segments


def serialize_segments(segments):
    return "|".join(f"{x};{y}" for x, y in segments)


def _clear_global_cache():
    mountains_cache.clear()
    rivers_cache.clear()
    mountain_cells.clear()


async def init_terrain():
    _clear_global_cache()

    m_count = await get_mountain_count()
    r_count = await get_river_count()

    if m_count == 0 or r_count == 0:
        rivers = generate_rivers()
        mountains = generate_mountains(rivers)

        serialized_rivers = []
        for river in rivers:
            segments_str = serialize_segments(river["segments"])
            serialized_rivers.append({
                "name": river["name"],
                "segments": segments_str,
            })

        serialized_mountains = []
        for m in mountains:
            cells_str = ";".join(f"{r},{c}" for r, c in m["cells"])
            vertices_str = ";".join(f"{x},{y}" for x, y in m["vertices"])
            serialized_mountains.append({
                "name": m["name"],
                "cells": cells_str,
                "vertices": vertices_str,
                "size": m["size"],
            })

        await truncate_mountains()
        await truncate_rivers()
        await batch_insert_mountains(serialized_mountains)
        await batch_insert_rivers(serialized_rivers)
        m_rows = await get_all_mountains()
        r_rows = await get_all_rivers()
        logger.info(f"地形初始化完成，生成 {len(mountains)} 座山脉，{len(rivers)} 条河流")
    else:
        m_rows = await get_all_mountains()
        r_rows = await get_all_rivers()
        logger.info(f"从数据库加载 {len(m_rows)} 座山脉，{len(r_rows)} 条河流")

    for m in m_rows:
        mid = m["id"]
        mountains_cache[mid] = {
            "id": mid,
            "name": m["name"],
            "cells": parse_cells(m["cells"]),
            "vertices": parse_vertices(m["vertices"]),
            "size": m["size"],
        }
        for rc in mountains_cache[mid]["cells"]:
            mountain_cells.add(rc)

    for r in r_rows:
        rid = r["id"]
        rivers_cache[rid] = {
            "id": rid,
            "name": r["name"],
            "segments": parse_segments(r["segments"]),
        }

    return {
        "mountains": list(mountains_cache.values()),
        "rivers": list(rivers_cache.values()),
    }


async def expand_mountain_vertices():
    for mid, m in mountains_cache.items():
        new_vertices = _expand_mountain_to_cells(m["cells"], m["size"])
        m["vertices"] = new_vertices
        vertices_str = ";".join(f"{x},{y}" for x, y in new_vertices)
        await update_mountain_vertices(mid, vertices_str)
    logger.info(f"山脉顶点已扩展，共 {len(mountains_cache)} 座")


def get_all_terrain_from_cache():
    mountains = []
    for m in mountains_cache.values():
        mountains.append({
            "id": m["id"],
            "name": m["name"],
            "vertices": [list(v) for v in m["vertices"]],
            "cells": [list(c) for c in m["cells"]],
            "size": m["size"],
        })
    rivers = []
    for r in rivers_cache.values():
        rivers.append({
            "id": r["id"],
            "name": r["name"],
            "segments": [list(s) for s in r["segments"]],
        })
    return {"mountains": mountains, "rivers": rivers}


def is_cell_blocked(row, col):
    return (row, col) in mountain_cells


def get_all_river_segments():
    all_segments = []
    for river in rivers_cache.values():
        segs = []
        seg_list = river["segments"]
        for i in range(len(seg_list) - 1):
            segs.append((seg_list[i], seg_list[i + 1]))
        all_segments.extend(segs)
    return all_segments
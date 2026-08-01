import math
import random
import logging

from data.global_data import towns_cache, roads_cache, mountain_cells
from roads.roads_db import (
    batch_insert_roads,
    truncate_roads,
    get_all_roads,
    get_road_count,
)
from terrain.terrain_utils import (
    segments_cross as _segments_cross,
    position_to_grid,
    river_blocks_edge,
)

logger = logging.getLogger('36ji-server')

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

EDGE_THRESHOLD = 150


def _build_grid_map():
    grid_map = {}
    for town_id, town in towns_cache.items():
        row, col = _position_to_grid_index(town["pos_x"], town["pos_y"])
        grid_map[(row, col)] = town_id
    return grid_map


def _position_to_grid_index(px, py):
    col = (px - MARGIN - CELL_WIDTH // 2) / CELL_WIDTH
    row = (py - MARGIN - CELL_HEIGHT // 2) / CELL_HEIGHT
    return round(row), round(col)


def _get_neighbor(row, col, dr, dc, grid_map):
    return grid_map.get((row + dr, col + dc))


def _calc_euclidean_distance(t1, t2):
    return math.sqrt((t1["pos_x"] - t2["pos_x"]) ** 2 + (t1["pos_y"] - t2["pos_y"]) ** 2)


def _distance_to_tier(dist):
    if dist < 140:
        return 50
    elif dist < 160:
        return 75
    else:
        return 100


def _is_edge_town(town):
    return (
        town["pos_x"] <= EDGE_THRESHOLD
        or town["pos_x"] >= MAP_WIDTH - EDGE_THRESHOLD
        or town["pos_y"] <= EDGE_THRESHOLD
        or town["pos_y"] >= MAP_HEIGHT - EDGE_THRESHOLD
    )


def _get_direction_sector(angle_deg):
    angle_deg = (angle_deg + 360) % 360
    sector_boundaries = [
        (337.5, 360.0, "N"),
        (0.0, 22.5, "N"),
        (22.5, 67.5, "NE"),
        (67.5, 112.5, "E"),
        (112.5, 157.5, "SE"),
        (157.5, 202.5, "S"),
        (202.5, 247.5, "SW"),
        (247.5, 292.5, "W"),
        (292.5, 337.5, "NW"),
    ]
    for lo, hi, sector in sector_boundaries:
        if lo <= angle_deg < hi:
            return sector
    return "N"


def _road_intersects_existing(new_a, new_b, roads):
    p1 = (towns_cache[new_a]["pos_x"], towns_cache[new_a]["pos_y"])
    q1 = (towns_cache[new_b]["pos_x"], towns_cache[new_b]["pos_y"])
    for rd in roads:
        a, b = rd["start_town_id"], rd["end_town_id"]
        if a == new_a or a == new_b or b == new_a or b == new_b:
            continue
        p2 = (towns_cache[a]["pos_x"], towns_cache[a]["pos_y"])
        q2 = (towns_cache[b]["pos_x"], towns_cache[b]["pos_y"])
        if _segments_cross(p1, q1, p2, q2):
            return True
    return False


def _fix_degree_one(roads, degree, added, grid_map, river_segs):
    for town_id in towns_cache:
        if degree.get(town_id, 0) != 1:
            continue
        if _is_edge_town(towns_cache[town_id]):
            continue

        row, col = _position_to_grid_index(
            towns_cache[town_id]["pos_x"], towns_cache[town_id]["pos_y"]
        )

        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            neighbor_id = _get_neighbor(row, col, dr, dc, grid_map)
            if neighbor_id is None:
                continue
            edge_key = (min(town_id, neighbor_id), max(town_id, neighbor_id))
            if edge_key in added:
                continue
            if degree.get(neighbor_id, 0) >= 5:
                continue

            p1 = (towns_cache[town_id]["pos_x"], towns_cache[town_id]["pos_y"])
            p2 = (towns_cache[neighbor_id]["pos_x"], towns_cache[neighbor_id]["pos_y"])
            if river_blocks_edge(p1, p2, river_segs):
                continue
            if _road_intersects_existing(town_id, neighbor_id, roads):
                continue

            added.add(edge_key)
            dist = _calc_euclidean_distance(towns_cache[town_id], towns_cache[neighbor_id])
            roads.append({
                "start_town_id": min(town_id, neighbor_id),
                "end_town_id": max(town_id, neighbor_id),
                "distance": _distance_to_tier(dist),
            })
            degree[town_id] += 1
            degree[neighbor_id] += 1

        if degree.get(town_id, 0) >= 2:
            continue

        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1), (-1, 0), (1, 0), (0, -1), (0, 1)]:
            neighbor_id = _get_neighbor(row, col, dr, dc, grid_map)
            if neighbor_id is None:
                continue
            edge_key = (min(town_id, neighbor_id), max(town_id, neighbor_id))
            if edge_key in added:
                continue

            p1 = (towns_cache[town_id]["pos_x"], towns_cache[town_id]["pos_y"])
            p2 = (towns_cache[neighbor_id]["pos_x"], towns_cache[neighbor_id]["pos_y"])
            if river_blocks_edge(p1, p2, river_segs):
                continue
            if _road_intersects_existing(town_id, neighbor_id, roads):
                continue

            added.add(edge_key)
            dist = _calc_euclidean_distance(towns_cache[town_id], towns_cache[neighbor_id])
            roads.append({
                "start_town_id": min(town_id, neighbor_id),
                "end_town_id": max(town_id, neighbor_id),
                "distance": _distance_to_tier(dist),
            })
            degree[town_id] += 1
            degree[neighbor_id] += 1
            if degree.get(town_id, 0) >= 2:
                break


def _trim_initial_city_roads(roads, degree, added, grid_map):
    groups = [
        {"center": (0, 5), "others": [(0, 4), (0, 6), (1, 5)]},
        {"center": (0, COLS - 6), "others": [(0, COLS - 7), (0, COLS - 5), (1, COLS - 6)]},
        {"center": (ROWS - 1, 5), "others": [(ROWS - 1, 4), (ROWS - 1, 6), (ROWS - 2, 5)]},
        {"center": (ROWS - 1, COLS - 6), "others": [(ROWS - 1, COLS - 7), (ROWS - 1, COLS - 5), (ROWS - 2, COLS - 6)]},
    ]

    for group in groups:
        center_id = grid_map.get(group["center"])
        other_ids = [grid_map.get(pos) for pos in group["others"]]
        if center_id is None or any(oid is None for oid in other_ids):
            continue

        group_ids = {center_id, *other_ids}

        for rd in roads[:]:
            a, b = rd["start_town_id"], rd["end_town_id"]
            if center_id in (a, b):
                other = b if a == center_id else a
                if other not in group_ids:
                    roads.remove(rd)
                    added.discard((min(a, b), max(a, b)))
                    degree[a] -= 1
                    degree[b] -= 1

        for rd in roads[:]:
            a, b = rd["start_town_id"], rd["end_town_id"]
            if a in other_ids and b in other_ids:
                roads.remove(rd)
                added.discard((min(a, b), max(a, b)))
                degree[a] -= 1
                degree[b] -= 1

        for oid in other_ids:
            if degree[oid] >= 2:
                continue
            row, col = _position_to_grid_index(
                towns_cache[oid]["pos_x"], towns_cache[oid]["pos_y"]
            )
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                neighbor_id = _get_neighbor(row, col, dr, dc, grid_map)
                if neighbor_id is None or neighbor_id in group_ids:
                    continue
                edge_key = (min(oid, neighbor_id), max(oid, neighbor_id))
                if edge_key in added:
                    continue
                if degree.get(neighbor_id, 0) >= 5:
                    continue
                if _road_intersects_existing(oid, neighbor_id, roads):
                    continue
                added.add(edge_key)
                dist = _calc_euclidean_distance(towns_cache[oid], towns_cache[neighbor_id])
                roads.append({
                    "start_town_id": min(oid, neighbor_id),
                    "end_town_id": max(oid, neighbor_id),
                    "distance": _distance_to_tier(dist),
                })
                degree[oid] += 1
                degree[neighbor_id] += 1
                if degree[oid] >= 2:
                    break

        for oid in other_ids:
            edge_key = (min(center_id, oid), max(center_id, oid))
            if edge_key in added:
                continue
            other_deg = degree.get(oid, 0)
            if other_deg >= 5:
                continue
            found = False
            for rd in roads:
                a, b = rd["start_town_id"], rd["end_town_id"]
                if center_id in (a, b) and oid in (a, b):
                    found = True
                    break
            if found:
                continue
            added.add(edge_key)
            dist = _calc_euclidean_distance(towns_cache[center_id], towns_cache[oid])
            roads.append({
                "start_town_id": min(center_id, oid),
                "end_town_id": max(center_id, oid),
                "distance": _distance_to_tier(dist),
            })
            degree[center_id] += 1
            degree[oid] += 1


def generate_roads():
    from terrain.terrain_core import get_all_river_segments

    grid_map = _build_grid_map()
    river_segs = get_all_river_segments()

    roads = []
    added = set()
    degree = {}

    for town_id in towns_cache:
        degree[town_id] = 0

    for town_id, town in towns_cache.items():
        row, col = _position_to_grid_index(town["pos_x"], town["pos_y"])

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            neighbor_id = _get_neighbor(row, col, dr, dc, grid_map)
            if neighbor_id is None:
                continue
            edge_key = (min(town_id, neighbor_id), max(town_id, neighbor_id))
            if edge_key in added:
                continue

            p1 = (town["pos_x"], town["pos_y"])
            p2 = (towns_cache[neighbor_id]["pos_x"], towns_cache[neighbor_id]["pos_y"])
            if river_blocks_edge(p1, p2, river_segs):
                continue

            added.add(edge_key)
            dist = _calc_euclidean_distance(town, towns_cache[neighbor_id])
            roads.append({
                "start_town_id": min(town_id, neighbor_id),
                "end_town_id": max(town_id, neighbor_id),
                "distance": _distance_to_tier(dist),
            })
            degree[town_id] += 1
            degree[neighbor_id] += 1

    for row in range(0, ROWS - 1, 2):
        for col in range(0, COLS - 1, 2):
            tl = _get_neighbor(row, col, 0, 0, grid_map)
            tr = _get_neighbor(row, col, 0, 1, grid_map)
            bl = _get_neighbor(row, col, 1, 0, grid_map)
            br = _get_neighbor(row, col, 1, 1, grid_map)

            if tl is None or tr is None or bl is None or br is None:
                continue

            if ((row + col) // 2) % 2 == 0:
                a, b = tr, bl
            else:
                a, b = tl, br

            edge_key = (min(a, b), max(a, b))
            if edge_key in added:
                continue

            if degree[a] >= 5 or degree[b] >= 5:
                continue

            p1 = (towns_cache[a]["pos_x"], towns_cache[a]["pos_y"])
            p2 = (towns_cache[b]["pos_x"], towns_cache[b]["pos_y"])
            if river_blocks_edge(p1, p2, river_segs):
                continue

            added.add(edge_key)
            dist = _calc_euclidean_distance(towns_cache[a], towns_cache[b])
            roads.append({
                "start_town_id": min(a, b),
                "end_town_id": max(a, b),
                "distance": _distance_to_tier(dist),
            })
            degree[a] += 1
            degree[b] += 1

    _prune_roads(roads, degree, added)
    _fix_degree_one(roads, degree, added, grid_map, river_segs)
    _trim_initial_city_roads(roads, degree, added, grid_map)

    return roads


def _is_diagonal(town_id, neighbor_id):
    t1 = towns_cache[town_id]
    t2 = towns_cache[neighbor_id]
    r1, c1 = _position_to_grid_index(t1["pos_x"], t1["pos_y"])
    r2, c2 = _position_to_grid_index(t2["pos_x"], t2["pos_y"])
    return r1 != r2 and c1 != c2


def _bfs_connected(start, end, adjacency, removed_edge):
    visited = {start}
    queue = [start]
    while queue:
        cur = queue.pop(0)
        if cur == end:
            return True
        for nb in adjacency.get(cur, []):
            if nb in visited:
                continue
            if (cur, nb) == removed_edge or (nb, cur) == removed_edge:
                continue
            visited.add(nb)
            queue.append(nb)
    return False


def _prune_roads(roads, degree, added):
    edge_towns = [t for t in towns_cache if _is_edge_town(towns_cache[t])]
    interior_towns = [t for t in towns_cache if t not in edge_towns]
    random.shuffle(edge_towns)
    random.shuffle(interior_towns)

    edge_targets = {}
    edge_2 = int(len(edge_towns) * 0.40)
    edge_3 = int(len(edge_towns) * 0.50)
    edge_4 = len(edge_towns) - edge_2 - edge_3
    for i, t in enumerate(edge_towns):
        if i < edge_2:
            edge_targets[t] = 2
        elif i < edge_2 + edge_3:
            edge_targets[t] = 3
        else:
            edge_targets[t] = 4

    adjacency = {}
    for rd in roads:
        a, b = rd["start_town_id"], rd["end_town_id"]
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    for town_id in towns_cache:
        target = edge_targets.get(town_id, 5)
        current = degree[town_id]
        if current <= target:
            continue

        to_remove = current - target
        for _ in range(to_remove):
            neighbors = adjacency.get(town_id, [])
            if not neighbors:
                break

            neighbors.sort(key=lambda nb: (1 if _is_diagonal(town_id, nb) else 0, 1 if _is_edge_town(towns_cache.get(nb, {})) else 0))

            removed = False
            for nb in neighbors:
                nb_target = edge_targets.get(nb, 5)
                if degree[nb] - 1 < nb_target or degree[nb] - 1 < 2:
                    continue
                removed_edge = (min(town_id, nb), max(town_id, nb))
                if not _bfs_connected(town_id, nb, adjacency, removed_edge):
                    continue

                adjacency[town_id].remove(nb)
                adjacency[nb].remove(town_id)
                degree[town_id] -= 1
                degree[nb] -= 1
                removed = True
                break
            if not removed:
                break

    for town_id in towns_cache:
        target = edge_targets.get(town_id, 5)
        current = degree[town_id]
        if current <= target:
            continue

        to_remove = current - target
        for _ in range(to_remove):
            neighbors = adjacency.get(town_id, [])
            if not neighbors:
                break

            neighbors.sort(key=lambda nb: (0 if _is_diagonal(town_id, nb) else 1, 1 if _is_edge_town(towns_cache.get(nb, {})) else 0))

            removed = False
            for nb in neighbors:
                nb_target = edge_targets.get(nb, 5)
                if degree[nb] - 1 < nb_target or degree[nb] - 1 < 2:
                    continue
                removed_edge = (min(town_id, nb), max(town_id, nb))
                if not _bfs_connected(town_id, nb, adjacency, removed_edge):
                    continue

                adjacency[town_id].remove(nb)
                adjacency[nb].remove(town_id)
                degree[town_id] -= 1
                degree[nb] -= 1
                removed = True
                break
            if not removed:
                break

    pruned = []
    for rd in roads:
        a, b = rd["start_town_id"], rd["end_town_id"]
        if b in adjacency.get(a, []):
            pruned.append(rd)
    roads[:] = pruned
    added.clear()
    for rd in roads:
        added.add((min(rd["start_town_id"], rd["end_town_id"]), max(rd["start_town_id"], rd["end_town_id"])))

    edge_deg = {2: 0, 3: 0, 4: 0, 5: 0}
    interior_deg = {2: 0, 3: 0, 4: 0, 5: 0}
    for t in towns_cache:
        d = degree[t]
        if _is_edge_town(towns_cache[t]):
            edge_deg[d] = edge_deg.get(d, 0) + 1
        else:
            interior_deg[d] = interior_deg.get(d, 0) + 1
    logger.info(f"道路修剪完成，总计 {len(roads)} 条")
    logger.info(f"边缘度数: {edge_deg}")
    logger.info(f"内部度数: {interior_deg}")


def validate_roads(roads):
    errors = []

    degree = {tid: 0 for tid in towns_cache}
    edge_set = set()
    duplicate_edges = []

    for rd in roads:
        a, b = rd["start_town_id"], rd["end_town_id"]
        degree[a] += 1
        degree[b] += 1
        key = (min(a, b), max(a, b))
        if key in edge_set:
            duplicate_edges.append(key)
        edge_set.add(key)

    if duplicate_edges:
        errors.append(f"存在 {len(duplicate_edges)} 条重复道路")

    crossing_count = 0
    n = len(roads)
    for i in range(n):
        for j in range(i + 1, n):
            a1, b1 = roads[i]["start_town_id"], roads[i]["end_town_id"]
            a2, b2 = roads[j]["start_town_id"], roads[j]["end_town_id"]
            p1 = (towns_cache[a1]["pos_x"], towns_cache[a1]["pos_y"])
            q1 = (towns_cache[b1]["pos_x"], towns_cache[b1]["pos_y"])
            p2 = (towns_cache[a2]["pos_x"], towns_cache[a2]["pos_y"])
            q2 = (towns_cache[b2]["pos_x"], towns_cache[b2]["pos_y"])
            if _segments_cross(p1, q1, p2, q2):
                crossing_count += 1
                if crossing_count <= 5:
                    errors.append(f"道路交叉: ({a1},{b1}) 与 ({a2},{b2})")

    if crossing_count > 0:
        errors.append(f"共发现 {crossing_count} 处道路交叉")

    visited = set()
    stack = [list(towns_cache.keys())[0]]
    while stack:
        tid = stack.pop()
        if tid in visited:
            continue
        visited.add(tid)
        for rd in roads:
            a, b = rd["start_town_id"], rd["end_town_id"]
            if a == tid and b not in visited:
                stack.append(b)
            elif b == tid and a not in visited:
                stack.append(a)

    if len(visited) != len(towns_cache):
        errors.append(f"存在 {len(towns_cache) - len(visited)} 个孤立城池（非单连通域）")

    orphan = [tid for tid in towns_cache if degree[tid] == 0]
    if orphan:
        errors.append(f"存在 {len(orphan)} 个无道路城池")

    degree_one = [tid for tid in towns_cache if degree[tid] == 1]
    degree_one_ratio = len(degree_one) / len(towns_cache) * 100
    if degree_one_ratio > 2.0:
        errors.append(f"单道路城池占比 {degree_one_ratio:.1f}%，超过 2% 上限")

    non_edge_degree_one = [
        tid for tid in degree_one if not _is_edge_town(towns_cache[tid])
    ]
    if non_edge_degree_one:
        errors.append(f"存在 {len(non_edge_degree_one)} 个非边缘的单道路城池")

    over_degree = [tid for tid in towns_cache if degree[tid] > 5]
    if over_degree:
        errors.append(f"存在 {len(over_degree)} 个超过 5 条道路的城池")

    sector_violations = 0
    for tid in towns_cache:
        neighbors = []
        for rd in roads:
            a, b = rd["start_town_id"], rd["end_town_id"]
            if a == tid:
                neighbors.append(b)
            elif b == tid:
                neighbors.append(a)

        sectors = {}
        for nid in neighbors:
            dx = towns_cache[nid]["pos_x"] - towns_cache[tid]["pos_x"]
            dy = towns_cache[nid]["pos_y"] - towns_cache[tid]["pos_y"]
            angle = math.degrees(math.atan2(-dy, dx))
            if angle < 0:
                angle += 360
            sector = _get_direction_sector(angle)
            if sector in sectors:
                sector_violations += 1
                if sector_violations <= 5:
                    errors.append(f"城池 {tid} 在 {sector} 方向有多条道路")
            sectors[sector] = True

    if sector_violations > 0:
        errors.append(f"共发现 {sector_violations} 处方向扇区冲突")

    invalid_tiers = [rd for rd in roads if rd["distance"] not in (50, 75, 100)]
    if invalid_tiers:
        errors.append(f"存在 {len(invalid_tiers)} 条距离分档无效的道路")

    degree_dist = {}
    for d in degree.values():
        degree_dist[d] = degree_dist.get(d, 0) + 1

    if not errors:
        logger.info("道路验证全部通过")
        logger.info(f"道路总数: {len(roads)}")
        logger.info(
            "度数分布: "
            + ", ".join(
                f"度{k}: {v}个" for k, v in sorted(degree_dist.items())
            )
        )
        logger.info(f"单道路城池: {len(degree_one)} 个 ({degree_one_ratio:.1f}%)")
        logger.info(f"连通域: 1 个（全部 {len(towns_cache)} 个城池连通）")
    else:
        for e in errors:
            logger.error(e)

    return errors


async def init_roads():
    count = await get_road_count()

    if count == 0:
        town_count = len(towns_cache)
        if town_count == 0:
            await truncate_roads()
            logger.info("城池表为空，已清空道路表")
            return

        roads = generate_roads()
        validate_roads(roads)
        await batch_insert_roads(roads)
        roads_from_db = await get_all_roads()
        for rd in roads_from_db:
            roads_cache[rd["id"]] = dict(rd)
        logger.info(f"道路初始化完成，生成 {len(roads)} 条道路")
        return roads
    else:
        rows = await get_all_roads()
        for row in rows:
            roads_cache[row["id"]] = dict(row)
        roads = list(roads_cache.values())
        validate_roads(roads)
        logger.info(f"从数据库加载 {len(roads)} 条道路")
        return roads


def get_all_roads_from_cache():
    return list(roads_cache.values())


def get_roads_by_town_from_cache(town_id):
    return [
        rd for rd in roads_cache.values()
        if rd["start_town_id"] == town_id or rd["end_town_id"] == town_id
    ]
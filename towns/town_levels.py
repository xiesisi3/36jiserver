import random
import logging
from data.global_data import towns_cache, roads_cache
from towns.towns_db import batch_update_town_levels

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

LEVEL_ATTRS = {
    1:  {"forest": (0.60, 0.60), "fertile": (0.60, 0.60), "mine": (0.60, 0.60),
         "stability": 10000, "defense": 10000, "traffic": 10000},
    2:  {"forest": (0.89, 0.99), "fertile": (0.89, 0.99), "mine": (0.89, 0.99),
         "stability": 0, "defense": 0, "traffic": 0},
    3:  {"forest": (1.09, 1.19), "fertile": (1.09, 1.19), "mine": (1.09, 1.19),
         "stability": 0, "defense": 0, "traffic": 0},
    4:  {"forest": (1.49, 1.59), "fertile": (1.49, 1.59), "mine": (1.49, 1.59),
         "stability": 0, "defense": 0, "traffic": 0},
    5:  {"forest": (1.99, 2.09), "fertile": (1.99, 2.09), "mine": (1.99, 2.09),
         "stability": 0, "defense": 0, "traffic": 0},
    6:  {"forest": (2.49, 2.59), "fertile": (2.49, 2.59), "mine": (2.49, 2.59),
         "stability": 0, "defense": 100000, "traffic": 0},
}


def _build_adjacency():
    adj = {}
    for rd in roads_cache.values():
        a, b = rd["start_town_id"], rd["end_town_id"]
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


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


def _find_center_cross(grid_map):
    center_row = ROWS // 2
    center_col = COLS // 2

    center_id = grid_map.get((center_row, center_col))
    if center_id is None:
        for dr in range(1, 3):
            for dc in range(-dr, dr + 1):
                for r, c in [
                    (center_row + dr, center_col + dc),
                    (center_row - dr, center_col + dc),
                    (center_row + dc, center_col + dr),
                    (center_row + dc, center_col - dr),
                ]:
                    tid = grid_map.get((r, c))
                    if tid is not None:
                        center_row, center_col = r, c
                        center_id = tid
                        break
                if center_id is not None:
                    break
            if center_id is not None:
                break

    cross = []
    if center_id is not None:
        cross.append(center_id)

    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = center_row + dr, center_col + dc
        tid = grid_map.get((nr, nc))
        if tid is not None:
            cross.append(tid)
        else:
            for d in range(1, 3):
                for r2, c2 in [
                    (nr + d, nc),
                    (nr - d, nc),
                    (nr, nc + d),
                    (nr, nc - d),
                ]:
                    tid = grid_map.get((r2, c2))
                    if tid is not None:
                        cross.append(tid)
                        break
                if len(cross) > (len(cross) - len([x for x in cross if x is not None]) + 1):
                    break

    cross = list(dict.fromkeys(cross))
    return cross[:5]


def random_resource(lo, hi):
    return round(random.uniform(lo, hi), 2)


def _extend_from_seed(seed, adj, assigned_set, pool=None):
    if pool is None:
        pool = [n for n in adj.get(seed, []) if n not in assigned_set]
    if not pool:
        return []

    group = list(pool)

    while len(group) < 4:
        extender = random.choice(group)
        prev = seed
        if extender in pool:
            prev = seed
        else:
            for c in group:
                if extender in adj.get(c, []):
                    prev = c
                    break

        chain = [extender]
        current = extender
        for _ in range(2):
            candidates = [n for n in adj.get(current, [])
                          if n not in assigned_set and n not in group and n != prev]
            if not candidates:
                candidates = [n for n in adj.get(current, [])
                              if n not in assigned_set and n not in group]
            if not candidates:
                break
            nxt = random.choice(candidates)
            chain.append(nxt)
            prev = current
            current = nxt

        for c in chain[1:]:
            if c not in group:
                group.append(c)

        if len(group) >= 4:
            break

        if len(chain) >= 2:
            middle = chain[len(chain) // 2]
            candidates = [n for n in adj.get(middle, [])
                          if n not in assigned_set and n not in group]
            if candidates:
                group.append(random.choice(candidates))

        if len(group) >= 4:
            break

        extenders = [c for c in group
                     if any(n not in assigned_set and n not in group for n in adj.get(c, []))]
        if not extenders:
            break
        found = False
        for _ in range(len(extenders)):
            extender = random.choice(extenders)
            available = [n for n in adj.get(extender, [])
                         if n not in assigned_set and n not in group]
            if available:
                group.append(random.choice(available))
                found = True
                break
            extenders.remove(extender)
        if not found:
            break

    return group


def _find_l1_centers(l1_cities, adj):
    nation_groups = {}
    for tid in l1_cities:
        owner = towns_cache[tid].get("owner", 1)
        nation_groups.setdefault(owner, []).append(tid)

    centers = set()
    for city_ids in nation_groups.values():
        for tid in city_ids:
            l1_neighbors = [n for n in adj.get(tid, []) if n in city_ids]
            if len(l1_neighbors) >= 3:
                centers.add(tid)
                break
    return centers


def _bfs_collect(seeds, adj, exclude_set, target_count):
    collected = []
    frontier = list(seeds)
    visited = set(seeds) | exclude_set

    while len(collected) < target_count and frontier:
        next_frontier = []
        for node in frontier:
            for n in adj.get(node, []):
                if n not in visited:
                    visited.add(n)
                    collected.append(n)
                    next_frontier.append(n)
                    if len(collected) >= target_count:
                        break
            if len(collected) >= target_count:
                break
        frontier = next_frontier

    return collected


def _bfs_distance(seeds, target, adj, exclude_set):
    if target in seeds:
        return 0
    frontier = list(seeds)
    visited = set(seeds) | exclude_set
    dist = 0
    while frontier:
        dist += 1
        next_frontier = []
        for node in frontier:
            for n in adj.get(node, []):
                if n == target:
                    return dist
                if n not in visited:
                    visited.add(n)
                    next_frontier.append(n)
        frontier = next_frontier
    return 99999


def _bfs_distances(seeds, adj, exclude_set):
    dist_map = {}
    frontier = list(seeds)
    visited = set(seeds) | exclude_set
    dist = 0
    for s in seeds:
        if s not in exclude_set:
            dist_map[s] = 0
    while frontier:
        dist += 1
        next_frontier = []
        for node in frontier:
            for n in adj.get(node, []):
                if n not in visited:
                    visited.add(n)
                    dist_map[n] = dist
                    next_frontier.append(n)
        frontier = next_frontier
    return dist_map


def diffuse_town_levels():
    adj = _build_adjacency()
    grid_map = _build_grid_map()

    assigned = {}
    assigned_set = set()

    l1_nation_ids = {2, 3, 4, 5}
    l1_cities = [tid for tid, t in towns_cache.items() if t.get("owner", 1) in l1_nation_ids]
    l1_centers = _find_l1_centers(l1_cities, adj)
    l1_non_centers = [tid for tid in l1_cities if tid not in l1_centers]

    for tid in l1_cities:
        assigned[tid] = 1
        assigned_set.add(tid)

    logger.info(f"L1: {len(l1_cities)} 城 (中心 {len(l1_centers)}，非中心 {len(l1_non_centers)})")

    nation_groups = {}
    for seed in l1_non_centers:
        owner = towns_cache[seed].get("owner", 1)
        nation_groups.setdefault(owner, []).append(seed)

    l2_groups = {}
    l2_cities = []

    for _nation_id, seeds in nation_groups.items():
        pool = _bfs_collect(seeds, adj, assigned_set, 12)
        assignments = {seed: [] for seed in seeds}
        assigned_nation = set()

        seeds_sorted = sorted(seeds, key=lambda s: len(
            [n for n in adj.get(s, []) if n not in assigned_set]))
        for seed in seeds_sorted:
            for n in adj.get(seed, []):
                if n in pool and n not in assigned_set and n not in assigned_nation and len(assignments[seed]) < 4:
                    assignments[seed].append(n)
                    assigned_nation.add(n)

        remaining = [n for n in pool if n not in assigned_nation]
        for seed in seeds:
            while len(assignments[seed]) < 4 and remaining:
                n = remaining.pop(0)
                if n not in assigned_nation:
                    assignments[seed].append(n)
                    assigned_nation.add(n)

        for seed in seeds:
            g = assignments[seed]
            l2_groups[seed] = g
            for tid in g:
                assigned[tid] = 2
                assigned_set.add(tid)
            l2_cities.extend(g)

    logger.info(f"L2: {len(l2_cities)} 城 ({len(l2_groups)} 组)")

    l3_cities = []

    # Step 1: 所有 48 个 L2 的直接邻居全部初始化为 L3
    for seed, l2_nodes in l2_groups.items():
        for l2_node in l2_nodes:
            for n in adj.get(l2_node, []):
                if n not in assigned_set:
                    assigned[n] = 3
                    assigned_set.add(n)
                    l3_cities.append(n)

    logger.info(f"L3 初始 (L2 邻居): {len(l3_cities)} 城")

    # Step 2: 逐组检查，不足 12 个则 BFS 扩张（按初始 L3 数量升序，最缺的优先）
    group_info = []
    for seed, l2_nodes in l2_groups.items():
        group_l3 = set()
        for l2_node in l2_nodes:
            for n in adj.get(l2_node, []):
                if assigned.get(n) == 3:
                    group_l3.add(n)
        group_info.append((len(group_l3), seed, l2_nodes))

    group_info.sort(key=lambda x: x[0])

    region_stats = {}  # nation -> {init_total, added_total, groups}
    for init_count, seed, l2_nodes in group_info:
        if init_count >= 12:
            continue

        needed = 12 - init_count
        l1_l2_set = {tid for tid, lv in assigned.items() if lv in (1, 2)}
        pool_raw = _bfs_collect(l2_nodes, adj, l1_l2_set, 99999)
        pool = [n for n in pool_raw if assigned.get(n) != 3]
        added = 0
        for n in pool[:needed]:
            if n not in assigned_set:
                assigned[n] = 3
                assigned_set.add(n)
                l3_cities.append(n)
                added += 1

        owner = towns_cache[seed].get("owner", "?")
        region_stats.setdefault(owner, {"init": 0, "added": 0, "groups": 0})
        region_stats[owner]["init"] += init_count
        region_stats[owner]["added"] += added
        region_stats[owner]["groups"] += 1

    logger.info(f"L3: {len(l3_cities)} 城")

    # Step 3: 按区域补充，确保每个区域都有 36 个 L3（弥补共享节点导致的缺口）
    # 用 BFS 距离将每个 L3 节点归属到最近的区域
    region_l2 = {}  # nation -> list of L2 node ids
    for seed, nodes in l2_groups.items():
        owner = towns_cache[seed].get("owner", "?")
        region_l2.setdefault(owner, []).extend(nodes)

    l1_l2_set = {tid for tid, lv in assigned.items() if lv in (1, 2)}
    # 预计算每个区域到所有节点的 BFS 距离
    region_dist = {}
    for nation, l2_nodes in region_l2.items():
        region_dist[nation] = _bfs_distances(l2_nodes, adj, l1_l2_set)

    # 每个 L3 归属到距离最近的区域
    region_l3 = {nation: set() for nation in region_l2}
    for l3_node in l3_cities:
        best_nation = min(region_l2.keys(),
                          key=lambda n: region_dist[n].get(l3_node, 99999))
        region_l3[best_nation].add(l3_node)

    global_l3_before = len(l3_cities)
    for nation in sorted(region_l3.keys()):
        current = len(region_l3[nation])
        if current >= 36:
            continue
        needed = 36 - current
        pool = _bfs_collect(region_l2[nation], adj, l1_l2_set, 99999)
        pool = [n for n in pool if assigned.get(n) != 3]
        added = 0
        for n in pool:
            if added >= needed:
                break
            if n not in assigned_set:
                assigned[n] = 3
                assigned_set.add(n)
                l3_cities.append(n)
                added += 1

    total_added = len(l3_cities) - global_l3_before
    if total_added > 0:
        logger.info(f"L3 区域补充总计: +{total_added} → {len(l3_cities)} 城")

    l4_cities = []
    for seed in l3_cities:
        group = _extend_from_seed(seed, adj, assigned_set)
        g = group[:4]
        for tid in g:
            assigned[tid] = 4
            assigned_set.add(tid)
        l4_cities.extend(g)
    logger.info(f"L4: {len(l4_cities)} 城")

    l5_cities = []
    for seed in l4_cities:
        group = _extend_from_seed(seed, adj, assigned_set)
        g = group[:4]
        for tid in g:
            assigned[tid] = 5
            assigned_set.add(tid)
        l5_cities.extend(g)
    logger.info(f"L5: {len(l5_cities)} 城")

    l6_cross = _find_center_cross(grid_map)
    l6_cross_unassigned = [tid for tid in l6_cross if tid not in assigned_set]
    for tid in l6_cross:
        assigned[tid] = 6
        assigned_set.add(tid)
    logger.info(f"L6 十字: {len(l6_cross)} 城 (其中 {len(l6_cross_unassigned)} 个未被分配)，IDs: {l6_cross}")

    level_cycle = [5, 4]
    current_level_idx = 0
    wavefront = set(l6_cross)
    while wavefront:
        next_level = level_cycle[current_level_idx % 2]
        next_wave = set()
        for tid in wavefront:
            for nid in adj.get(tid, []):
                if nid not in assigned_set:
                    assigned[nid] = next_level
                    assigned_set.add(nid)
                    next_wave.add(nid)
        wavefront = next_wave
        current_level_idx += 1

    cycle2 = [4, 5]
    idx2 = 0
    last_wave = set()
    for tid in assigned_set:
        if assigned.get(tid) == 5:
            for nid in adj.get(tid, []):
                if nid not in assigned_set:
                    last_wave.add(nid)
    while last_wave:
        next_level = cycle2[idx2 % 2]
        next_wave = set()
        for tid in last_wave:
            if tid not in assigned_set:
                assigned[tid] = next_level
                assigned_set.add(tid)
            for nid in adj.get(tid, []):
                if nid not in assigned_set:
                    next_wave.add(nid)
        last_wave = next_wave
        idx2 += 1

    unassigned = [tid for tid in towns_cache if tid not in assigned_set]
    for tid in unassigned:
        assigned[tid] = random.choice([4, 5])
        assigned_set.add(tid)

    logger.info(f"等级扩散完成，L4/L5 交替填充 {len(unassigned)} 个剩余城池")

    all_assigned = len(assigned_set) == len(towns_cache)
    logger.info(f"全部城池已分配等级: {all_assigned} ({len(assigned_set)}/{len(towns_cache)})")

    dist = {}
    for tid, lv in assigned.items():
        dist.setdefault(lv, 0)
        dist[lv] += 1
    logger.info(f"等级分布: {dict(sorted(dist.items()))}")

    return assigned
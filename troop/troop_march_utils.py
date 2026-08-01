# 行军工具函数
# 最短路径(Dijkstra)、目标城池生成、行军时间计算、粮食消耗、城门坐标

import math
import heapq
import logging

from data.global_data import towns_cache, roads_cache, user_nation_cache
from data.troop_data import TROOP_DATA
from server_timer.server_timer_core import get_uptime_ms
from troop.troop_march_constants import (
    TRAFFIC_COEFFICIENT_TABLE,
    TRAVEL_TIME_BASE,
    FOOD_DISTANCE_FACTOR,
    MAX_MARCH_DELAY,
    ACCEL_FACTOR_30,
    ACCEL_FACTOR_50,
    ACCEL_FACTOR_NONE,
)

logger = logging.getLogger('36ji-server')


def _build_adjacency():
    adj = {}
    for rd in roads_cache.values():
        a, b = rd["start_town_id"], rd["end_town_id"]
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


def _build_weighted_adjacency():
    adj = {}
    for rd in roads_cache.values():
        a, b = rd["start_town_id"], rd["end_town_id"]
        d = rd.get("distance", 1)
        adj.setdefault(a, []).append((b, d))
        adj.setdefault(b, []).append((a, d))
    return adj


def dijkstra_shortest_path(source_town_id, target_town_id):
    """Dijkstra 最短路径，返回 (total_distance, path_town_ids)"""
    if source_town_id == target_town_id:
        return 0, [source_town_id]

    if source_town_id not in towns_cache or target_town_id not in towns_cache:
        return None, []

    adj = _build_weighted_adjacency()

    dist = {source_town_id: 0}
    prev = {source_town_id: None}
    pq = [(0, source_town_id)]
    visited = set()

    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)

        if u == target_town_id:
            break

        for v, w in adj.get(u, []):
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))

    if target_town_id not in dist:
        return None, []

    path = []
    cur = target_town_id
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return dist[target_town_id], path


def get_traffic_multiplier(traffic_value):
    """根据城池交通值获取速度系数"""
    for entry in TRAFFIC_COEFFICIENT_TABLE:
        if entry["min"] <= traffic_value <= entry["max"]:
            return entry["speed_multiplier"]
    return 1.0


def get_troop_min_speed(team):
    """获取部队中最慢兵种的速度值"""
    min_speed = None
    for slot in team:
        if not slot:
            continue
        troop_name = slot.get("兵种名称", "")
        count = slot.get("数量", 0)
        if not troop_name or count <= 0:
            continue
        for t in TROOP_DATA:
            if t["兵种名称"] == troop_name:
                spd = t.get("速度", 0)
                if spd > 0 and (min_speed is None or spd < min_speed):
                    min_speed = spd
                break
    return min_speed if min_speed is not None else 1


def get_troop_attack_food_cost(troop_name):
    """获取兵种攻击消耗粮食"""
    for t in TROOP_DATA:
        if t["兵种名称"] == troop_name:
            return t.get("攻击消耗粮食", 0)
    return 0


def calculate_travel_time_seconds(distance, min_speed, source_traffic, target_traffic):
    """计算行军时间（秒）

    公式: minutes = distance * 14 / min_speed / source_mult / target_mult
    返回: int 秒数
    """
    source_mult = get_traffic_multiplier(source_traffic)
    target_mult = get_traffic_multiplier(target_traffic)

    if min_speed <= 0 or source_mult <= 0 or target_mult <= 0:
        return 0

    minutes = distance * TRAVEL_TIME_BASE / min_speed / source_mult / target_mult
    seconds = math.ceil(minutes * 60)
    return seconds


def calculate_march_food(team, total_distance):
    """计算行军粮食消耗

    公式: 单兵消耗 = ceil(总路径距离 × 攻击消耗粮食 / 250)
    部队总消耗 = Σ(各槽位单兵消耗 × 该槽位兵力数量)
    """
    total_food = 0
    for slot in team:
        if not slot:
            continue
        troop_name = slot.get("兵种名称", "")
        count = slot.get("数量", 0)
        if not troop_name or count <= 0:
            continue
        attack_food = get_troop_attack_food_cost(troop_name)
        if attack_food <= 0:
            continue
        per_unit = math.ceil(total_distance * attack_food / FOOD_DISTANCE_FACTOR)
        total_food += per_unit * count
    return total_food


def get_gate_position(source_town_id, target_town_id, path_town_ids):
    """根据行军路径最后一程方向，计算目标城池的城门坐标

    外城网格 19×19，坐标体系: x=纵向(行,0-18), y=横向(列,0-18)
    城门坐标:
        上: (0, 9), 下: (18, 9), 左: (9, 0), 右: (9, 18)
    方向由路径倒数第二个城池与目标城池的坐标差决定
    """
    if len(path_town_ids) < 2:
        return 10, 9

    second_last_id = path_town_ids[-2]
    last_id = path_town_ids[-1]

    src_town = towns_cache.get(second_last_id)
    dst_town = towns_cache.get(last_id)
    if not src_town or not dst_town:
        return 10, 9

    dx = dst_town["pos_x"] - src_town["pos_x"]
    dy = dst_town["pos_y"] - src_town["pos_y"]

    if abs(dx) >= abs(dy):
        if dx > 0:
            return 9, 0
        else:
            return 9, 18
    else:
        if dy > 0:
            return 0, 9
        else:
            return 18, 9


def get_march_targets(user_nation_id, source_town_id):
    """获取可出征目标城池列表

    包含:
    1. 本国所有城池（排除出发城池）
    2. 本国城池紧挨着的邻接城池（非本国）

    优化: 跳过内部城池（所有邻居都是本国城池的）
    """
    adj = _build_adjacency()

    nation_towns = set()
    for town_id, town in towns_cache.items():
        if town.get("owner") == user_nation_id:
            nation_towns.add(town_id)

    targets = set()
    for town_id in nation_towns:
        if town_id == source_town_id:
            continue

        all_neighbors_nation = True
        for neighbor in adj.get(town_id, []):
            if neighbor not in nation_towns:
                all_neighbors_nation = False
                targets.add(neighbor)

        if not all_neighbors_nation or town_id not in targets:
            targets.add(town_id)

    for neighbor in adj.get(source_town_id, []):
        if neighbor not in nation_towns:
            targets.add(neighbor)

    if source_town_id in targets:
        targets.discard(source_town_id)

    result = []
    for town_id in targets:
        town = towns_cache[town_id]
        result.append({
            "town_id": town_id,
            "name": town.get("name", ""),
            "owner": town.get("owner", 0),
            "is_nation": town_id in nation_towns,
        })
    return result


def calc_batch_time_range(troop_list, source_town_id, target_town_id, accel_factors=None):
    """计算批量出征（自定义到达时间）的目标时间范围

    accel_factors: {troop_id: accel_factor} 字典，None 表示全部无加速
    返回: (earliest_arrive_ms, latest_arrive_ms)
    earliest: now + max(各部队加速后行军时间)
    latest: now + min(各部队加速后行军时间) + MAX_MARCH_DELAY
    """
    total_distance, path = dijkstra_shortest_path(source_town_id, target_town_id)
    if total_distance is None:
        return None, None

    source_town = towns_cache.get(source_town_id)
    target_town = towns_cache.get(target_town_id)
    if not source_town or not target_town:
        return None, None

    source_traffic = source_town.get("traffic", 10000)
    target_traffic = target_town.get("traffic", 10000)

    now_ms = get_uptime_ms()

    accelerated_times = []
    for troop in troop_list:
        tid = troop.get("id")
        team = troop.get("team", [])
        min_speed = get_troop_min_speed(team)
        travel_seconds = calculate_travel_time_seconds(
            total_distance, min_speed, source_traffic, target_traffic
        )
        factor = accel_factors.get(tid, 1.0) if accel_factors else 1.0
        accelerated_seconds = math.ceil(travel_seconds * factor)
        accelerated_times.append(accelerated_seconds)

    if not accelerated_times:
        return None, None

    earliest_arrive = now_ms + max(accelerated_times) * 1000
    latest_arrive = now_ms + min(accelerated_times) * 1000 + MAX_MARCH_DELAY * 1000

    return earliest_arrive, latest_arrive


def can_troops_arrive_at_time(troop_list, source_town_id, target_town_id, target_time_ms, accel_factors=None):
    """检查所有部队是否能在指定时间到达（用于自定义到达时间模式）

    accel_factors: {troop_id: accel_factor} 字典，None 表示全部无加速
    返回: (bool, [troop_errors])
    """
    total_distance, path = dijkstra_shortest_path(source_town_id, target_town_id)
    if total_distance is None:
        return False, ["路径不存在"]

    source_town = towns_cache.get(source_town_id)
    target_town = towns_cache.get(target_town_id)
    if not source_town or not target_town:
        return False, ["城池数据不存在"]

    source_traffic = source_town.get("traffic", 10000)
    target_traffic = target_town.get("traffic", 10000)

    now_ms = get_uptime_ms()

    errors = []
    for i, troop in enumerate(troop_list):
        tid = troop.get("id")
        team = troop.get("team", [])
        min_speed = get_troop_min_speed(team)
        travel_seconds = calculate_travel_time_seconds(
            total_distance, min_speed, source_traffic, target_traffic
        )
        factor = accel_factors.get(tid, 1.0) if accel_factors else 1.0
        accelerated_seconds = math.ceil(travel_seconds * factor)

        depart_time_ms = target_time_ms - accelerated_seconds * 1000

        if depart_time_ms < now_ms:
            errors.append(f"部队{i + 1}(ID:{tid}): 无法在指定时间到达，需要提前出发")
            continue

        max_depart_time_ms = now_ms + MAX_MARCH_DELAY * 1000
        if depart_time_ms > max_depart_time_ms:
            errors.append(f"部队{i + 1}(ID:{tid}): 出发时间超过最大延迟")

    return len(errors) == 0, errors
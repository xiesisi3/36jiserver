import copy
import logging
import random
from collections import deque

logger = logging.getLogger("36ji-server")

# 战斗棋盘尺寸
GRID_ROWS = 19
GRID_COLS = 19

# 战斗动画时间常量（毫秒），用于客户端播放战斗动画
MOVE_STEP_TIME_MS = 400       # 每移动一格耗时
WAIT_STEP_TIME_MS = 500       # 每步等待间隔
COMBAT_INITIAL_DELAY = 600    # 攻击前初始延迟
COMBAT_ACTION_INTERVAL = 800  # 每个子动作间隔
COMBAT_FINAL_DELAY = 800      # 攻击后收尾延迟

# BFS搜索四方向（上下左右）
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def is_valid_cell(r, c):
    """判断坐标是否在棋盘范围内"""
    return 0 <= r < GRID_ROWS and 0 <= c < GRID_COLS


def get_troop_owner(troop, user_nation_cache):
    """
    获取部队所属国家编号。
    user_nation_cache: {user_id: nation_id}，NPC部队user_id为'0'时返回0。

    优先级：_nation > user_nation_cache[user_id]
    _nation 字段用于民兵（义勇军/连弩）等特殊NPC部队，
    这些部队 user_id="0" 但需要通过 _nation 标记所属国家以正确判断敌我。
    正常玩家部队和山贼部队不携带 _nation 字段，走原始逻辑。
    """
    if troop is None:
        return None
    _nation = troop.get("_nation")
    if _nation is not None:
        return _nation
    raw_user_id = troop.get("user_id", "")
    user_id = str(raw_user_id) if raw_user_id is not None else ""
    return user_nation_cache.get(user_id, 0)


def is_enemy(troop_a, troop_b, user_nation_cache):
    """
    判断两支部队是否为敌对关系。
    规则：所属国家不同即为敌对；但两支NPC部队（owner均为0）之间不算敌对。
    """
    owner_a = get_troop_owner(troop_a, user_nation_cache)
    owner_b = get_troop_owner(troop_b, user_nation_cache)
    if owner_a is None or owner_b is None:
        return False
    if owner_a == 0 and owner_b == 0:
        return False
    return owner_a != owner_b


def is_troop_alive(troop):
    """判断部队是否存活（至少有一个槽位的兵种数量 > 0）"""
    if troop is None:
        return False
    team = troop.get("team", [])
    for slot in team:
        if slot and slot.get("兵种名称") and slot.get("数量", 0) > 0:
            return True
    return False


def get_troop_move_range(troop):
    """
    获取部队的移动范围（取所有存活槽位中移动范围的最小值）。
    因为部队整体移动受最慢兵种限制。

    注意：防守方部队在城池交通值为最高档位（皇家大道，90000-100000）时，
    移动力+1，该加成由 process_round_logic 在战斗开始前通过 _traffic_move_bonus 字段注入。
    """
    team = troop.get("team", [])
    min_range = None
    for slot in team:
        if not slot:
            continue
        name = slot.get("兵种名称", "")
        if not name:
            continue
        count = slot.get("数量", 0)
        if count <= 0:
            continue
        from data.troop_data import TROOP_DATA, TROOP_DATA_SPECIAL
        for t in TROOP_DATA:
            if t["兵种名称"] == name:
                move_range = t.get("战斗移动范围", 3)
                if min_range is None or move_range < min_range:
                    min_range = move_range
                break
        else:
            for t in TROOP_DATA_SPECIAL:
                if t["兵种名称"] == name:
                    move_range = t.get("战斗移动范围", 3)
                    if min_range is None or move_range < min_range:
                        min_range = move_range
                    break
    base = min_range if min_range is not None else 3
    base += troop.get("_traffic_move_bonus", 0)
    return base


def _bfs_full_range(start_pos, unmovable_set, max_range):
    """
    标准BFS搜索，从起点出发探索max_range步内的所有可达格子。
    unmovable_set: 不可通行的格子集合（城门位置、中心格等）。
    返回 (dist矩阵, prev矩阵)：
    - dist[r][c]: 起点到(r,c)的步数，-1表示不可达
    - prev[r][c]: (r,c)在BFS路径上的前驱坐标，用于路径重建
    """
    rows, cols = GRID_ROWS, GRID_COLS
    dist = [[-1] * cols for _ in range(rows)]
    prev = [[None] * cols for _ in range(rows)]
    sr, sc = start_pos
    if not (0 <= sr < rows and 0 <= sc < cols):
        return dist, prev
    dist[sr][sc] = 0
    q = deque()
    q.append((sr, sc))
    while q:
        r, c = q.popleft()
        if dist[r][c] >= max_range:
            continue
        for dr, dc in DIRECTIONS:
            nr, nc = r + dr, c + dc
            if not is_valid_cell(nr, nc):
                continue
            if (nr, nc) in unmovable_set:
                continue
            if dist[nr][nc] == -1:
                dist[nr][nc] = dist[r][c] + 1
                prev[nr][nc] = (r, c)
                q.append((nr, nc))
    return dist, prev


def _reconstruct_path(start_pos, target_pos, prev):
    """
    从prev矩阵重建从start_pos到target_pos的路径（不含起点）。
    返回路径列表 [step1, step2, ..., target_pos]，若不可达则返回None。
    """
    path = []
    cur = target_pos
    while cur is not None and cur != start_pos:
        path.append(cur)
        cur = prev[cur[0]][cur[1]]
    if cur is None:
        return None
    path.reverse()
    return path


def _get_troop_first_slot_attack(troop, skip_zero=False):
    """
    获取部队第一个有效攻击槽位的攻击力（攻击力 × 数量）。
    遍历槽位，找到第一个数量>0且攻击力>0的槽位。
    skip_zero=True时：跳过攻击力为0的槽位（如运输兵），用于"最高攻击"目标选择，
    避免因运输兵占第一个槽位而导致攻击力被误判为0。
    skip_zero=False时：遇到攻击力为0的槽位直接返回0，用于"最低攻击"目标选择。
    """
    team = troop.get("team", [])
    from data.troop_data import TROOP_DATA, TROOP_DATA_SPECIAL
    for slot in team:
        if slot and slot.get("兵种名称"):
            name = slot["兵种名称"]
            count = slot.get("数量", 0)
            if count > 0:
                for t in TROOP_DATA:
                    if t["兵种名称"] == name:
                        atk = t.get("攻击力", 0)
                        if atk > 0:
                            return atk * count
                        break
                else:
                    for t in TROOP_DATA_SPECIAL:
                        if t["兵种名称"] == name:
                            atk = t.get("攻击力", 0)
                            if atk > 0:
                                return atk * count
                            break
                if skip_zero:
                    continue
                return 0
    return 0


def _get_troop_total_soldiers(troop):
    """获取部队总兵力（所有槽位数量之和）"""
    total = 0
    for slot in (troop.get("team") or []):
        if slot and slot.get("兵种名称"):
            total += slot.get("数量", 0)
    return total


def _select_target_by_type(current_troop, all_troops, dist_map, target_type, user_nation_cache):
    enemies = []
    for t in all_troops:
        if not is_enemy(current_troop, t, user_nation_cache):
            continue
        if not is_troop_alive(t):
            continue
        pos = t.get("grid_pos")
        if not pos:
            continue
        pos = tuple(pos)
        d = dist_map[pos[0]][pos[1]]
        if d == -1:
            continue
        enemies.append((t, d))

    if not enemies:
        return None

    if target_type == "highest_attack":
        enemies.sort(key=lambda x: (-_get_troop_first_slot_attack(x[0], skip_zero=True), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "lowest_attack":
        enemies.sort(key=lambda x: (_get_troop_first_slot_attack(x[0]), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "most_food":
        enemies.sort(key=lambda x: (-x[0].get("food", 0), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "most_troops":
        enemies.sort(key=lambda x: (-_get_troop_total_soldiers(x[0]), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "fewest_troops":
        enemies.sort(key=lambda x: (_get_troop_total_soldiers(x[0]), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    else:
        enemies.sort(key=lambda x: (x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))

    return enemies[0][0]


def _select_nearest_enemy_in_range(current_troop, all_troops, dist_map, max_range, user_nation_cache):
    """
    在BFS已探索的范围内，找到距离最近的敌军。
    同距离时按创建时间、更新时间排序（先创建的优先）。
    此处只负责选目标，不关心路径。
    """
    best_enemy = None
    best_dist = float('inf')
    best_create_time = float('inf')
    best_update_time = float('inf')

    for t in all_troops:
        if not is_enemy(current_troop, t, user_nation_cache):
            continue
        if not is_troop_alive(t):
            continue
        pos = t.get("grid_pos")
        if not pos:
            continue
        pos = tuple(pos)
        d = dist_map[pos[0]][pos[1]]
        if d == -1 or d > max_range:
            continue
        ct = t.get("create_time", 0)
        ut = t.get("update_time", 0)
        if d < best_dist or (d == best_dist and ct < best_create_time) or (d == best_dist and ct == best_create_time and ut < best_update_time):
            best_enemy = t
            best_dist = d
            best_create_time = ct
            best_update_time = ut

    return best_enemy


def _find_nearest_target_with_expanding_bfs(current_troop, all_troops, unmovable_set, move_range, user_nation_cache):
    """
    策略A：「最近」目标选择。
    关键设计：BFS不能提前对全图做（因为部队行动后位置会变），必须在每支部队轮到自己行动时
    才执行BFS，保证"最近"的定义是基于当前实时战场状态的。

    优化策略：先以move_range为初始范围做BFS，若找到敌军则直接返回，避免全图BFS。
    若move_range内无敌军，则逐层扩展BFS范围（每次扩展move_range步），
    直到找到第一个敌军或探索完所有可达格子。每次扩展复用已有的BFS队列和距离矩阵，
    不需要重新开始，总计只做一次BFS，且会在找到第一个敌军时提前终止。
    """
    start_pos = tuple(current_troop.get("grid_pos", []))
    if not start_pos:
        return None, None, None, None

    dist = [[-1] * GRID_COLS for _ in range(GRID_ROWS)]
    prev = [[None] * GRID_COLS for _ in range(GRID_ROWS)]
    dist[start_pos[0]][start_pos[1]] = 0
    q = deque([start_pos])

    current_max_range = move_range
    max_possible = GRID_ROWS * GRID_COLS

    while current_max_range <= max_possible:
        # 继续BFS，处理当前层（距离 < current_max_range 的所有格子）
        while q:
            r, c = q[0]
            d = dist[r][c]
            if d >= current_max_range:
                break
            q.popleft()
            for dr, dc in DIRECTIONS:
                nr, nc = r + dr, c + dc
                if not is_valid_cell(nr, nc):
                    continue
                if (nr, nc) in unmovable_set:
                    continue
                if dist[nr][nc] == -1:
                    dist[nr][nc] = d + 1
                    prev[nr][nc] = (r, c)
                    q.append((nr, nc))

        # 检查当前范围内是否有敌军
        target = _select_nearest_enemy_in_range(current_troop, all_troops, dist, current_max_range, user_nation_cache)
        if target is not None:
            target_pos = tuple(target.get("grid_pos", []))
            bfs_dist = dist[target_pos[0]][target_pos[1]]
            path = _reconstruct_path(start_pos, target_pos, prev)
            if path is None:
                path = []
            return target_pos, path, bfs_dist, target

        if not q:
            break

        current_max_range += move_range

    return None, None, None, None


def _find_target_by_criteria_with_reverse_bfs(current_troop, all_troops, unmovable_set, move_range, target_type, user_nation_cache):
    """
    策略B：非「最近」目标选择（最高攻击、最低攻击、最大粮食、最大兵力、最少兵力）。
    选目标时不依赖BFS，而是直接遍历所有部队按对应属性排序取最优。
    然后对选中的目标做逆向BFS（从目标位置出发搜索到当前部队位置），判可达性。

    可达：用逆向路径反转后作为移动路径。
    不可达：不退到次优目标（避免连环BFS），而是退回到策略A（最近目标）。
    因为被挡住说明挡路的敌军必然很近，策略A的BFS很快就能找到目标。
    每支部队最多2次BFS。
    """
    start_pos = tuple(current_troop.get("grid_pos", []))
    if not start_pos:
        return None, None, None, None

    # 收集所有存活敌军（不需要BFS，直接遍历部队列表）
    enemies = []
    for t in all_troops:
        if not is_enemy(current_troop, t, user_nation_cache):
            continue
        if not is_troop_alive(t):
            continue
        if not t.get("grid_pos"):
            continue
        enemies.append(t)

    if not enemies:
        return None, None, None, None

    # 按目标类型排序，取最优
    if target_type == "highest_attack":
        enemies.sort(key=lambda x: (-_get_troop_first_slot_attack(x, skip_zero=True),
                                     x.get("create_time", 0), x.get("update_time", 0)))
    elif target_type == "lowest_attack":
        enemies.sort(key=lambda x: (_get_troop_first_slot_attack(x),
                                     x.get("create_time", 0), x.get("update_time", 0)))
    elif target_type == "most_food":
        enemies.sort(key=lambda x: (-x.get("food", 0),
                                     x.get("create_time", 0), x.get("update_time", 0)))
    elif target_type == "most_troops":
        enemies.sort(key=lambda x: (-_get_troop_total_soldiers(x),
                                     x.get("create_time", 0), x.get("update_time", 0)))
    elif target_type == "fewest_troops":
        enemies.sort(key=lambda x: (_get_troop_total_soldiers(x),
                                     x.get("create_time", 0), x.get("update_time", 0)))
    else:
        enemies.sort(key=lambda x: (x.get("create_time", 0), x.get("update_time", 0)))

    best_enemy = enemies[0]
    target_pos = tuple(best_enemy.get("grid_pos", []))

    # 逆向BFS：从目标位置出发搜索到当前部队位置
    max_possible = GRID_ROWS * GRID_COLS
    dist, prev = _bfs_full_range(target_pos, unmovable_set, max_possible)

    if dist[start_pos[0]][start_pos[1]] != -1:
        # 可达：通过prev反向追溯，构建从当前到目标的路径（不含起点）
        bfs_dist = dist[start_pos[0]][start_pos[1]]
        path = []
        cur = start_pos
        while cur != target_pos:
            cur = prev[cur[0]][cur[1]]
            if cur is None:
                path = None
                break
            path.append(cur)
        if path is None:
            path = []
        return target_pos, path, bfs_dist, best_enemy

    # 不可达：退回到策略A（最近目标）
    return _find_nearest_target_with_expanding_bfs(current_troop, all_troops, unmovable_set, move_range, user_nation_cache)


def find_best_target_with_path(current_troop, all_troops, unmovable_set, user_nation_cache, target_type="nearest"):
    """
    战斗目标选择与路径计算入口。
    根据目标类型分流到两种不同策略：

    策略A（nearest-最近）：逐层扩展BFS，找到第一个敌军即停。BFS在每支部队行动时实时执行，
    确保"最近"基于当前战场状态。支持随机攻击位（由调用方通过_get_flanking_positions实现）。

    策略B（highest_attack/lowest_attack/most_food/most_troops/fewest_troops）：
    遍历排序选最优目标，逆向BFS判可达。不可达时退回到策略A。每支部队最多2次BFS。

    返回值：(target_pos, bfs_path, bfs_dist, target_troop)
    - target_pos: 目标格子坐标 (r, c)
    - bfs_path: 从当前到目标的路径（不含起点），用于移动
    - bfs_dist: BFS距离
    - target_troop: 目标部队对象
    若找不到目标，全部返回None。
    """
    start_pos = current_troop.get("grid_pos")
    if not start_pos:
        return None, None, None, None
    start_pos = tuple(start_pos)

    move_range = get_troop_move_range(current_troop)

    if target_type == "nearest":
        return _find_nearest_target_with_expanding_bfs(current_troop, all_troops, unmovable_set, move_range, user_nation_cache)
    else:
        return _find_target_by_criteria_with_reverse_bfs(current_troop, all_troops, unmovable_set, move_range, target_type, user_nation_cache)


def _get_flanking_positions(current_pos, target_troop, attack_range, dist_map, move_range,
                            unmovable_set, enemy_positions):
    """
    获取目标周围可攻击的"包围位置"。
    遍历目标周围attack_range范围内的所有格子，筛选出：
    1. 在地图内且不在不可通行集合中
    2. 没有被其他敌军占据（除非是当前部队自己的位置）
    3. 从当前位置可达（dist_map中距离不为-1）且在移动力范围内
    返回所有候选位置列表，调用方随机选择一个实现"随机攻击位"效果。
    """
    target_pos = tuple(target_troop.get("grid_pos", []))
    candidates = []
    for dr in range(-attack_range, attack_range + 1):
        for dc in range(-attack_range, attack_range + 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = target_pos[0] + dr, target_pos[1] + dc
            if not is_valid_cell(nr, nc):
                continue
            if abs(dr) + abs(dc) > attack_range:
                continue
            if (nr, nc) in unmovable_set:
                continue
            if (nr, nc) in enemy_positions and (nr, nc) != current_pos:
                continue
            d = dist_map[nr][nc]
            if d == -1 or d > move_range:
                continue
            candidates.append((nr, nc))
    return candidates


def execute_flanking_movement(current, sim, target_troop, attack_range, move_range,
                               steps_left, unmovable_set, sim_troops, user_nation_cache):
    """
    执行包围移动：在目标周围随机选择一个可达的攻击位，并移动到该位置。

    核心设计：
    1. BFS使用包含敌军位置的unmovable_set，确保路径不会穿过敌军。
       如果BFS穿过敌军（如目标部队），重建的路径在执行时会被enemy_positions_set拦截，
       导致包围移动失败。
    2. BFS范围使用move_range（总移动力）确保能发现绕路路径，
       但候选位筛选使用steps_left（剩余步数），避免选到实际走不到的包围位。

    返回：(new_current, flanking_path, new_steps_left)
    - new_current: 移动后的最终位置
    - flanking_path: 包围移动的路径点列表（不含起点），若未移动则为空列表
    - new_steps_left: 移动后的剩余步数
    """
    enemy_positions_set = {
        tuple(t.get("grid_pos", [])) for t in sim_troops.values()
        if is_enemy(sim, t, user_nation_cache) and is_troop_alive(t) and t.get("grid_pos")
    }
    # 包围BFS的关键：将敌军位置加入不可通行集合，避免路径穿过敌军
    flanking_unmovable = unmovable_set | enemy_positions_set
    dist_map, prev_map = _bfs_full_range(current, flanking_unmovable, move_range)
    flanking = _get_flanking_positions(
        current, target_troop, attack_range, dist_map, steps_left,
        unmovable_set, enemy_positions_set
    )

    flanking_path = []
    new_current = current
    new_steps_left = steps_left

    if not flanking:
        return new_current, flanking_path, new_steps_left

    chosen = random.choice(flanking)
    if chosen == current:
        return new_current, flanking_path, new_steps_left

    chosen_path = _reconstruct_path(current, chosen, prev_map)
    if not chosen_path:
        return new_current, flanking_path, new_steps_left

    for step in chosen_path:
        enemy_positions_set_updated = {
            tuple(t.get("grid_pos", [])) for t in sim_troops.values()
            if is_enemy(sim, t, user_nation_cache) and is_troop_alive(t) and t.get("grid_pos")
        }
        if step in enemy_positions_set_updated and step != new_current:
            break
        new_current = step
        flanking_path.append(new_current)
        sim["grid_pos"] = list(new_current)
        new_steps_left -= 1
        if new_steps_left <= 0:
            break

    return new_current, flanking_path, new_steps_left


def _find_fallback_target(current_troop, all_troops, attack_range, dist_map, target_type, user_nation_cache):
    """
    保底攻击目标选择：移动完成后，若原目标不在攻击范围内，在攻击范围内寻找可攻击的敌军。
    与_select_target_by_type逻辑相同，但筛选范围是attack_range（攻击范围）而非移动范围。
    用于确保部队移动后即使原目标不可达，也能攻击周围的敌军。
    """
    enemies = []
    for t in all_troops:
        if not is_enemy(current_troop, t, user_nation_cache):
            continue
        if not is_troop_alive(t):
            continue
        pos = t.get("grid_pos")
        if not pos:
            continue
        pos = tuple(pos)
        d = dist_map[pos[0]][pos[1]]
        if d == -1 or d > attack_range:
            continue
        enemies.append((t, d))

    if not enemies:
        return None

    if target_type == "highest_attack":
        enemies.sort(key=lambda x: (-_get_troop_first_slot_attack(x[0], skip_zero=True), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "lowest_attack":
        enemies.sort(key=lambda x: (_get_troop_first_slot_attack(x[0]), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "most_food":
        enemies.sort(key=lambda x: (-x[0].get("food", 0), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "most_troops":
        enemies.sort(key=lambda x: (-_get_troop_total_soldiers(x[0]), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    elif target_type == "fewest_troops":
        enemies.sort(key=lambda x: (_get_troop_total_soldiers(x[0]), x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))
    else:
        enemies.sort(key=lambda x: (x[1],
                                     x[0].get("create_time", 0), x[0].get("update_time", 0)))

    return enemies[0][0]


def get_attack_range(troop):
    """
    获取部队的攻击范围（取所有攻击槽位中攻击范围的最小值）。
    只考虑攻击力>0的槽位（运输兵等非攻击兵种不参与计算）。
    """
    team = troop.get("team", [])
    min_range = None
    from data.troop_data import TROOP_DATA, TROOP_DATA_SPECIAL
    for slot in team:
        if not slot:
            continue
        name = slot.get("兵种名称", "")
        if not name:
            continue
        count = slot.get("数量", 0)
        if count <= 0:
            continue
        for t in TROOP_DATA:
            if t["兵种名称"] == name:
                atk = t.get("攻击力", 0)
                if atk <= 0:
                    break
                ar = t.get("战斗攻击范围", 1)
                if min_range is None or ar < min_range:
                    min_range = ar
                break
        else:
            for t in TROOP_DATA_SPECIAL:
                if t["兵种名称"] == name:
                    atk = t.get("攻击力", 0)
                    if atk <= 0:
                        break
                    ar = t.get("战斗攻击范围", 1)
                    if min_range is None or ar < min_range:
                        min_range = ar
                    break
    return min_range if min_range is not None else 1


def manhattan_distance(p1, p2):
    """曼哈顿距离（网格距离），用于战斗中的距离判断"""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def calculate_troop_initial_positions(troop_ids, gate_positions):
    """
    计算部队初始站位：将部队按顺序分配到城门位置，循环分配。
    如果城门位置为空，则默认放在中心(9,9)。
    """
    positions = {}
    gate_list = list(gate_positions)
    for i, tid in enumerate(troop_ids):
        if gate_list:
            positions[tid] = gate_list[i % len(gate_list)]
        else:
            positions[tid] = (9, 9)
    return positions


def count_sub_actions(atk):
    count = 0
    if atk.get("sk"):
        count += 1
    if atk.get("t") is not None:
        count += 1
    if atk.get("dk"):
        count += 1
    ct = atk.get("ct")
    if ct:
        count += len(ct)
    da = atk.get("da")
    if da:
        count += 1
        if da.get("sk"):
            count += 1
        if da.get("t") is not None:
            count += 1
        if da.get("dk"):
            count += 1
        da_ct = da.get("ct")
        if da_ct:
            count += len(da_ct)
    return count


def calculate_round_duration(troop_paths, attack_sequences=None):
    total_ms = 0
    tid_to_path = {str(k): v for k, v in troop_paths.items()}

    atk_seq = attack_sequences or {}
    tid_to_atk = {str(k): v for k, v in atk_seq.items()}

    for tid, path in tid_to_path.items():
        total_ms += WAIT_STEP_TIME_MS
        move_steps = max(0, len(path) - 1) if path else 0
        total_ms += move_steps * MOVE_STEP_TIME_MS
        total_ms += WAIT_STEP_TIME_MS

        troop_attacks = tid_to_atk.get(tid, {})
        if troop_attacks:
            total_ms += 3 * WAIT_STEP_TIME_MS
            total_ms += COMBAT_INITIAL_DELAY
            sub_actions = 0
            for target_atks in troop_attacks.values():
                for atk in target_atks:
                    sub_actions += count_sub_actions(atk)
            total_ms += sub_actions * COMBAT_ACTION_INTERVAL
            total_ms += COMBAT_FINAL_DELAY
            total_ms += WAIT_STEP_TIME_MS

    return total_ms


def calculate_troop_timing(ss):
    timing = []
    offset_ms = 0
    for entry in ss:
        path = entry.get("ph", [])
        atk_list = entry.get("atk") or []

        start_ms = offset_ms
        offset_ms += WAIT_STEP_TIME_MS
        move_steps = max(0, len(path) - 1) if path else 0
        offset_ms += move_steps * MOVE_STEP_TIME_MS
        offset_ms += WAIT_STEP_TIME_MS

        if atk_list:
            offset_ms += 3 * WAIT_STEP_TIME_MS
            offset_ms += COMBAT_INITIAL_DELAY
            sub_actions = 0
            for atk in atk_list:
                sub_actions += count_sub_actions(atk)
            offset_ms += sub_actions * COMBAT_ACTION_INTERVAL
            offset_ms += COMBAT_FINAL_DELAY
            offset_ms += WAIT_STEP_TIME_MS

        timing.append({"id": entry["id"], "s": start_ms, "e": offset_ms})

    return timing
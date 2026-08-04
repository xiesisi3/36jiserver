"""
民兵（义勇军/连弩）生成与清理模块

当城池发生战斗时，防御方会根据民心(popular_support)自动生成民兵部队：
- 义勇军：每1000民心 → 3支（每支500人，每槽100人），最多30支
- 连弩：超过10000民心后，每1000民心 → 2支（每支150人，每槽30人），无上限

民兵特性：
- user_id="0"（NPC），不记录个人击杀，但通过_nation字段标记所属国家
- 义勇军使用山贼武将ID -10002，连弩使用山贼武将ID -10005，享受城池防御/攻击/交通加成
- 战斗准备阶段生成并写入DB，战斗结束后全部删除
- 服务器恢复时不重新生成（仅补_nation字段）

设计原因：
- _nation字段用于解决user_id="0"与敌我判定冲突：民兵user_id="0"会被is_enemy判定为对所有玩家敌对，
  通过get_troop_owner优先读取_nation，使民兵获得正确的国家归属，从而识别友军和敌军
- create_time=1 使民兵在战斗排序中排在最前，进攻方优先攻击民兵
- 民兵不直接写入grid，由 _cleanup_town_grid 统一处理网格同步，避免重复写入
"""
import logging
from data.town_attr_data import (
    generate_militia_config,
    MILITIA_VOLUNTEER_GENERAL_ID,
    MILITIA_CROSSBOW_GENERAL_ID,
    MILITIA_DEFAULT_GRID_X,
    MILITIA_DEFAULT_GRID_Y,
)
from data.global_data import troop_cache, town_outer_grid_cache
from troop.troop_db import insert_troop, delete_troop
from towns.towns_outer.town_outer_grid_core import remove_troop_from_grid
from combat.combat_utils import recalc_troop_food

logger = logging.getLogger("36ji-server")


def _build_militia_team(troop_name, per_slot, slots):
    """
    构建民兵部队的team数组。
    每个槽位填充相同的兵种和人数，slot[5]为空（运输兵槽位）。
    """
    team = []
    for i in range(slots):
        team.append({"兵种名称": troop_name, "数量": per_slot})
    team.append(None)
    return team


async def generate_militia_troops(town_id, town):
    """
    根据城池民心值生成民兵部队，写入DB、cache。

    只在战斗准备阶段(enter_battle_preparation)调用一次。
    服务器恢复时不会调用此函数（民兵已在DB中或已消灭）。
    民兵不写入grid，由 _cleanup_town_grid 统一处理网格同步。

    Args:
        town_id: 城池ID
        town: 城池数据字典（towns_cache中的对象）

    Returns:
        list: 生成的民兵部队字典列表，已包含 troop_id 和 grid_pos
    """
    popular_support = town.get("popular_support", 0)
    if popular_support <= 0:
        return []

    configs = generate_militia_config(popular_support)
    if not configs:
        return []

    nation_id = town.get("owner", 0)
    if not nation_id:
        logger.warning(f"民兵生成: 城池{town_id}无归属国家，跳过")
        return []

    # 确保两个武将模板都存在
    from general.general_utils import get_general_info
    if not get_general_info(-MILITIA_VOLUNTEER_GENERAL_ID):
        logger.warning(f"民兵生成: 义勇军武将模板 {MILITIA_VOLUNTEER_GENERAL_ID} 不存在")
        return []
    if not get_general_info(-MILITIA_CROSSBOW_GENERAL_ID):
        logger.warning(f"民兵生成: 连弩武将模板 {MILITIA_CROSSBOW_GENERAL_ID} 不存在")
        return []

    # 兵种名称 → 武将ID 映射
    TROOP_TO_GENERAL = {
        "义勇军": MILITIA_VOLUNTEER_GENERAL_ID,
        "连弩": MILITIA_CROSSBOW_GENERAL_ID,
    }

    militia_troops = []

    for cfg in configs:
        troop_name = cfg["troop_name"]
        count = cfg["count"]
        per_slot = cfg["per_slot"]
        slots = cfg["slots"]

        for i in range(count):
            team = _build_militia_team(troop_name, per_slot, slots)

            # 构建部队数据，create_time/update_time=1 使民兵在战斗排序中排在最前
            # 设计原因：进攻方优先攻击民兵，民兵作为"肉盾"保护真正的玩家部队
            troop_dict = {
                "user_id": "0",
                "general_id": -TROOP_TO_GENERAL.get(troop_name, MILITIA_VOLUNTEER_GENERAL_ID),
                "team": team,
                "food": 0,
                "status": 1,
                "pos": town_id,
                "dest": None,
                "dep_time": 0,
                "arrive_time": 0,
                "grid_x": MILITIA_DEFAULT_GRID_X,
                "grid_y": MILITIA_DEFAULT_GRID_Y,
                "target_type": "nearest",
                "create_time": 1,
                "update_time": 1,
                # _nation: 标记民兵所属国家，用于get_troop_owner正确判断敌我
                # 这是解决user_id="0"与敌我判定冲突的关键字段
                "_nation": nation_id,
            }

            # 按兵种可携带粮食上限计算粮食，并设置为最大值
            # recalc_troop_food 只计算max_food并在超出时下调，不会自动填充
            # 民兵初始food=0，需要手动设置为上限值
            recalc_troop_food(troop_dict)
            troop_dict["food"] = troop_dict.get("max_food", 0)

            # 写入DB
            troop_id = await insert_troop(troop_dict)
            troop_dict["id"] = troop_id
            troop_dict["troop_id"] = troop_id
            troop_dict["grid_pos"] = [MILITIA_DEFAULT_GRID_X, MILITIA_DEFAULT_GRID_Y]

            # 写入内存缓存（grid由 _cleanup_town_grid 统一处理，避免重复写入）
            troop_cache[troop_id] = troop_dict

            militia_troops.append(troop_dict)

    volunteer_count = sum(1 for t in militia_troops if
                          any(s and s.get("兵种名称") == "义勇军" for s in t["team"] if s))
    crossbow_count = len(militia_troops) - volunteer_count
    logger.info(
        f"民兵生成: 城池{town_id} 民心={popular_support}，"
        f"义勇军{volunteer_count}支，连弩{crossbow_count}支，"
        f"国家={nation_id}"
    )

    return militia_troops


async def cleanup_militia_troops(town_id, battle_troops):
    """
    战斗结束后清理所有民兵部队（从DB、cache、grid中删除）。

    民兵是临时部队，无论战斗胜负，战斗结束后全部销毁。

    Args:
        town_id: 城池ID
        battle_troops: 战斗部队列表（_battle_troops）
    """
    militia_deleted = 0
    grid = town_outer_grid_cache.get(town_id)

    for troop in battle_troops:
        tid = troop.get("troop_id")
        general_id = troop.get("general_id")

        # 识别民兵: general_id == -10002 (义勇军) 或 -10005 (连弩)
        if general_id not in (-MILITIA_VOLUNTEER_GENERAL_ID, -MILITIA_CROSSBOW_GENERAL_ID):
            continue

        # 从DB删除
        if tid is not None:
            await delete_troop(tid)

        # 从cache删除
        if tid in troop_cache:
            del troop_cache[tid]

        # 从grid删除
        if grid is not None:
            grid_pos = troop.get("grid_pos")
            if grid_pos and len(grid_pos) == 2:
                gx, gy = grid_pos[0], grid_pos[1]
                if 0 <= gx < 19 and 0 <= gy < 19:
                    cell = grid[gx][gy]
                    if tid in cell:
                        cell.remove(tid)
                    await remove_troop_from_grid(town_id, tid, gx, gy)

        militia_deleted += 1

    if militia_deleted > 0:
        logger.info(f"民兵清理: 城池{town_id} 删除{militia_deleted}支民兵部队")
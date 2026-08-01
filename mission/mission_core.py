import json
import logging
from data.mission_data import MISSION_CONFIG, TREASURE_SET_MAP, TREASURE_SET_REFINED_MAP
from data.global_data import mission_cache, generals_cache, fief_cache, towns_cache, user_resource_cache, user_nation_cache
from data.hero_data import HEROES
from mission.mission_db import (
    get_all_missions,
    get_mission_by_user,
    insert_mission,
    update_mission_claimed,
    update_mission_combat_score,
)

logger = logging.getLogger('36ji-server')

FIXED_HERO_NAMES = {h["hero_name"] for h in HEROES}

_MISSION_TYPE_COLUMN_MAP = {
    "general_level": "general",
}


def _get_column_name(mission_type):
    base = _MISSION_TYPE_COLUMN_MAP.get(mission_type, mission_type)
    return f"{base}_claimed"


async def load_all_missions_to_cache():
    """服务端启动时，从数据库加载所有使命进度到内存"""
    rows = await get_all_missions()
    mission_cache.clear()
    for row in rows:
        data = dict(row)
        user_id = data["user_id"]
        data["general_claimed"] = json.loads(data.get("general_claimed") or "[]")
        data["hero_claimed"] = json.loads(data.get("hero_claimed") or "[]")
        data["fief_claimed"] = json.loads(data.get("fief_claimed") or "[]")
        data["combat_claimed"] = json.loads(data.get("combat_claimed") or "[]")
        data["city_claimed"] = json.loads(data.get("city_claimed") or "[]")
        data["development_claimed"] = json.loads(data.get("development_claimed") or "[]")
        mission_cache[user_id] = data
    logger.info(f"使命缓存加载完成，共 {len(mission_cache)} 条")


async def ensure_mission(user_id):
    """确保用户有使命进度记录，没有则创建"""
    if user_id in mission_cache:
        return
    existing = await get_mission_by_user(user_id)
    if existing:
        data = dict(existing)
        data["general_claimed"] = json.loads(data.get("general_claimed") or "[]")
        data["hero_claimed"] = json.loads(data.get("hero_claimed") or "[]")
        data["fief_claimed"] = json.loads(data.get("fief_claimed") or "[]")
        data["combat_claimed"] = json.loads(data.get("combat_claimed") or "[]")
        data["city_claimed"] = json.loads(data.get("city_claimed") or "[]")
        data["development_claimed"] = json.loads(data.get("development_claimed") or "[]")
        mission_cache[user_id] = data
    else:
        await insert_mission(user_id)
        mission_cache[user_id] = {
            "user_id": user_id,
            "combat_score": 0,
            "development_score": 0,
            "general_claimed": [],
            "hero_claimed": [],
            "fief_claimed": [],
            "combat_claimed": [],
            "city_claimed": [],
            "development_claimed": [],
        }


def _get_current_value(user_id, mission_type):
    """获取用户某使命类型的当前计数值"""
    if mission_type == "general_level":
        return _get_general_level(user_id)
    elif mission_type == "hero":
        return _get_hero_count(user_id)
    elif mission_type == "fief":
        return _get_fief_count(user_id)
    elif mission_type == "combat":
        return _get_combat_score(user_id)
    elif mission_type == "city":
        return _get_nation_city_count(user_id)
    elif mission_type == "development":
        return _get_development_score(user_id)
    return 0


def _get_general_level(user_id):
    """获取玩家同名武将的等级"""
    player_name = (user_resource_cache.get(user_id, {}) or {}).get("player_name", "")
    if not player_name:
        return 0
    user_generals = generals_cache.get(user_id, [])
    for g in user_generals:
        if g.get("hero_name") == player_name:
            return g.get("level", 1)
    return 0


def _get_hero_count(user_id):
    """获取玩家拥有的英雄武将数量"""
    user_generals = generals_cache.get(user_id, [])
    count = 0
    for g in user_generals:
        if g.get("hero_name") in FIXED_HERO_NAMES:
            count += 1
    return count


def _get_fief_count(user_id):
    """获取玩家封地数量"""
    count = 0
    for fief in fief_cache.values():
        if fief.get("user_id") == user_id:
            count += 1
    return count


def _get_combat_score(user_id):
    """获取累计战斗积分"""
    mission = mission_cache.get(user_id, {})
    return mission.get("combat_score", 0)


def _get_nation_city_count(user_id):
    """获取玩家所属国家的城池数量"""
    nation_id = user_nation_cache.get(user_id)
    if nation_id is None:
        return 0
    count = 0
    for town in towns_cache.values():
        if town.get("owner") == nation_id:
            count += 1
    return count


def _get_development_score(user_id):
    """获取累计发展分（暂未实装）"""
    mission = mission_cache.get(user_id, {})
    return mission.get("development_score", 0)


def get_mission_list(user_id):
    """获取所有使命的当前阶段摘要（只返回第一个未领取的阶段）
    :return: dict，每个使命类型包含 current_value、current_stage、threshold、rewards、can_claim
    """
    mission = mission_cache.get(user_id)
    if mission is None:
        return {}

    result = {}
    for mission_type, config in MISSION_CONFIG.items():
        current = _get_current_value(user_id, mission_type)
        claimed_list = mission.get(_get_column_name(mission_type), [])
        stages = config["stages"]
        all_stages = {s["stage"] for s in stages}
        if all_stages.issubset(set(claimed_list)):
            result[mission_type] = {
                "name": config["name"],
                "description": config["description"],
                "current_value": current,
                "completed": True,
            }
        else:
            for stage in stages:
                stage_num = stage["stage"]
                if stage_num not in claimed_list:
                    result[mission_type] = {
                        "name": config["name"],
                        "description": config["description"],
                        "current_value": current,
                        "current_stage": stage_num,
                        "threshold": stage["threshold"],
                        "rewards": stage["rewards"],
                        "can_claim": current >= stage["threshold"],
                    }
                    break
    return result


def get_mission_detail(user_id, mission_type):
    """获取单种使命类型的所有阶段详情（方便客户端查看目标）
    :param user_id: 用户ID
    :param mission_type: 使命类型
    :return: dict 或 None
    """
    config = MISSION_CONFIG.get(mission_type)
    if config is None:
        return None

    mission = mission_cache.get(user_id)
    if mission is None:
        return None

    current = _get_current_value(user_id, mission_type)
    claimed_list = mission.get(_get_column_name(mission_type), [])
    stages = []
    for stage in config["stages"]:
        stage_num = stage["stage"]
        stages.append({
            "stage": stage_num,
            "threshold": stage["threshold"],
            "claimed": stage_num in claimed_list,
            "rewards": stage["rewards"],
        })

    return {
        "mission_type": mission_type,
        "name": config["name"],
        "description": config["description"],
        "current_value": current,
        "stages": stages,
    }


async def claim_mission_reward(user_id, mission_type):
    """领取使命奖励（自动领取第一个未领取的阶段）
    :param user_id: 用户ID
    :param mission_type: 使命类型
    :return: (success: bool, result: str|dict)
    """
    config = MISSION_CONFIG.get(mission_type)
    if config is None:
        return False, f"无效的使命类型: {mission_type}"

    mission = mission_cache.get(user_id)
    if mission is None:
        return False, "使命进度数据不存在"

    claimed_list = mission.get(_get_column_name(mission_type), [])
    all_stages = {s["stage"] for s in config["stages"]}
    if all_stages.issubset(set(claimed_list)):
        return False, "所有阶段奖励已领取完毕"

    target_stage = None
    stage_config = None
    for s in config["stages"]:
        stage_num = s["stage"]
        if stage_num not in claimed_list:
            target_stage = stage_num
            stage_config = s
            break

    if target_stage is None or stage_config is None:
        return False, "未找到可领取的阶段"

    current = _get_current_value(user_id, mission_type)
    if current < stage_config["threshold"]:
        return False, f"未达到条件，需要 {stage_config['threshold']}，当前 {current}"

    granted = await _grant_rewards(user_id, mission_type, stage_config["rewards"])
    if granted is None:
        return False, "奖励发放失败"

    claimed_list.append(target_stage)
    claimed_json = json.dumps(claimed_list)
    await update_mission_claimed(user_id, _get_column_name(mission_type), claimed_json)
    mission[_get_column_name(mission_type)] = claimed_list

    return True, {
        "mission_type": mission_type,
        "stage": target_stage,
        "rewards": stage_config["rewards"],
        "granted": granted,
    }


async def _grant_rewards(user_id, mission_type, rewards):
    """发放奖励
    :return: 发放结果列表，失败返回 None
    """
    from items.item_core import add_item_to_user
    from treasure.treasure_core import _build_treasure_dict
    from treasure.treasure_db import insert_treasure as insert_treasure_db
    from user_resource.user_resource_db import update_user_resource_field
    from data.treasure_data import TREASURES
    from data.global_data import treasure_cache

    granted = []
    for reward in rewards:
        reward_type = reward["type"]

        if reward_type == "item":
            item_name = reward["item_name"]
            quantity = reward.get("quantity", 1)
            result = await add_item_to_user(user_id, item_name, quantity)
            if "error" in result:
                logger.error(f"使命奖励发放失败: user_id={user_id}, item={item_name}, error={result['error']}")
                return None
            granted.append({
                "type": "item",
                "item_id": result["item_id"],
                "item_name": result["item_name"],
                "item_category": result["item_category"],
                "icon_path": result["icon_path"],
                "subcategory": result["subcategory"],
                "condition": result["condition"],
                "quantity": quantity,
            })

        elif reward_type == "treasure":
            treasure_name = reward["treasure_name"]
            template = None
            for t in TREASURES:
                if t["name"] == treasure_name:
                    template = t
                    break
            if template is None:
                logger.error(f"使命奖励宝物模板不存在: {treasure_name}")
                return None
            data = _build_treasure_dict(template, user_id)
            treasure_id = await insert_treasure_db(data)
            data["id"] = treasure_id
            treasure_cache[treasure_id] = data
            granted.append(dict(data))

        elif reward_type == "treasure_set":
            level = reward["level"]
            refined = reward.get("refined", False)
            if refined:
                names = TREASURE_SET_REFINED_MAP.get(level, [])
            else:
                names = TREASURE_SET_MAP.get(level, [])
            if not names:
                logger.error(f"使命奖励宝物套装不存在: level={level}, refined={refined}")
                return None
            for treasure_name in names:
                template = None
                for t in TREASURES:
                    if t["name"] == treasure_name:
                        template = t
                        break
                if template is None:
                    logger.error(f"使命奖励宝物模板不存在: {treasure_name}")
                    return None
                data = _build_treasure_dict(template, user_id)
                treasure_id = await insert_treasure_db(data)
                data["id"] = treasure_id
                treasure_cache[treasure_id] = data
                granted.append(dict(data))

        elif reward_type == "gold":
            quantity = reward.get("quantity", 0)
            current_gold = user_resource_cache.get(user_id, {}).get("gold", 0)
            new_gold = current_gold + quantity
            await update_user_resource_field(user_id, "gold", new_gold)
            if user_id in user_resource_cache:
                user_resource_cache[user_id]["gold"] = new_gold
            granted.append({
                "type": "gold",
                "quantity": quantity,
                "new_gold": new_gold,
            })

        elif reward_type == "special":
            if not reward.get("implemented", False):
                logger.error(f"使命特殊奖励暂未实装: {reward.get('special_name', '')}")
                return None
            granted.append({
                "type": "special",
                "special_name": reward.get("special_name", ""),
            })

    return granted


async def add_combat_score(user_id, score):
    """累加战斗积分（只增不减）"""
    if score <= 0:
        return
    mission = mission_cache.get(user_id)
    if mission is None:
        await ensure_mission(user_id)
        mission = mission_cache.get(user_id)
    if mission is None:
        return
    new_score = mission.get("combat_score", 0) + score
    mission["combat_score"] = new_score
    await update_mission_combat_score(user_id, new_score)


async def add_development_score(user_id, score):
    """累加发展分（只增不减）"""
    if score <= 0:
        return
    mission = mission_cache.get(user_id)
    if mission is None:
        await ensure_mission(user_id)
        mission = mission_cache.get(user_id)
    if mission is None:
        return
    new_score = mission.get("development_score", 0) + score
    mission["development_score"] = new_score
    from mission.mission_db import update_mission_development_score
    await update_mission_development_score(user_id, new_score)
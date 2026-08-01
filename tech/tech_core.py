import logging
from data.tech_data import TECH_CONFIG, TECH_TYPES, get_tech_cost, SERIES_TO_ATTACK_TECH, SERIES_TO_COMBO_TECH
from data.global_data import tech_cache, user_resource_cache
from tech.tech_db import get_all_techs, get_tech_by_user, upsert_tech

logger = logging.getLogger('36ji-server')


async def load_all_techs_to_cache():
    """服务端启动时，从数据库加载所有科技进度到内存"""
    rows = await get_all_techs()
    tech_cache.clear()
    for row in rows:
        user_id = row["user_id"]
        if user_id not in tech_cache:
            tech_cache[user_id] = {}
        tech_cache[user_id][row["tech_type"]] = row["level"]
    logger.info(f"科技缓存加载完成，共 {len(tech_cache)} 个用户")


async def ensure_tech(user_id):
    """确保用户有科技进度记录，没有则初始化（全部0级）"""
    if user_id in tech_cache:
        return
    rows = await get_tech_by_user(user_id)
    if rows:
        tech_cache[user_id] = {}
        for row in rows:
            tech_cache[user_id][row["tech_type"]] = row["level"]
    else:
        tech_cache[user_id] = {t: 0 for t in TECH_TYPES}


def get_tech_level(user_id, tech_type):
    """获取用户某科技的当前等级，未初始化返回0"""
    cache = tech_cache.get(user_id, {})
    return cache.get(tech_type, 0)


def get_tech_list(user_id):
    """获取用户所有科技的当前状态列表"""
    result = []
    for tech_type in TECH_TYPES:
        config = TECH_CONFIG[tech_type]
        current_level = get_tech_level(user_id, tech_type)
        next_level = current_level + 1
        max_level = config["max_level"]
        if next_level > max_level:
            next_cost = 0
            effect = f"{config['effect_desc']}（已满级）"
        else:
            next_cost = get_tech_cost(tech_type, next_level)
            effect = _get_effect_desc(tech_type, current_level)
        result.append({
            "type": tech_type,
            "current_level": current_level,
            "max_level": max_level,
            "next_level": next_level,
            "next_cost": next_cost,
            "effect": effect,
            "not_implemented": config.get("not_implemented", False),
        })
    return result


def get_tech_detail(user_id, tech_type):
    """获取某种科技的所有等级详情"""
    config = TECH_CONFIG.get(tech_type)
    if not config:
        return None
    current_level = get_tech_level(user_id, tech_type)
    levels = []
    for lv in range(1, config["max_level"] + 1):
        cost = get_tech_cost(tech_type, lv)
        unlocked = lv <= current_level
        effect = _get_level_effect_desc(tech_type, lv)
        levels.append({
            "level": lv,
            "cost": cost,
            "unlocked": unlocked,
            "effect": effect,
        })
    return {
        "type": tech_type,
        "max_level": config["max_level"],
        "current_level": current_level,
        "effect_desc": config["effect_desc"],
        "not_implemented": config.get("not_implemented", False),
        "levels": levels,
    }


async def unlock_tech(user_id, tech_type):
    """解锁科技下一级，扣除铜币，更新缓存和数据库"""
    config = TECH_CONFIG.get(tech_type)
    if not config:
        return False, "无效的科技类型"

    current_level = get_tech_level(user_id, tech_type)
    next_level = current_level + 1

    if next_level > config["max_level"]:
        return False, f"{tech_type}已满级({config['max_level']}级)"

    if config.get("not_implemented"):
        return False, f"{tech_type}暂未实装"

    cost = get_tech_cost(tech_type, next_level)

    resource = user_resource_cache.get(user_id)
    if not resource:
        return False, "用户资源不存在"

    if resource.get("copper", 0) < cost:
        return False, f"铜币不足，需要{cost}，当前{resource.get('copper', 0)}"

    new_copper = resource["copper"] - cost
    resource["copper"] = new_copper
    from user_resource.user_resource_db import update_user_resource_field
    await update_user_resource_field(user_id, "copper", new_copper)

    tech_cache[user_id][tech_type] = next_level
    await upsert_tech(user_id, tech_type, next_level)

    logger.info(f"用户 {user_id} 解锁 {tech_type} 第{next_level}级，消耗铜币{cost}")

    return True, {
        "type": tech_type,
        "new_level": next_level,
        "cost": cost,
        "copper_remaining": new_copper,
    }


def get_general_limit(user_id):
    """计算武将数量上限（世卿世禄）"""
    level = get_tech_level(user_id, "世卿世禄")
    config = TECH_CONFIG["世卿世禄"]
    return config["base_limit"] + level * config["limit_per_level"]


def get_fief_limit(user_id):
    """计算封地数量上限（列土封疆）"""
    level = get_tech_level(user_id, "列土封疆")
    config = TECH_CONFIG["列土封疆"]
    return config["base_limit"] + level * config["limit_per_level"]


def get_attack_bonus(user_id, troop_series):
    """获取兵种系列的科技攻击力加成系数"""
    tech_type = SERIES_TO_ATTACK_TECH.get(troop_series)
    if not tech_type:
        return 1.0
    level = get_tech_level(user_id, tech_type)
    config = TECH_CONFIG[tech_type]
    return 1.0 + level * config["bonus_per_level"]


def get_combo_bonus(user_id, troop_series):
    """获取兵种系列的科技连击率加成"""
    tech_type = SERIES_TO_COMBO_TECH.get(troop_series)
    if not tech_type:
        return 0.0
    level = get_tech_level(user_id, tech_type)
    config = TECH_CONFIG[tech_type]
    return level * config["bonus_per_level"]


def _get_effect_desc(tech_type, current_level):
    """获取科技当前效果描述"""
    config = TECH_CONFIG[tech_type]
    if config.get("not_implemented"):
        return f"{config['effect_desc']}（暂未实装）"
    if config["category"] == "limit":
        base = config["base_limit"]
        per = config["limit_per_level"]
        return f"{config['effect_desc']}{base + current_level * per}→{base + (current_level + 1) * per}"
    elif config["category"] == "battle":
        bonus = config["bonus_per_level"]
        return f"{config['effect_desc']}（当前+{int(bonus * 100 * current_level)}%，下一级+{int(bonus * 100 * (current_level + 1))}%）"
    return config["effect_desc"]


def _get_level_effect_desc(tech_type, level):
    """获取科技指定等级的效果描述"""
    config = TECH_CONFIG[tech_type]
    if config.get("not_implemented"):
        return f"{config['effect_desc']}（暂未实装）"
    if config["category"] == "limit":
        base = config["base_limit"]
        per = config["limit_per_level"]
        return f"{config['effect_desc']}{base + (level - 1) * per}→{base + level * per}"
    elif config["category"] == "battle":
        bonus = config["bonus_per_level"]
        return f"{config['effect_desc']}（当前+{int(bonus * 100 * level)}%）"
    return config["effect_desc"]
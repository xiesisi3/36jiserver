import logging
import random

from data.item_data import ITEM_INDEX
from data.hero_data import HEROES
from data.global_data import items_cache, user_resource_cache, generals_cache
from items.item_db import (
    insert_item,
    get_item_by_id,
    get_items_by_user,
    get_item_by_user_and_name,
    update_item_quantity,
    delete_item,
    get_all_items,
)
from user_resource.user_resource_db import update_user_resource_field
from general.general_db import update_general
from general.general_core import add_exp, sync_cache_update as sync_general_cache_update

logger = logging.getLogger('36ji-server')

_FIXED_HERO_NAMES = {h["hero_name"] for h in HEROES}


async def load_all_items_to_cache():
    items = await get_all_items()
    for item in items:
        items_cache[item["id"]] = item
    logger.info(f"道具缓存加载完成，共 {len(items)} 条记录")


async def add_item_to_user(user_id, item_name, quantity=1):
    """给用户添加道具，同名堆叠
    :return: {"item_id": int, "item_name": str, "item_category": str, "quantity": int,
               "icon_path": str, "subcategory": str, "condition": list|None, "is_new": bool}
    """
    template = ITEM_INDEX.get(item_name)
    if template is None:
        logger.warning(f"道具模板不存在: {item_name}")
        return {"error": f"道具模板不存在: {item_name}"}

    item_category = template["category"]
    icon_path = template.get("icon_path", "")
    subcategory = template.get("subcategory", "")
    condition = template.get("condition") if item_category == "general" else None

    existing = await get_item_by_user_and_name(user_id, item_name)
    if existing:
        new_quantity = existing["quantity"] + quantity
        await update_item_quantity(existing["id"], new_quantity)
        existing["quantity"] = new_quantity
        items_cache[existing["id"]] = existing
        return {
            "item_id": existing["id"],
            "item_name": item_name,
            "item_category": item_category,
            "icon_path": icon_path,
            "subcategory": subcategory,
            "condition": condition,
            "quantity": new_quantity,
            "is_new": False,
        }
    else:
        data = {
            "user_id": user_id,
            "item_name": item_name,
            "item_category": item_category,
            "quantity": quantity,
        }
        item_id = await insert_item(data)
        data["id"] = item_id
        items_cache[item_id] = data
        return {
            "item_id": item_id,
            "item_name": item_name,
            "item_category": item_category,
            "icon_path": icon_path,
            "subcategory": subcategory,
            "condition": condition,
            "quantity": quantity,
            "is_new": True,
        }


def get_user_items_from_cache(user_id):
    """从缓存中获取用户所有道具，附带模板信息"""
    items = []
    for item in items_cache.values():
        if item["user_id"] == user_id:
            entry = {
                "id": item["id"],
                "item_name": item["item_name"],
                "item_category": item["item_category"],
                "quantity": item["quantity"],
            }
            template = ITEM_INDEX.get(item["item_name"])
            if template:
                entry["icon_path"] = template.get("icon_path", "")
                entry["subcategory"] = template.get("subcategory", "")
                if template.get("category") == "general":
                    entry["condition"] = template.get("condition")
            items.append(entry)
    return items


async def _consume_items(item_id, count=1):
    """消耗道具，数量-count，归零时删除"""
    item = items_cache.get(item_id)
    if not item:
        return None

    new_quantity = item["quantity"] - count
    if new_quantity <= 0:
        await delete_item(item_id)
        del items_cache[item_id]
        return None
    else:
        await update_item_quantity(item_id, new_quantity)
        item["quantity"] = new_quantity
        return item


def _check_general_condition(general, condition):
    """校验武将使用条件
    :param general: 武将数据字典
    :param condition: 条件列表（如 ["alive", "not_fighting", "not_hero"]），None 表示无条件
    :return: (True, "") 或 (False, "错误信息")
    """
    if condition is None:
        return True, ""

    status = general.get("status", 1)
    for cond in condition:
        if cond == "alive" and status == 4:
            return False, "武将已阵亡，无法使用"
        if cond == "not_fighting" and status == 3:
            return False, "武将正在战斗中，无法使用"
        if cond == "not_hero" and general.get("hero_name") in _FIXED_HERO_NAMES:
            return False, "英雄武将无法使用该道具"
    return True, ""


def _get_general_by_id(user_id, general_id):
    """从缓存中查找指定武将"""
    for g in generals_cache.get(user_id, []):
        if g["id"] == general_id:
            return g
    return None


async def _use_chest(user_id, item_id, item, template, quantity=1):
    """使用宝箱类道具，支持批量"""
    copper_min, copper_max = template["copper"]
    total_copper = 0
    all_treasure_drops = []
    item_drop_counts = {}

    for _ in range(quantity):
        total_copper += random.randint(copper_min, copper_max)
        for drop in template.get("drops", []):
            if random.random() < drop["rate"]:
                if drop["type"] == "treasure":
                    all_treasure_drops.append(drop["level"])
                elif drop["type"] == "item":
                    name = drop["name"]
                    item_drop_counts[name] = item_drop_counts.get(name, 0) + 1

    res = user_resource_cache.get(user_id)
    if not res:
        return False, "用户资源不存在"

    res["copper"] = res.get("copper", 0) + total_copper
    await update_user_resource_field(user_id, "copper", res["copper"])

    drop_results = []
    for level in all_treasure_drops:
        treasure_result = await _drop_treasure(user_id, level)
        if treasure_result:
            drop_results.append(treasure_result)

    for item_name, count in item_drop_counts.items():
        item_result = await add_item_to_user(user_id, item_name, count)
        if "error" not in item_result:
            drop_results.append({
                "type": "item",
                "item_id": item_result["item_id"],
                "item_name": item_result["item_name"],
                "item_category": item_result["item_category"],
                "icon_path": item_result["icon_path"],
                "subcategory": item_result["subcategory"],
                "condition": item_result["condition"],
                "quantity": count,
            })

    await _consume_items(item_id, quantity)

    return True, {
        "item_id": item_id,
        "item_name": template["name"],
        "quantity_used": quantity,
        "copper_gained": total_copper,
        "drops": drop_results,
    }


async def _drop_treasure(user_id, level):
    """从指定等级宝物池中随机掉落一件宝物"""
    from data.treasure_data import TREASURES
    candidates = [t for t in TREASURES if t["level"] == level]
    if not candidates:
        logger.warning(f"宝物等级 {level} 无可用模板")
        return None

    template = random.choice(candidates)
    from treasure.treasure_core import _build_treasure_dict
    from treasure.treasure_db import insert_treasure as insert_treasure_db
    from data.global_data import treasure_cache

    data = _build_treasure_dict(template, user_id)
    treasure_id = await insert_treasure_db(data)
    data["id"] = treasure_id
    treasure_cache[treasure_id] = data

    return dict(data)


async def _use_player_resource(user_id, item_id, item, template, quantity=1):
    """使用玩家类-资源型道具，支持批量"""
    effects = template.get("effects", {})
    if not effects:
        return False, "道具效果配置为空"

    res = user_resource_cache.get(user_id)
    if not res:
        return False, "用户资源不存在"

    resources_gained = {}
    for _ in range(quantity):
        for field, value in effects.items():
            if isinstance(value, list):
                amount = random.randint(value[0], value[1])
            else:
                amount = value
            if amount > 0:
                resources_gained[field] = resources_gained.get(field, 0) + amount

    for field, amount in resources_gained.items():
        res[field] = res.get(field, 0) + amount
        await update_user_resource_field(user_id, field, res[field])

    await _consume_items(item_id, quantity)

    return True, {
        "item_id": item_id,
        "item_name": template["name"],
        "quantity_used": quantity,
        "resources_gained": resources_gained,
    }


async def _use_skill_book(user_id, item_id, item, template, general_id, quantity=1):
    """使用技能书，让目标武将学会技能，不支持批量"""
    if quantity > 1:
        return False, "技能书不支持批量使用，请逐个使用"

    general = _get_general_by_id(user_id, general_id)
    if general is None:
        return False, "武将不存在"

    ok, err = _check_general_condition(general, template.get("condition"))
    if not ok:
        return False, err

    skill_name = template["skill_name"]
    skill_desc = ""
    for hero in HEROES:
        if hero["skill_name"] == skill_name:
            skill_desc = hero.get("skill_desc", "")
            break

    updates = {
        "skill_name": skill_name,
        "skill_desc": skill_desc,
    }
    general["skill_name"] = skill_name
    general["skill_desc"] = skill_desc
    await update_general(general_id, updates)
    sync_general_cache_update(general_id, updates)

    await _consume_items(item_id)

    return True, {
        "item_id": item_id,
        "item_name": template["name"],
        "general_id": general_id,
        "skill_name": skill_name,
        "skill_desc": skill_desc,
    }


async def _use_random_skill_book(user_id, item_id, item, template, quantity=1):
    """使用随机技能书，获得随机技能书道具，支持批量"""
    skill_pool = template.get("skill_pool", [])
    if not skill_pool:
        return False, "技能池为空"

    skill_counts = {}
    for _ in range(quantity):
        skill_name = random.choice(skill_pool)
        skill_counts[skill_name] = skill_counts.get(skill_name, 0) + 1

    obtained_skill_books = []
    for skill_name, count in skill_counts.items():
        result = await add_item_to_user(user_id, skill_name, count)
        if "error" in result:
            return False, result["error"]
        obtained_skill_books.append({
            "item_id": result["item_id"],
            "item_name": result["item_name"],
            "item_category": result["item_category"],
            "icon_path": result["icon_path"],
            "subcategory": result["subcategory"],
            "condition": result["condition"],
            "quantity": count,
        })

    await _consume_items(item_id, quantity)

    return True, {
        "item_id": item_id,
        "item_name": template["name"],
        "quantity_used": quantity,
        "obtained_skill_books": obtained_skill_books,
    }


async def _use_exp_book(user_id, item_id, item, template, general_id, quantity=1):
    """使用经验书，给目标武将增加经验，支持批量"""
    general = _get_general_by_id(user_id, general_id)
    if general is None:
        return False, "武将不存在"

    ok, err = _check_general_condition(general, template.get("condition"))
    if not ok:
        return False, err

    total_exp = template["exp"] * quantity
    result = add_exp(general, total_exp, use_wisdom=False)
    await update_general(general_id, result["updates"])
    sync_general_cache_update(general_id, result["updates"])

    await _consume_items(item_id, quantity)

    return True, {
        "item_id": item_id,
        "item_name": template["name"],
        "quantity_used": quantity,
        "general_id": general_id,
        "total_exp": total_exp,
        "leveled_up": result["leveled_up"],
        "new_level": result["new_level"],
        "new_exp": result["new_exp"],
        "levels_gained": result["levels_gained"],
        "skill_points": general.get("skill_points", 0),
    }


async def use_item(user_id, item_id, general_id=None, quantity=1):
    """使用道具，根据类别分发到对应处理函数
    :param user_id: 用户ID
    :param item_id: 道具ID
    :param general_id: 目标武将ID（skill_book/exp 类型必填）
    :param quantity: 使用数量，默认1
    :return: (success: bool, result: str|dict)
    """
    item = items_cache.get(item_id)
    if not item:
        return False, "道具不存在"

    if item["user_id"] != user_id:
        return False, "道具不属于该用户"

    if not isinstance(quantity, int) or quantity <= 0:
        return False, "使用数量必须为正整数"

    if quantity > item["quantity"]:
        return False, f"道具数量不足，需要 {quantity}，当前 {item['quantity']}"

    template = ITEM_INDEX.get(item["item_name"])
    if template is None:
        return False, f"道具模板不存在: {item['item_name']}"

    category = template["category"]

    if category == "chest":
        return await _use_chest(user_id, item_id, item, template, quantity)

    elif category == "player":
        subcategory = template.get("subcategory", "")
        if subcategory == "material":
            return False, f"{template['name']}是强化材料，无法直接使用，请在宝物强化中使用"
        elif subcategory == "resource":
            return await _use_player_resource(user_id, item_id, item, template, quantity)
        else:
            return False, f"未知的玩家道具子类型: {subcategory}"

    elif category == "general":
        subcategory = template.get("subcategory", "")

        if subcategory == "random_skill":
            return await _use_random_skill_book(user_id, item_id, item, template, quantity)

        if not general_id:
            return False, "请指定目标武将ID"

        if subcategory == "skill_book":
            return await _use_skill_book(user_id, item_id, item, template, general_id, quantity)
        elif subcategory == "exp":
            return await _use_exp_book(user_id, item_id, item, template, general_id, quantity)
        elif subcategory == "buff":
            return False, "武将加成类道具暂未实装"
        elif subcategory == "reset":
            return False, "武将重置类道具暂未实装"
        else:
            return False, f"未知的武将道具子类型: {subcategory}"

    else:
        return False, f"未知的道具类别: {category}"


async def grant_initial_items(user_id):
    items_to_grant = [
        ("官府货票", 3),
        ("私人货票", 6),
        ("普通货票", 3),
        ("实木宝箱", 5),
        ("青铜宝箱", 3),
    ]
    for item_name, qty in items_to_grant:
        await add_item_to_user(user_id, item_name, qty)
    logger.info(f"玩家 {user_id} 初始道具赠送完成")
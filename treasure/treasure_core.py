import logging
import random
import datetime

from core.database import get_pool
from data.treasure_data import TREASURES
from data.global_data import treasure_cache, generals_cache, troop_cache, treasure_enhance_daily, user_resource_cache
from treasure.treasure_db import (
    insert_treasure,
    get_treasures_by_user,
    get_all_treasures,
    update_treasure,
    delete_treasure,
)
from general.general_db import update_general
from general.general_core import sync_cache_update as sync_general_cache_update
from user_resource.user_resource_db import update_user_resource_field, update_user_resource
from troop.troop_utils import get_general_max_troop_count, calculate_total_troops

logger = logging.getLogger('36ji-server')

INITIAL_TREASURE_NAMES = [
    "桃木剑",
    "兵法心要",
    "衡论",
    "练兵实记",
    "青铜剑",
    "黑石扳指",
    "护身符",
    "开国校尉剑",
    "和氏璧",
]

TREASURE_TEMPLATE_MAP = {t["name"]: t for t in TREASURES}

ATTR_FIELD_MAP = {
    "force": "force",
    "intelligence": "intelligence",
    "charisma": "charisma",
    "infantry": "infantry_phase",
    "cavalry": "cavalry_phase",
    "archer": "archer_phase",
    "governance": "governance_phase",
    "wisdom": "wisdom",
    "combo_rate": "combo_rate",
}


def _build_icon_path(treasure_name):
    return f"resources/img/treasure/{treasure_name}.png"


def _build_treasure_dict(template, user_id):
    return {
        "user_id": user_id,
        "treasure_name": template["name"],
        "treasure_type": template["type"],
        "level": template["level"],
        "enhance": template.get("enhance", 0),
        "force": template.get("force", 0),
        "intelligence": template.get("intelligence", 0),
        "charisma": template.get("charisma", 0),
        "infantry": template.get("infantry", 0),
        "cavalry": template.get("cavalry", 0),
        "archer": template.get("archer", 0),
        "governance": template.get("governance", 0),
        "wisdom": template.get("wisdom", 0),
        "star_level": 0,
        "star_force": 0,
        "star_intelligence": 0,
        "star_charisma": 0,
        "star_wisdom": 0,
        "star_infantry": 0,
        "star_cavalry": 0,
        "star_archer": 0,
        "star_governance": 0,
        "combo_rate": template.get("combo_rate", 0.0),
        "exclusive": template.get("exclusive", ""),
        "icon_path": _build_icon_path(template["name"]),
        "is_equipped": 0,
        "general_id": None,
    }


async def grant_initial_treasures(user_id):
    treasure_ids = []
    for name in INITIAL_TREASURE_NAMES:
        template = TREASURE_TEMPLATE_MAP.get(name)
        if template is None:
            logger.warning(f"宝物模板不存在: {name}")
            continue
        data = _build_treasure_dict(template, user_id)
        treasure_id = await insert_treasure(data)
        data["id"] = treasure_id
        treasure_cache[treasure_id] = data
        treasure_ids.append(treasure_id)
    logger.info(f"玩家 {user_id} 初始宝物赠送完成，共 {len(treasure_ids)} 件")
    return treasure_ids


def _get_general(user_id, general_id):
    for g in generals_cache.get(user_id, []):
        if g["id"] == general_id:
            return g
    return None


def _apply_treasure_attrs(general, treasure, sign):
    for treasure_attr, general_attr in ATTR_FIELD_MAP.items():
        val = treasure.get(treasure_attr, 0)
        if val:
            general[general_attr] = general.get(general_attr, 0) + sign * val


def _find_equipped_of_type(user_id, general_id, treasure_type):
    for t in treasure_cache.values():
        if (t["user_id"] == user_id
                and t["is_equipped"]
                and t["general_id"] == general_id
                and t["treasure_type"] == treasure_type):
            return t
    return None


async def _unequip_internal(treasure_id):
    treasure = treasure_cache.get(treasure_id)
    if not treasure or not treasure["is_equipped"]:
        return

    general_id = treasure["general_id"]
    user_id = treasure["user_id"]
    general = _get_general(user_id, general_id)
    if general:
        _apply_treasure_attrs(general, treasure, -1)

    treasure["is_equipped"] = 0
    treasure["general_id"] = None

    await update_treasure(treasure_id, {"is_equipped": 0, "general_id": None})
    if general:
        gen_updates = {ATTR_FIELD_MAP[k]: general[ATTR_FIELD_MAP[k]] for k in ATTR_FIELD_MAP}
        await update_general(general_id, gen_updates)
        sync_general_cache_update(general_id, gen_updates)


async def _equip_internal(treasure_id, general_id):
    treasure = treasure_cache.get(treasure_id)
    if not treasure:
        return

    user_id = treasure["user_id"]
    general = _get_general(user_id, general_id)
    if general:
        _apply_treasure_attrs(general, treasure, 1)

    treasure["is_equipped"] = 1
    treasure["general_id"] = general_id

    await update_treasure(treasure_id, {"is_equipped": 1, "general_id": general_id})
    if general:
        gen_updates = {ATTR_FIELD_MAP[k]: general[ATTR_FIELD_MAP[k]] for k in ATTR_FIELD_MAP}
        await update_general(general_id, gen_updates)
        sync_general_cache_update(general_id, gen_updates)


async def equip_treasure(user_id, treasure_id, general_id):
    treasure = treasure_cache.get(treasure_id)
    if not treasure:
        return False, "宝物不存在"
    if treasure["user_id"] != user_id:
        return False, "宝物不属于你"
    if treasure["is_equipped"]:
        if treasure["general_id"] == general_id:
            return False, "该宝物已装备在此武将上"
        return False, "该宝物已装备在其他武将上"

    general = _get_general(user_id, general_id)
    if not general:
        return False, "武将不存在"

    status = general.get("status", 0)
    if status in (3, 4):
        return False, "武将当前处于战斗中或死亡状态，无法装备宝物"

    if general.get("level", 0) < treasure["level"]:
        return False, f"需要武将等级达到{treasure['level']}级才能装备此宝物"

    new_treasure_attrs = {k: treasure.get(k, 0) for k in ATTR_FIELD_MAP}
    existing = _find_equipped_of_type(user_id, general_id, treasure["treasure_type"])
    if existing:
        existing_attrs = {k: existing.get(k, 0) for k in ATTR_FIELD_MAP}
        net_delta = {}
        for k in ATTR_FIELD_MAP:
            diff = new_treasure_attrs.get(k, 0) - existing_attrs.get(k, 0)
            if diff != 0:
                net_delta[k] = diff
        if status in (1, 2) and net_delta:
            ok, err = _check_troop_capacity(general, net_delta)
            if not ok:
                return False, err
        await _unequip_internal(existing["id"])
    else:
        if status in (1, 2):
            ok, err = _check_troop_capacity(general, new_treasure_attrs)
            if not ok:
                return False, err

    await _equip_internal(treasure_id, general_id)
    return True, "装备成功"


async def unequip_treasure(user_id, treasure_id):
    treasure = treasure_cache.get(treasure_id)
    if not treasure:
        return False, "宝物不存在"
    if treasure["user_id"] != user_id:
        return False, "宝物不属于你"
    if not treasure["is_equipped"]:
        return False, "该宝物未装备"

    general_id = treasure["general_id"]
    general = _get_general(user_id, general_id)
    if general:
        status = general.get("status", 0)
        if status in (3, 4):
            return False, "武将当前处于战斗中或死亡状态，无法卸载宝物"
        if status in (1, 2):
            neg_attrs = {k: -treasure.get(k, 0) for k in ATTR_FIELD_MAP if treasure.get(k, 0)}
            ok, err = _check_troop_capacity(general, neg_attrs)
            if not ok:
                return False, err

    await _unequip_internal(treasure_id)
    return True, "卸载成功"


def get_user_treasures_from_cache(user_id):
    return [t for t in treasure_cache.values() if t["user_id"] == user_id]


async def load_all_treasures_to_cache():
    rows = await get_all_treasures()
    treasure_cache.clear()
    for row in rows:
        treasure_cache[row["id"]] = dict(row)
    logger.info(f"宝物缓存加载完成，共 {len(treasure_cache)} 条")


# ─────────────────────────────────────────────────────────────
# 强化 / 分解 / 还原 / 购买 核心逻辑
# ─────────────────────────────────────────────────────────────

MAX_ENHANCE_BASE = 9
DAILY_ENHANCE_LIMIT = 20
GOLD_ENHANCE_COST = 8
GOLD_RESET_COST = 24
MATERIAL_BUY_PRICE = 10
STAR_UPGRADE_BASE_COST = 500

LEVEL_COEFFICIENT_MAP = {
    (1, 5): 1,
    (7, 10): 2,
    (13, 16): 3,
    (20, 25): 4,
    (30, 30): 5,
    (35, 35): 6,
}

ENHANCE_TYPE_FORCE = "force"
ENHANCE_TYPE_INTELLIGENCE = "intelligence"
ENHANCE_TYPE_CHARISMA = "charisma"
ENHANCE_TYPE_WISDOM = "wisdom"
ENHANCE_TYPE_INFANTRY = "infantry"
ENHANCE_TYPE_CAVALRY = "cavalry"
ENHANCE_TYPE_ARCHER = "archer"
ENHANCE_TYPE_GOVERNANCE = "governance"

ENHANCE_PROBABILITY = {
    "神兵": {
        "force": 30, "intelligence": 14, "charisma": 14, "wisdom": 14,
        "infantry": 7, "cavalry": 7, "archer": 7, "governance": 7,
    },
    "宝典": {
        "intelligence": 30, "force": 14, "charisma": 14, "wisdom": 14,
        "infantry": 7, "cavalry": 7, "archer": 7, "governance": 7,
    },
    "神器": {
        "charisma": 30, "force": 14, "intelligence": 14, "wisdom": 14,
        "infantry": 7, "cavalry": 7, "archer": 7, "governance": 7,
    },
}

MATERIAL_TYPE_MAP = {
    "神兵": "red_iron",
    "宝典": "books",
    "神器": "flint",
}


def _get_level_coefficient(level):
    for (low, high), coeff in LEVEL_COEFFICIENT_MAP.items():
        if low <= level <= high:
            return coeff
    return 1


def _get_enhance_cost(level, target_enhance):
    coeff = _get_level_coefficient(level)
    return target_enhance * (coeff + 1)


def _get_enhance_success_rate(level, current_enhance):
    rate = 1.0 - (level * 0.01 + current_enhance * 0.025)
    return max(0.15, min(0.95, rate))


def _get_max_enhance_level(star_level):
    return MAX_ENHANCE_BASE + star_level * 2


STAR_COMBO_CONFIG = {
    1: (0.50, 0.01),
    2: (0.40, 0.02),
    3: (0.30, 0.03),
}


def _get_or_refresh_enhance_daily(user_id):
    today = datetime.date.today().isoformat()
    record = treasure_enhance_daily.get(user_id)
    if record is None or record.get("date") != today:
        treasure_enhance_daily[user_id] = {"count": DAILY_ENHANCE_LIMIT, "date": today}
    return treasure_enhance_daily[user_id]


def _find_troop_by_general_id(general_id):
    for tid, troop in troop_cache.items():
        if troop.get("general_id") == general_id:
            return troop
    return None


def _check_troop_capacity(general, treasure_attr_delta):
    general_id = general["id"]
    troop = _find_troop_by_general_id(general_id)
    if not troop:
        return True, ""
    current_total = calculate_total_troops(troop.get("team", []))
    temp_general = dict(general)
    for attr, delta in treasure_attr_delta.items():
        key = ATTR_FIELD_MAP.get(attr, attr)
        temp_general[key] = temp_general.get(key, 0) + delta
    new_max = get_general_max_troop_count(temp_general)
    if current_total > new_max:
        return False, f"部队兵力({current_total})将超过可携带上限({new_max})，无法操作"
    return True, ""


def _check_operation_allowed(treasure, treasure_attr_delta=None):
    if not treasure.get("is_equipped"):
        return True, ""
    general_id = treasure["general_id"]
    user_id = treasure["user_id"]
    general = _get_general(user_id, general_id)
    if not general:
        return True, ""
    status = general.get("status", 0)
    if status in (3, 4):
        return False, "武将当前处于战斗中或死亡状态，无法操作宝物"
    if status in (1, 2) and treasure_attr_delta:
        ok, err = _check_troop_capacity(general, treasure_attr_delta)
        if not ok:
            return False, err
    return True, ""


def _random_enhance_attr(treasure_type):
    probs = ENHANCE_PROBABILITY.get(treasure_type, ENHANCE_PROBABILITY["神兵"])
    items = list(probs.items())
    attrs = [it[0] for it in items]
    weights = [it[1] for it in items]
    return random.choices(attrs, weights=weights, k=1)[0]


def _get_enhance_attr_delta(attr_name):
    """返回本次强化对属性的增量"""
    if attr_name == ENHANCE_TYPE_WISDOM:
        return random.randint(8, 15)
    return 1


async def _update_general_attrs_for_treasure(general, treasure_attr_delta, sign):
    """更新武将属性（内存+DB），sign=1为增加，-1为减少"""
    general_id = general["id"]
    gen_updates = {}
    for treasure_attr, delta in treasure_attr_delta.items():
        general_field = ATTR_FIELD_MAP.get(treasure_attr, treasure_attr)
        general[general_field] = general.get(general_field, 0) + sign * delta
        gen_updates[general_field] = general[general_field]
    await update_general(general_id, gen_updates)
    sync_general_cache_update(general_id, gen_updates)


# ─────────────────────────────────────────────────────────────
# 强化
# ─────────────────────────────────────────────────────────────
async def enhance_treasure(user_id, treasure_id, use_gold=False):
    treasure = treasure_cache.get(treasure_id)
    if not treasure:
        return False, "宝物不存在", None
    if treasure["user_id"] != user_id:
        return False, "宝物不属于你", None

    current_enhance = treasure.get("enhance", 0)
    max_enhance = _get_max_enhance_level(treasure.get("star_level", 0))
    if current_enhance >= max_enhance:
        return False, f"该宝物强化上限为{max_enhance}次，已达到最大强化等级", None

    treasure_level = treasure["level"]
    target_enhance = current_enhance + 1
    cost = _get_enhance_cost(treasure_level, target_enhance)
    treasure_type = treasure["treasure_type"]
    material_field = MATERIAL_TYPE_MAP.get(treasure_type, "red_iron")

    if use_gold:
        res = user_resource_cache.get(user_id)
        if not res or res.get("gold", 0) < GOLD_ENHANCE_COST:
            return False, "黄金不足", None
        res["gold"] -= GOLD_ENHANCE_COST
        await update_user_resource_field(user_id, "gold", res["gold"])
    else:
        daily = _get_or_refresh_enhance_daily(user_id)
        if daily["count"] <= 0:
            return False, "本日强化次数已用完", None
        res = user_resource_cache.get(user_id)
        if not res or res.get(material_field, 0) < cost:
            material_name = {"red_iron": "赤铁", "books": "书籍", "flint": "燧石"}.get(material_field, material_field)
            return False, f"{material_name}不足，需要{cost}个", None
        res[material_field] -= cost
        daily["count"] -= 1
        await update_user_resource_field(user_id, material_field, res[material_field])

        success_rate = _get_enhance_success_rate(treasure_level, current_enhance)
        if random.random() >= success_rate:
            daily_remaining = _get_or_refresh_enhance_daily(user_id)["count"]
            return False, f"强化失败（成功率{success_rate*100:.0f}%）", {
                "success": False,
                "cost": cost,
                "daily_remaining": daily_remaining,
            }

    attr_name = _random_enhance_attr(treasure_type)
    attr_delta = _get_enhance_attr_delta(attr_name)
    treasure_attr_delta = {attr_name: attr_delta}
    treasure[attr_name] = treasure.get(attr_name, 0) + attr_delta
    treasure["enhance"] = current_enhance + 1

    await update_treasure(treasure_id, {
        "enhance": treasure["enhance"],
        attr_name: treasure[attr_name],
    })

    if treasure.get("is_equipped"):
        general_id = treasure["general_id"]
        general = _get_general(user_id, general_id)
        if general:
            await _update_general_attrs_for_treasure(general, treasure_attr_delta, 1)

    daily_remaining = None
    if not use_gold:
        daily_remaining = _get_or_refresh_enhance_daily(user_id)["count"]

    return True, "强化成功", {
        "treasure": dict(treasure),
        "enhance_attr": attr_name,
        "enhance_delta": attr_delta,
        "cost": cost,
        "daily_remaining": daily_remaining,
    }


# ─────────────────────────────────────────────────────────────
# 分解
# ─────────────────────────────────────────────────────────────
async def decompose_treasure(user_id, treasure_id):
    treasure = treasure_cache.get(treasure_id)
    if not treasure:
        return False, "宝物不存在", None
    if treasure["user_id"] != user_id:
        return False, "宝物不属于你", None

    if treasure.get("is_equipped"):
        attr_delta = {}
        for attr_name in ATTR_FIELD_MAP:
            val = treasure.get(attr_name, 0)
            if val:
                attr_delta[attr_name] = -val
        ok, err = _check_operation_allowed(treasure, attr_delta)
        if not ok:
            return False, err, None
        general_id = treasure["general_id"]
        general = _get_general(user_id, general_id)
        if general:
            await _update_general_attrs_for_treasure(general, attr_delta, 1)
        treasure["is_equipped"] = 0
        treasure["general_id"] = None

    treasure_level = treasure["level"]
    star_level = treasure.get("star_level", 0)
    if star_level > 0:
        material_count = treasure_level * star_level * 3
    else:
        material_count = treasure_level
    treasure_type = treasure["treasure_type"]
    material_field = MATERIAL_TYPE_MAP.get(treasure_type, "red_iron")
    material_name = {"red_iron": "赤铁", "books": "书籍", "flint": "燧石"}.get(material_field, material_field)

    res = user_resource_cache.get(user_id)
    if res:
        res[material_field] = res.get(material_field, 0) + material_count
        await update_user_resource_field(user_id, material_field, res[material_field])

    del treasure_cache[treasure_id]
    await delete_treasure(treasure_id)

    return True, f"分解成功，获得{material_count}个{material_name}", {
        "treasure_id": treasure_id,
        "material_type": material_name,
        "material_count": material_count,
    }


# ─────────────────────────────────────────────────────────────
# 还原（重置强化等级为0）
# ─────────────────────────────────────────────────────────────
async def reset_treasure(user_id, treasure_id):
    treasure = treasure_cache.get(treasure_id)
    if not treasure:
        return False, "宝物不存在", None
    if treasure["user_id"] != user_id:
        return False, "宝物不属于你", None

    current_enhance = treasure.get("enhance", 0)
    if current_enhance == 0:
        return False, "该宝物未强化过，无需还原", None

    template = TREASURE_TEMPLATE_MAP.get(treasure["treasure_name"])
    if not template:
        return False, "宝物模板不存在", None

    if treasure.get("is_equipped"):
        attr_delta = {}
        for attr_name in ATTR_FIELD_MAP:
            current_val = treasure.get(attr_name, 0)
            template_val = template.get(attr_name, 0)
            star_bonus = treasure.get(f"star_{attr_name}", 0)
            target_val = template_val + star_bonus
            if current_val != target_val:
                attr_delta[attr_name] = target_val - current_val
        if attr_delta:
            ok, err = _check_operation_allowed(treasure, attr_delta)
            if not ok:
                return False, err, None
            general_id = treasure["general_id"]
            general = _get_general(user_id, general_id)
            if general:
                await _update_general_attrs_for_treasure(general, attr_delta, 1)

    res = user_resource_cache.get(user_id)
    if not res or res.get("gold", 0) < GOLD_RESET_COST:
        return False, "黄金不足", None
    res["gold"] -= GOLD_RESET_COST
    await update_user_resource_field(user_id, "gold", res["gold"])

    reset_attrs = {}
    for attr_name in ATTR_FIELD_MAP:
        template_val = template.get(attr_name, 0)
        star_bonus = treasure.get(f"star_{attr_name}", 0)
        treasure[attr_name] = template_val + star_bonus
        reset_attrs[attr_name] = template_val + star_bonus
    treasure["enhance"] = 0
    reset_attrs["enhance"] = 0

    await update_treasure(treasure_id, reset_attrs)

    return True, "还原成功", {
        "treasure": dict(treasure),
    }


# ─────────────────────────────────────────────────────────────
# 购买强化材料
# ─────────────────────────────────────────────────────────────
async def buy_material(user_id, material_type, quantity):
    if material_type not in ("red_iron", "books", "flint"):
        return False, "材料类型无效，可选：red_iron/books/flint"

    if not isinstance(quantity, int) or quantity <= 0:
        return False, "数量必须为正整数"

    total_cost = quantity * MATERIAL_BUY_PRICE
    res = user_resource_cache.get(user_id)
    if not res or res.get("copper", 0) < total_cost:
        return False, f"铜币不足，需要{total_cost}个"

    res["copper"] -= total_cost
    res[material_type] = res.get(material_type, 0) + quantity

    await update_user_resource(user_id, {
        "copper": res["copper"],
        material_type: res[material_type],
    })

    material_name = {"red_iron": "赤铁", "books": "书籍", "flint": "燧石"}.get(material_type, material_type)
    return True, f"购买成功，消耗{total_cost}铜币，获得{quantity}个{material_name}", {
        "material_type": material_name,
        "quantity": quantity,
        "cost": total_cost,
        "copper": res["copper"],
        "balance": res[material_type],
    }


# ─────────────────────────────────────────────────────────────
# 查询强化剩余次数
# ─────────────────────────────────────────────────────────────
def get_enhance_quota(user_id):
    daily = _get_or_refresh_enhance_daily(user_id)
    return {
        "daily_limit": DAILY_ENHANCE_LIMIT,
        "daily_remaining": daily["count"],
    }


# ─────────────────────────────────────────────────────────────
# 升星
# ─────────────────────────────────────────────────────────────
async def star_upgrade(user_id, treasure_ids, base_index, target_attr):
    if len(treasure_ids) != 5:
        return False, "需要5件相同宝物进行升星", None
    if base_index < 0 or base_index >= 5:
        return False, "基底索引无效", None

    valid_attrs = ("force", "intelligence", "charisma", "wisdom",
                   "infantry", "cavalry", "archer", "governance")
    if target_attr not in valid_attrs:
        return False, "指定的属性无效", None

    treasures = []
    for tid in treasure_ids:
        t = treasure_cache.get(tid)
        if not t:
            return False, f"宝物 {tid} 不存在", None
        if t["user_id"] != user_id:
            return False, f"宝物 {tid} 不属于你", None
        treasures.append(t)

    base = treasures[base_index]
    current_star = base.get("star_level", 0)
    if current_star >= 3:
        return False, "已达到最大星等（三星）", None

    target_star = current_star + 1

    for t in treasures:
        if t["treasure_name"] != base["treasure_name"]:
            return False, "宝物名称不一致", None
        if t.get("star_level", 0) != current_star:
            return False, "宝物星等不一致", None

    for t in treasures:
        if t.get("is_equipped"):
            attr_delta = {}
            for attr_name in ATTR_FIELD_MAP:
                val = t.get(attr_name, 0)
                if val:
                    attr_delta[attr_name] = -val
            ok, err = _check_operation_allowed(t, attr_delta)
            if not ok:
                return False, err, None

    level = base["level"]
    cost = STAR_UPGRADE_BASE_COST * level * (1 + target_star)
    treasure_type = base["treasure_type"]
    material_field = MATERIAL_TYPE_MAP.get(treasure_type, "red_iron")
    material_name = {"red_iron": "赤铁", "books": "书籍", "flint": "燧石"}.get(material_field, material_field)

    res = user_resource_cache.get(user_id)
    if not res or res.get(material_field, 0) < cost:
        return False, f"{material_name}不足，需要{cost}个", None

    old_attrs = {}
    for attr_name in ATTR_FIELD_MAP:
        old_attrs[attr_name] = base.get(attr_name, 0)
    old_combo = base.get("combo_rate", 0.0)

    combo_increased = False
    combo_delta = 0.0

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.begin()
        try:
            res[material_field] -= cost
            await update_user_resource_field(user_id, material_field, res[material_field], conn)

            for i, t in enumerate(treasures):
                if i == base_index:
                    continue
                if t.get("is_equipped"):
                    general_id = t["general_id"]
                    general = _get_general(user_id, general_id)
                    if general:
                        _apply_treasure_attrs(general, t, -1)
                        gen_updates = {ATTR_FIELD_MAP[k]: general[ATTR_FIELD_MAP[k]] for k in ATTR_FIELD_MAP}
                        await update_general(general_id, gen_updates, conn)
                        sync_general_cache_update(general_id, gen_updates)
                del treasure_cache[t["id"]]
                await delete_treasure(t["id"], conn)

            base["star_level"] = target_star
            base["enhance"] = 0

            star_delta = random.randint(8, 15) if target_attr == "wisdom" else 1
            star_field = f"star_{target_attr}"
            base[star_field] = base.get(star_field, 0) + star_delta

            template = TREASURE_TEMPLATE_MAP.get(base["treasure_name"])
            update_fields = {"star_level": target_star, "enhance": 0}
            update_fields[star_field] = base[star_field]

            for attr_name in ATTR_FIELD_MAP:
                template_val = template.get(attr_name, 0) if template else 0
                star_bonus = base.get(f"star_{attr_name}", 0)
                base[attr_name] = template_val + star_bonus
                update_fields[attr_name] = base[attr_name]

            prob, bonus = STAR_COMBO_CONFIG[target_star]
            if random.random() < prob:
                base["combo_rate"] = base.get("combo_rate", 0.0) + bonus
                combo_increased = True
                combo_delta = bonus
            update_fields["combo_rate"] = base["combo_rate"]

            await update_treasure(base["id"], update_fields, conn)

            if base.get("is_equipped"):
                general_id = base["general_id"]
                general = _get_general(user_id, general_id)
                if general:
                    attr_delta = {}
                    for attr_name in ATTR_FIELD_MAP:
                        new_val = base.get(attr_name, 0)
                        old_val = old_attrs.get(attr_name, 0)
                        diff = new_val - old_val
                        if diff != 0:
                            attr_delta[attr_name] = diff

                    for treasure_attr, delta in attr_delta.items():
                        general_field = ATTR_FIELD_MAP[treasure_attr]
                        general[general_field] = general.get(general_field, 0) + delta

                    combo_diff = base.get("combo_rate", 0.0) - old_combo
                    if combo_diff != 0:
                        general["combo_rate"] = general.get("combo_rate", 0.0) + combo_diff

                    gen_updates = {ATTR_FIELD_MAP[k]: general[ATTR_FIELD_MAP[k]] for k in ATTR_FIELD_MAP}
                    gen_updates["combo_rate"] = general["combo_rate"]
                    await update_general(general_id, gen_updates, conn)
                    sync_general_cache_update(general_id, gen_updates)

            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    return True, f"升星成功，宝物已升至{target_star}星", {
        "treasure": dict(base),
        "star_level": target_star,
        "target_star": target_star,
        "combo_rate_increased": combo_increased,
        "combo_rate_delta": combo_delta,
        "cost": cost,
        "material_type": material_name,
    }
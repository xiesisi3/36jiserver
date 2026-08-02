# -*- coding: utf-8 -*-
# 军团兑换系统静态配置
# 本模块为纯数据配置，不依赖任何项目内模块，可被任意模块安全导入
# 所有积分消耗、解锁条件、道具定价均在此集中管理，方便手动微调

# =============================================================================
# 一、军团粮仓上限扩展（9个阶段，初始为阶段0：10W上限）
# 阶段值（容量）与积分消耗成正比，比例：1军团积分 = 100存储上限
# =============================================================================
GRANARY_STAGES = [
    {"stage": 0, "max": 100000,   "cost": 0},
    {"stage": 1, "max": 500000,   "cost": 5000},
    {"stage": 2, "max": 1000000,  "cost": 10000},
    {"stage": 3, "max": 2000000,  "cost": 20000},
    {"stage": 4, "max": 4000000,  "cost": 40000},
    {"stage": 5, "max": 8000000,  "cost": 80000},
    {"stage": 6, "max": 16000000, "cost": 160000},
    {"stage": 7, "max": 32000000, "cost": 320000},
    {"stage": 8, "max": 64000000, "cost": 640000},
    {"stage": 9, "max": 100000000,"cost": 1000000},
]

# =============================================================================
# 二、宝箱与货票类解锁（阶段0默认解锁，阶段1-8需军团积分）
# 个人积分 = 战斗结算中的宝箱/货票分值 × 5
# 分值来源：data/combat_reward_config.py 的 TICKET_SCORE 和 CHEST_SCORE
# =============================================================================
CHEST_TICKET_STAGES = [
    {
        "stage": 0,
        "cost": 0,
        "chests": ["实木宝箱"],
        "tickets": ["私人货票"],
        "prices": {
            "实木宝箱": 125,
            "私人货票": 125,
        },
    },
    {
        "stage": 1,
        "cost": 5000,
        "chests": ["青铜宝箱"],
        "tickets": ["普通货票"],
        "prices": {
            "青铜宝箱": 375,
            "普通货票": 375,
        },
    },
    {
        "stage": 2,
        "cost": 10000,
        "chests": ["精铁宝箱"],
        "tickets": ["官府货票"],
        "prices": {
            "精铁宝箱": 1000,
            "官府货票": 1000,
        },
    },
    {
        "stage": 3,
        "cost": 20000,
        "chests": ["白银宝箱"],
        "tickets": ["吕氏货票"],
        "prices": {
            "白银宝箱": 2500,
            "吕氏货票": 2500,
        },
    },
    {
        "stage": 4,
        "cost": 40000,
        "chests": ["黄金宝箱"],
        "tickets": ["范式货票"],
        "prices": {
            "黄金宝箱": 6250,
            "范式货票": 6250,
        },
    },
    {
        "stage": 5,
        "cost": 80000,
        "chests": ["钻石宝箱"],
        "tickets": ["内府货票"],
        "prices": {
            "钻石宝箱": 15000,
            "内府货票": 15000,
        },
    },
    {
        "stage": 6,
        "cost": 160000,
        "chests": ["武神礼包"],
        "tickets": ["王公货票"],
        "prices": {
            "武神礼包": 37500,
            "王公货票": 37500,
        },
    },
    {
        "stage": 7,
        "cost": 320000,
        "chests": ["战神礼包"],
        "tickets": ["亲王货票"],
        "prices": {
            "战神礼包": 100000,
            "亲王货票": 100000,
        },
    },
    {
        "stage": 8,
        "cost": 640000,
        "chests": ["军神礼包"],
        "tickets": ["皇家货票"],
        "prices": {
            "军神礼包": 250000,
            "皇家货票": 250000,
        },
    },
]

# =============================================================================
# 三、加成类道具解锁（4个阶段，全部需要军团积分解锁）
# 军团积分消耗与宝箱货票类总量持平（约120万）
# =============================================================================
BUFF_STAGES = [
    {
        "stage": 1,
        "cost": 80000,
        "items": [
            "天赋重置丹", "洗髓丹", "经验书",
            "赤铁", "书籍", "燧石",
        ],
        "prices": {
            "天赋重置丹": 2000,
            "洗髓丹": 2000,
            "经验书": 500,
            "赤铁": 300,
            "书籍": 300,
            "燧石": 300,
        },
    },
    {
        "stage": 2,
        "cost": 160000,
        "items": [
            "步步为营1", "披坚执锐1", "临阵磨枪1", "天罡护体1",
            "随机技能书",
        ],
        "prices": {
            "步步为营1": 1000,
            "披坚执锐1": 1000,
            "临阵磨枪1": 1000,
            "天罡护体1": 1000,
            "随机技能书": 3000,
        },
    },
    {
        "stage": 3,
        "cost": 320000,
        "items": [
            "步步为营2", "披坚执锐2", "临阵磨枪2", "天罡护体2",
            "高级经验书",
        ],
        "prices": {
            "步步为营2": 2000,
            "披坚执锐2": 2000,
            "临阵磨枪2": 2000,
            "天罡护体2": 2000,
            "高级经验书": 2500,
        },
    },
    {
        "stage": 4,
        "cost": 640000,
        "items": [
            "步步为营3", "披坚执锐3", "临阵磨枪3", "天罡护体3",
            "斗志昂扬",
        ],
        "prices": {
            "步步为营3": 4000,
            "披坚执锐3": 4000,
            "临阵磨枪3": 4000,
            "天罡护体3": 4000,
            "斗志昂扬": 5000,
        },
    },
]

# =============================================================================
# 四、特殊类道具解锁（4个阶段，全部需要军团积分解锁）
# 军团积分消耗与宝箱货票类总量持平（约120万）
# =============================================================================
SPECIAL_STAGES = [
    {
        "stage": 1,
        "cost": 80000,
        "items": ["土灵珠"],
        "prices": {
            "土灵珠": 10000,
        },
    },
    {
        "stage": 2,
        "cost": 160000,
        "items": ["红包"],
        "prices": {
            "红包": 2000,
        },
    },
    {
        "stage": 3,
        "cost": 320000,
        "items": ["水灵珠"],
        "prices": {
            "水灵珠": 30000,
        },
    },
    {
        "stage": 4,
        "cost": 640000,
        "items": ["金砖"],
        "prices": {
            "金砖": 10000,
        },
    },
]

# =============================================================================
# 五、阶段4加成类——技能书（22种单本）
# 该阶段解锁后，玩家可兑换指定技能书，每种5,000积分
# =============================================================================
SKILL_BOOK_LIST = [
    "勤政", "反击", "屯田", "巧变", "筑城",
    "炼金", "鼓舞", "连营", "论战", "不屈",
    "刚胆", "诱敌", "久战", "洞察", "死战",
    "破阵", "强袭", "乱击", "箭岚", "天佑",
    "攻城", "奇袭",
]

# 技能书统一价格
SKILL_BOOK_PRICE = 5000

# =============================================================================
# 六、灵珠配置
# =============================================================================
PEARL_CONFIG = {
    "土灵珠": {
        "bonus": 0.50,
        "description": "提高城池资源获得收益50%",
        "upgrade_to": "水灵珠",
    },
    "水灵珠": {
        "bonus": 1.50,
        "description": "提高城池资源获得收益150%",
        "upgrade_to": None,
        "cannot_downgrade": True,
    },
}

# 灵珠生效的城池等级上限
PEARL_MAX_TOWN_LEVEL = 3

# =============================================================================
# 七、便捷查询函数
# =============================================================================

def get_granary_stage_cost(stage):
    """获取指定粮仓阶段的积分消耗"""
    for s in GRANARY_STAGES:
        if s["stage"] == stage:
            return s["cost"]
    return None


def get_granary_stage_max(stage):
    """获取指定粮仓阶段的上限值"""
    for s in GRANARY_STAGES:
        if s["stage"] == stage:
            return s["max"]
    return None


def get_chest_ticket_stage_cost(stage):
    """获取指定宝箱货票阶段的积分消耗"""
    for s in CHEST_TICKET_STAGES:
        if s["stage"] == stage:
            return s["cost"]
    return None


def get_buff_stage_cost(stage):
    """获取指定加成类阶段的积分消耗"""
    for s in BUFF_STAGES:
        if s["stage"] == stage:
            return s["cost"]
    return None


def get_special_stage_cost(stage):
    """获取指定特殊类阶段的积分消耗"""
    for s in SPECIAL_STAGES:
        if s["stage"] == stage:
            return s["cost"]
    return None


def get_item_price(item_name):
    """获取道具的个人积分价格，遍历所有类型查找"""
    for stage in CHEST_TICKET_STAGES:
        if item_name in stage.get("prices", {}):
            return stage["prices"][item_name]

    for stage in BUFF_STAGES:
        if item_name in stage.get("prices", {}):
            return stage["prices"][item_name]

    if item_name in SKILL_BOOK_LIST:
        return SKILL_BOOK_PRICE

    for stage in SPECIAL_STAGES:
        if item_name in stage.get("prices", {}):
            return stage["prices"][item_name]

    return None


def get_item_unlock_stage(item_name):
    """获取道具的解锁阶段，返回 (类型标识, 阶段号)"""
    for stage in CHEST_TICKET_STAGES:
        if item_name in stage["chests"] or item_name in stage["tickets"]:
            return ("chest_ticket", stage["stage"])

    for stage in BUFF_STAGES:
        if item_name in stage["items"]:
            return ("buff", stage["stage"])

    if item_name in SKILL_BOOK_LIST:
        return ("buff", 4)

    for stage in SPECIAL_STAGES:
        if item_name in stage["items"]:
            return ("special", stage["stage"])

    return None


def get_unlockable_items(category, stage):
    """获取某类型某阶段解锁的道具列表"""
    if category == "chest_ticket":
        for s in CHEST_TICKET_STAGES:
            if s["stage"] == stage:
                return s["chests"] + s["tickets"]
    elif category == "buff":
        items = []
        for s in BUFF_STAGES:
            if s["stage"] <= stage:
                items.extend(s["items"])
        if stage >= 4:
            items.extend(SKILL_BOOK_LIST)
        return items
    elif category == "special":
        for s in SPECIAL_STAGES:
            if s["stage"] == stage:
                return s["items"]
    return []


def get_all_unlockable_items(chest_ticket_stage, buff_stage, special_stage):
    """获取军团当前所有可兑换的道具列表"""
    items = {}
    # 宝箱与货票（累积解锁）
    for s in CHEST_TICKET_STAGES:
        if s["stage"] <= chest_ticket_stage:
            for item_name, price in s.get("prices", {}).items():
                items[item_name] = price
    # 加成类（累积解锁）
    for s in BUFF_STAGES:
        if s["stage"] <= buff_stage:
            for item_name, price in s.get("prices", {}).items():
                items[item_name] = price
    # 技能书
    if buff_stage >= 4:
        for name in SKILL_BOOK_LIST:
            items[name] = SKILL_BOOK_PRICE
    # 特殊类（累积解锁）
    for s in SPECIAL_STAGES:
        if s["stage"] <= special_stage:
            for item_name, price in s.get("prices", {}).items():
                items[item_name] = price
    return items
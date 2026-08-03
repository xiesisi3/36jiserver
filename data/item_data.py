# -*- coding: utf-8 -*-
# 道具静态数据
# 道具分为三类：chest（宝箱类）、player（玩家类）、general（武将类）
# category 字段说明：
#   chest:   宝箱类，可直接打开，获得铜钱 + 概率掉落宝物/经验书/技能书
#   player:  玩家类，直接增加玩家资源（木材/粮食/铁矿/黄金）
#   general: 武将类，需指定目标武将使用
# player 类 subcategory 说明：
#   resource: 可使用，增加玩家资源
#   material: 强化材料，不可直接使用，由宝物强化模块消耗
#   pearl:    灵珠，用于封地城池提高资源收益，通过军团接口使用
# general 类 subcategory 说明：
#   buff:         临时加成（攻击/防御/血量/士气/经验倍率）
#   exp:          经验书
#   reset:        重置类（属性点/天赋）
#   skill_book:   技能书（直接学会指定技能）
#   random_skill: 随机技能书（元道具，使用后获得一本随机技能书）
# condition 说明（可组合，None 表示无条件）：
#   "alive":        武将存活（status != 4）
#   "not_fighting": 武将非战斗中（status != 3）
#   "not_hero":     非22英雄武将（非固定英雄池中的武将）

ITEMS = [
    # =====================================================================
    # 宝箱类（chest）
    # copper: [min, max] 铜钱随机范围
    # drops: 独立概率掉落列表，每项独立判定
    #   type=treasure: level 为宝物等级, rate 为掉落概率
    #   type=item:     name 为道具名称, rate 为掉落概率
    # =====================================================================
    {
        "name": "实木宝箱",
        "category": "chest",
        "icon_path": "resources/img/item/实木宝箱.png",
        "copper": [150, 250],
        "drops": [
            {"type": "treasure", "level": 1, "rate": 0.10},
            {"type": "treasure", "level": 3, "rate": 0.05},
            {"type": "item", "name": "经验书", "rate": 0.01},
        ],
    },
    {
        "name": "青铜宝箱",
        "category": "chest",
        "icon_path": "resources/img/item/青铜宝箱.png",
        "copper": [240, 420],
        "drops": [
            {"type": "treasure", "level": 3, "rate": 0.10},
            {"type": "treasure", "level": 5, "rate": 0.05},
            {"type": "item", "name": "经验书", "rate": 0.02},
        ],
    },
    {
        "name": "精铁宝箱",
        "category": "chest",
        "icon_path": "resources/img/item/精铁宝箱.png",
        "copper": [400, 590],
        "drops": [
            {"type": "treasure", "level": 5, "rate": 0.10},
            {"type": "treasure", "level": 7, "rate": 0.05},
            {"type": "item", "name": "经验书", "rate": 0.03},
        ],
    },
    {
        "name": "白银宝箱",
        "category": "chest",
        "icon_path": "resources/img/item/白银宝箱.png",
        "copper": [580, 820],
        "drops": [
            {"type": "treasure", "level": 7, "rate": 0.10},
            {"type": "treasure", "level": 10, "rate": 0.05},
            {"type": "item", "name": "高级经验书", "rate": 0.01},
        ],
    },
    {
        "name": "黄金宝箱",
        "category": "chest",
        "icon_path": "resources/img/item/黄金宝箱.png",
        "copper": [710, 1120],
        "drops": [
            {"type": "treasure", "level": 10, "rate": 0.10},
            {"type": "treasure", "level": 13, "rate": 0.05},
            {"type": "item", "name": "高级经验书", "rate": 0.02},
        ],
    },
    {
        "name": "钻石宝箱",
        "category": "chest",
        "icon_path": "resources/img/item/钻石宝箱.png",
        "copper": [900, 1800],
        "drops": [
            {"type": "treasure", "level": 13, "rate": 0.10},
            {"type": "treasure", "level": 16, "rate": 0.05},
            {"type": "item", "name": "高级经验书", "rate": 0.03},
        ],
    },
    {
        "name": "武神礼包",
        "category": "chest",
        "icon_path": "resources/img/item/武神礼包.png",
        "copper": [1400, 2800],
        "drops": [
            {"type": "treasure", "level": 16, "rate": 0.10},
            {"type": "treasure", "level": 20, "rate": 0.05},
            {"type": "item", "name": "技能书", "rate": 0.01},
        ],
    },
    {
        "name": "战神礼包",
        "category": "chest",
        "icon_path": "resources/img/item/战神礼包.png",
        "copper": [2000, 3500],
        "drops": [
            {"type": "treasure", "level": 20, "rate": 0.10},
            {"type": "treasure", "level": 25, "rate": 0.05},
            {"type": "treasure", "level": 30, "rate": 0.02},
            {"type": "item", "name": "技能书", "rate": 0.02},
        ],
    },
    {
        "name": "军神礼包",
        "category": "chest",
        "icon_path": "resources/img/item/军神礼包.png",
        "copper": [2200, 4000],
        "drops": [
            {"type": "treasure", "level": 25, "rate": 0.10},
            {"type": "treasure", "level": 30, "rate": 0.05},
            {"type": "treasure", "level": 35, "rate": 0.002},
            {"type": "item", "name": "技能书", "rate": 0.03},
        ],
    },

    # =====================================================================
    # 玩家类-资源型（player / resource）
    # effects: 资源增加效果，值为 [min, max] 范围或固定值
    #   支持的资源字段: wood, grain, iron, gold
    # =====================================================================
    {
        "name": "私人货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/私人货票.png",
        "effects": {
            "wood": [5000, 10000],
            "grain": [3000, 6000],
            "iron": [1800, 3600],
        },
    },
    {
        "name": "普通货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/普通货票.png",
        "effects": {
            "wood": [10000, 15000],
            "grain": [6000, 9000],
            "iron": [3600, 5400],
        },
    },
    {
        "name": "官府货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/官府货票.png",
        "effects": {
            "wood": [15000, 30000],
            "grain": [9000, 18000],
            "iron": [5400, 10800],
        },
    },
    {
        "name": "吕氏货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/吕氏货票.png",
        "effects": {
            "wood": [30000, 45000],
            "grain": [18000, 27000],
            "iron": [10800, 16200],
        },
    },
    {
        "name": "范式货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/范式货票.png",
        "effects": {
            "wood": [45000, 90000],
            "grain": [27000, 54000],
            "iron": [16200, 32400],
        },
    },
    {
        "name": "内府货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/内府货票.png",
        "effects": {
            "wood": [90000, 135000],
            "grain": [54000, 81000],
            "iron": [32400, 48600],
        },
    },
    {
        "name": "王公货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/王公货票.png",
        "effects": {
            "wood": [135000, 270000],
            "grain": [81000, 162000],
            "iron": [48600, 97200],
        },
    },
    {
        "name": "亲王货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/亲王货票.png",
        "effects": {
            "wood": [270000, 405000],
            "grain": [162000, 243000],
            "iron": [97200, 145800],
        },
    },
    {
        "name": "皇家货票",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/皇家货票.png",
        "effects": {
            "wood": [405000, 810000],
            "grain": [243000, 486000],
            "iron": [145800, 291600],
        },
    },
    {
        "name": "红包",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/红包.png",
        "effects": {
            "gold": 100,
        },
    },
    {
        "name": "金砖",
        "category": "player",
        "subcategory": "resource",
        "icon_path": "resources/img/item/金砖.png",
        "effects": {
            "gold": 500,
        },
    },

    # =====================================================================
    # 玩家类-灵珠（player / pearl）
    # 用于封地城池，提高该城池资源收益，实际效果由 PEARL_CONFIG 控制
    # =====================================================================
    {
        "name": "土灵珠",
        "category": "player",
        "subcategory": "pearl",
        "icon_path": "resources/img/item/土灵珠.png",
        "desc": "提高城池资源获得收益50%",
    },
    {
        "name": "水灵珠",
        "category": "player",
        "subcategory": "pearl",
        "icon_path": "resources/img/item/水灵珠.png",
        "desc": "提高城池资源获得收益150%",
    },

    # =====================================================================
    # 玩家类-强化材料（player / material）
    # 不可直接使用，由宝物强化模块消耗
    # =====================================================================
    {
        "name": "赤铁",
        "category": "player",
        "subcategory": "material",
        "icon_path": "resources/img/item/赤铁.png",
        "resource_field": "red_iron",
        "desc": "强化神兵材料",
    },
    {
        "name": "书籍",
        "category": "player",
        "subcategory": "material",
        "icon_path": "resources/img/item/书籍.png",
        "resource_field": "books",
        "desc": "强化宝典材料",
    },
    {
        "name": "燧石",
        "category": "player",
        "subcategory": "material",
        "icon_path": "resources/img/item/燧石.png",
        "resource_field": "flint",
        "desc": "强化神器材料",
    },

    # =====================================================================
    # 武将类（general）
    # subcategory=buff:   临时加成类
    #   effects 中可包含: morale, attack_bonus, defense_bonus, hp_bonus, exp_bonus
    # subcategory=exp:    经验书
    #   exp: 经验值
    # subcategory=reset:  重置类
    #   reset_type: "attributes"（属性点+性格） / "talents"（天赋）
    # subcategory=skill_book:     技能书（直接学会）
    #   skill_name: 技能名称
    # subcategory=random_skill:   随机技能书
    #   skill_pool: 可选技能列表
    # condition: 使用条件列表
    # =====================================================================
    {
        "name": "斗志昂扬",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/斗志昂扬.png",
        "effects": {"morale": 1000},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "步步为营1",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/步步为营1.png",
        "effects": {"defense_bonus": 0.30},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "步步为营2",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/步步为营2.png",
        "effects": {"defense_bonus": 0.50},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "步步为营3",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/步步为营3.png",
        "effects": {"defense_bonus": 1.00},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "临阵磨枪1",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/临阵磨枪1.png",
        "effects": {"exp_bonus": 0.50},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "临阵磨枪2",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/临阵磨枪2.png",
        "effects": {"exp_bonus": 1.00},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "临阵磨枪3",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/临阵磨枪3.png",
        "effects": {"exp_bonus": 1.50},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "披坚执锐1",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/披坚执锐1.png",
        "effects": {"attack_bonus": 0.30},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "披坚执锐2",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/披坚执锐2.png",
        "effects": {"attack_bonus": 0.50},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "披坚执锐3",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/披坚执锐3.png",
        "effects": {"attack_bonus": 1.00},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "天罡护体1",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/天罡护体1.png",
        "effects": {"hp_bonus": 0.30},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "天罡护体2",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/天罡护体2.png",
        "effects": {"hp_bonus": 0.50},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "天罡护体3",
        "category": "general",
        "subcategory": "buff",
        "icon_path": "resources/img/item/天罡护体3.png",
        "effects": {"hp_bonus": 1.00},
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "洗髓丹",
        "category": "general",
        "subcategory": "reset",
        "icon_path": "resources/img/item/洗髓丹.png",
        "reset_type": "attributes",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "天赋重置丹",
        "category": "general",
        "subcategory": "reset",
        "icon_path": "resources/img/item/天赋重置丹.png",
        "reset_type": "talents",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "经验书",
        "category": "general",
        "subcategory": "exp",
        "icon_path": "resources/img/item/经验书.png",
        "exp": 5000,
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "高级经验书",
        "category": "general",
        "subcategory": "exp",
        "icon_path": "resources/img/item/高级经验书.png",
        "exp": 25000,
        "condition": ["alive", "not_fighting"],
    },
    {
        "name": "技能书",
        "category": "general",
        "subcategory": "random_skill",
        "icon_path": "resources/img/item/技能书.png",
        "skill_pool": [
            "勤政", "反击", "强攻", "奇袭", "倾城", "穿透", "魅惑", "突击",
            "军神", "急行", "固守", "火袭", "神算", "霸王", "狂热", "鼓舞",
            "狙击", "枪阵", "奇将", "武卒", "混战", "无双",
        ],
        "condition": None,
    },
    {
        "name": "勤政",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "勤政",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "反击",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "反击",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "强攻",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "强攻",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "奇袭",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "奇袭",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "倾城",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "倾城",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "穿透",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "穿透",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "魅惑",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "魅惑",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "突击",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "突击",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "军神",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "军神",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "急行",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "急行",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "固守",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "固守",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "火袭",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "火袭",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "神算",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "神算",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "霸王",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "霸王",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "狂热",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "狂热",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "鼓舞",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "鼓舞",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "狙击",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "狙击",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "枪阵",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "枪阵",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "奇将",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "奇将",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "武卒",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "武卒",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "混战",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "混战",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
    {
        "name": "无双",
        "category": "general",
        "subcategory": "skill_book",
        "icon_path": "resources/img/item/技能书.png",
        "skill_name": "无双",
        "condition": ["alive", "not_fighting", "not_hero"],
    },
]

ITEM_INDEX = {item["name"]: item for item in ITEMS}
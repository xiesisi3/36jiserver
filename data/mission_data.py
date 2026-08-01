# 使命系统静态配置
# 每种使命类型包含多个阶段，每个阶段有阈值和奖励列表
# 奖励类型: "item"（道具）、"treasure"（宝物）、"treasure_set"（宝物套装）、"gold"（黄金）、"special"（特殊）

MISSION_CONFIG = {
    "general_level": {
        "name": "武将升级",
        "description": "自身同名武将等级提升",
        "stages": [
            {"stage": 1, "threshold": 5,  "rewards": [{"type": "item", "item_name": "技能书", "quantity": 1}]},
            {"stage": 2, "threshold": 7,  "rewards": [{"type": "item", "item_name": "技能书", "quantity": 2}]},
            {"stage": 3, "threshold": 10, "rewards": [{"type": "item", "item_name": "技能书", "quantity": 3}]},
            {"stage": 4, "threshold": 13, "rewards": [{"type": "item", "item_name": "白银宝箱", "quantity": 3}]},
            {"stage": 5, "threshold": 16, "rewards": [{"type": "item", "item_name": "黄金宝箱", "quantity": 2}]},
            {"stage": 6, "threshold": 20, "rewards": [{"type": "item", "item_name": "黄金宝箱", "quantity": 3}]},
            {"stage": 7, "threshold": 25, "rewards": [{"type": "item", "item_name": "钻石宝箱", "quantity": 2}]},
            {"stage": 8, "threshold": 30, "rewards": [{"type": "item", "item_name": "钻石宝箱", "quantity": 3}]},
            {"stage": 9, "threshold": 40, "rewards": [{"type": "item", "item_name": "武神礼包", "quantity": 1}]},
        ],
    },
    "hero": {
        "name": "英雄招募",
        "description": "获得的英雄武将数量",
        "stages": [
            {"stage": 1, "threshold": 2,  "rewards": [{"type": "treasure", "treasure_name": "开国校尉剑"}]},
            {"stage": 2, "threshold": 4,  "rewards": [{"type": "treasure", "treasure_name": "和氏璧"}]},
            {"stage": 3, "threshold": 6,  "rewards": [{"type": "treasure_set", "level": 7}]},
            {"stage": 4, "threshold": 9,  "rewards": [{"type": "treasure_set", "level": 13}]},
            {"stage": 5, "threshold": 12, "rewards": [{"type": "treasure_set", "level": 20}]},
            {"stage": 6, "threshold": 15, "rewards": [{"type": "treasure_set", "level": 25}]},
            {"stage": 7, "threshold": 18, "rewards": [{"type": "treasure_set", "level": 25, "refined": True}]},
            {"stage": 8, "threshold": 20, "rewards": [{"type": "treasure_set", "level": 30}]},
            {"stage": 9, "threshold": 22, "rewards": [{"type": "treasure_set", "level": 30, "refined": True}]},
        ],
    },
    "fief": {
        "name": "个人扩张",
        "description": "封地数量",
        "stages": [
            {"stage": 1, "threshold": 3,  "rewards": [{"type": "item", "item_name": "私人货票", "quantity": 2}]},
            {"stage": 2, "threshold": 5,  "rewards": [{"type": "item", "item_name": "普通货票", "quantity": 2}]},
            {"stage": 3, "threshold": 8,  "rewards": [{"type": "item", "item_name": "官府货票", "quantity": 3}]},
            {"stage": 4, "threshold": 11, "rewards": [{"type": "item", "item_name": "吕氏货票", "quantity": 3}]},
            {"stage": 5, "threshold": 14, "rewards": [{"type": "item", "item_name": "范式货票", "quantity": 3}]},
            {"stage": 6, "threshold": 17, "rewards": [{"type": "item", "item_name": "内府货票", "quantity": 3}]},
            {"stage": 7, "threshold": 20, "rewards": [
                {"type": "item", "item_name": "王公货票", "quantity": 2},
                {"type": "item", "item_name": "内府货票", "quantity": 1},
            ]},
            {"stage": 8, "threshold": 22, "rewards": [
                {"type": "item", "item_name": "亲王货票", "quantity": 1},
                {"type": "item", "item_name": "王公货票", "quantity": 1},
            ]},
            {"stage": 9, "threshold": 24, "rewards": [
                {"type": "item", "item_name": "皇家货票", "quantity": 1},
                {"type": "item", "item_name": "亲王货票", "quantity": 1},
            ]},
        ],
    },
    "combat": {
        "name": "战斗",
        "description": "累计战斗积分",
        "stages": [
            {"stage": 1,  "threshold": 500,       "rewards": [{"type": "gold", "quantity": 100}]},
            {"stage": 2,  "threshold": 1200,      "rewards": [{"type": "gold", "quantity": 300}]},
            {"stage": 3,  "threshold": 3000,      "rewards": [{"type": "gold", "quantity": 500}]},
            {"stage": 4,  "threshold": 5000,      "rewards": [{"type": "gold", "quantity": 800}]},
            {"stage": 5,  "threshold": 20000,     "rewards": [{"type": "gold", "quantity": 1200}]},
            {"stage": 6,  "threshold": 50000,     "rewards": [{"type": "gold", "quantity": 2000}]},
            {"stage": 7,  "threshold": 100000,    "rewards": [{"type": "gold", "quantity": 3500}]},
            {"stage": 8,  "threshold": 500000,    "rewards": [{"type": "gold", "quantity": 6000}]},
            {"stage": 9,  "threshold": 1000000,   "rewards": [{"type": "gold", "quantity": 10000}]},
        ],
    },
    "city": {
        "name": "国家扩张",
        "description": "本国拥有的城池数量",
        "stages": [
            {"stage": 1,  "threshold": 5,    "rewards": [{"type": "gold", "quantity": 50}]},
            {"stage": 2,  "threshold": 7,    "rewards": [{"type": "gold", "quantity": 100}]},
            {"stage": 3,  "threshold": 10,   "rewards": [{"type": "gold", "quantity": 150}]},
            {"stage": 4,  "threshold": 15,   "rewards": [{"type": "gold", "quantity": 200}]},
            {"stage": 5,  "threshold": 21,   "rewards": [{"type": "gold", "quantity": 300}]},
            {"stage": 6,  "threshold": 35,   "rewards": [{"type": "gold", "quantity": 500}]},
            {"stage": 7,  "threshold": 50,   "rewards": [{"type": "gold", "quantity": 800}]},
            {"stage": 8,  "threshold": 68,   "rewards": [{"type": "gold", "quantity": 1000}]},
            {"stage": 9,  "threshold": 88,   "rewards": [{"type": "gold", "quantity": 1500}]},
            {"stage": 10, "threshold": 120,  "rewards": [{"type": "gold", "quantity": 2000}]},
            {"stage": 11, "threshold": 155,  "rewards": [{"type": "gold", "quantity": 3000}]},
            {"stage": 12, "threshold": 195,  "rewards": [{"type": "gold", "quantity": 5000}]},
            {"stage": 13, "threshold": 250,  "rewards": [{"type": "gold", "quantity": 6000}]},
            {"stage": 14, "threshold": 310,  "rewards": [{"type": "gold", "quantity": 8000}]},
            {"stage": 15, "threshold": 400,  "rewards": [{"type": "gold", "quantity": 10000}]},
            {"stage": 16, "threshold": 999,  "rewards": [{"type": "special", "special_name": "胜利之礼", "implemented": False}]},
        ],
    },
    "development": {
        "name": "发展",
        "description": "累计发展分",
        "stages": [
            {"stage": 1,  "threshold": 500,       "rewards": [{"type": "item", "item_name": "私人货票", "quantity": 2}]},
            {"stage": 2,  "threshold": 1500,      "rewards": [{"type": "item", "item_name": "普通货票", "quantity": 2}]},
            {"stage": 3,  "threshold": 3000,      "rewards": [{"type": "item", "item_name": "官府货票", "quantity": 3}]},
            {"stage": 4,  "threshold": 5000,      "rewards": [{"type": "item", "item_name": "吕氏货票", "quantity": 3}]},
            {"stage": 5,  "threshold": 10000,     "rewards": [{"type": "item", "item_name": "范式货票", "quantity": 3}]},
            {"stage": 6,  "threshold": 20000,     "rewards": [{"type": "item", "item_name": "内府货票", "quantity": 3}]},
            {"stage": 7,  "threshold": 50000,     "rewards": [
                {"type": "item", "item_name": "王公货票", "quantity": 2},
                {"type": "item", "item_name": "内府货票", "quantity": 1},
            ]},
            {"stage": 8,  "threshold": 100000,    "rewards": [
                {"type": "item", "item_name": "亲王货票", "quantity": 1},
                {"type": "item", "item_name": "王公货票", "quantity": 1},
            ]},
            {"stage": 9,  "threshold": 200000,    "rewards": [
                {"type": "item", "item_name": "皇家货票", "quantity": 1},
                {"type": "item", "item_name": "亲王货票", "quantity": 1},
            ]},
            {"stage": 10, "threshold": 350000,    "rewards": [{"type": "item", "item_name": "皇家货票", "quantity": 5}]},
            {"stage": 11, "threshold": 600000,    "rewards": [{"type": "item", "item_name": "皇家货票", "quantity": 10}]},
            {"stage": 12, "threshold": 1000000,   "rewards": [{"type": "item", "item_name": "皇家货票", "quantity": 15}]},
            {"stage": 13, "threshold": 2500000,   "rewards": [{"type": "item", "item_name": "皇家货票", "quantity": 20}]},
            {"stage": 14, "threshold": 5000000,   "rewards": [{"type": "item", "item_name": "皇家货票", "quantity": 30}]},
            {"stage": 15, "threshold": 10000000,  "rewards": [{"type": "item", "item_name": "皇家货票", "quantity": 50}]},
        ],
    },
}

# 每个等级对应的宝物套装（神兵 + 宝典 + 神器）
TREASURE_SET_MAP = {
    7:  ["鱼肠", "美芹十论", "吉光毛裘"],
    13: ["青龙偃月", "尉缭子", "马宝石"],
    20: ["轩辕夏禹", "遁甲天书", "伏羲琴"],
    25: ["龙舌", "握奇经", "九曲珠"],
    30: ["芦叶枪", "神器谱", "九黎壶"],
}

# 精炼套装（精炼后缀）
TREASURE_SET_REFINED_MAP = {
    25: ["龙舌（精炼）", "握奇经（精炼）", "九曲珠（精炼）"],
    30: ["芦叶枪（精炼）", "神器谱（精炼）", "九黎壶（精炼）"],
}
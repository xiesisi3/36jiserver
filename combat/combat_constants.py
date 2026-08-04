# 战斗系统常量定义

TECH_BONUS = 1.05
DEFENSE_HERO_BONUS = 1.05
HP_HERO_BONUS = 1.05

# 兵种克制关系
COUNTER_BONUS = {
    ("步兵系", "弓兵系"): 1.5,
    ("弓兵系", "骑兵系"): 1.5,
    ("骑兵系", "步兵系"): 1.5,
    ("步兵系", "骑兵系"): 0.75,
    ("弓兵系", "步兵系"): 0.75,
    ("骑兵系", "弓兵系"): 0.75,
}

# 相性 → 兵种系列的映射
PHASE_TO_SERIES = {
    "infantry_phase": "步兵系",
    "cavalry_phase": "骑兵系",
    "archer_phase": "弓兵系",
}

# 士气连击率表
MORALE_TO_DOUBLE_ATTACK_RATE = [
    (0, 0),
    (50, 3),
    (100, 8),
    (300, 15),
    (600, 30),
]

# 剿匪难度配置
ROBBER_DIFFICULTY_CONFIG = {
    "极易": {
        "general_name": "山贼",
        "force": 10,
        "intelligence": 10,
        "charisma": 10,
        "food": 10000,
        "team": [
            {"兵种名称": "轻步兵", "数量": 2},
            {"兵种名称": "轻骑兵", "数量": 2},
            {"兵种名称": "弓箭手", "数量": 2},
            {"兵种名称": "", "数量": 0},
            {"兵种名称": "运输兵", "数量": 2},
        ],
        "exp_mult": 0.5,
        "stability_factor": 1.0,
    },
    "简单": {
        "general_name": "山贼",
        "force": 20,
        "intelligence": 20,
        "charisma": 50,
        "food": 25000,
        "team": [
            {"兵种名称": "轻步兵", "数量": 10},
            {"兵种名称": "轻骑兵", "数量": 20},
            {"兵种名称": "弓箭手", "数量": 10},
            {"兵种名称": "", "数量": 0},
            {"兵种名称": "运输兵", "数量": 10},
        ],
        "exp_mult": 0.8,
        "stability_factor": 1.2,
    },
    "普通": {
        "general_name": "山贼",
        "force": 40,
        "intelligence": 30,
        "charisma": 20,
        "food": 50000,
        "team": [
            {"兵种名称": "轻步兵", "数量": 20},
            {"兵种名称": "轻骑兵", "数量": 20},
            {"兵种名称": "弓箭手", "数量": 40},
            {"兵种名称": "", "数量": 0},
            {"兵种名称": "运输兵", "数量": 20},
        ],
        "exp_mult": 1.0,
        "stability_factor": 1.5,
    },
    "困难": {
        "general_name": "山贼",
        "force": 20,
        "intelligence": 45,
        "charisma": 60,
        "food": 60000,
        "team": [
            {"兵种名称": "轻步兵", "数量": 50},
            {"兵种名称": "轻骑兵", "数量": 50},
            {"兵种名称": "弓箭手", "数量": 50},
            {"兵种名称": "", "数量": 0},
            {"兵种名称": "运输兵", "数量": 20},
        ],
        "exp_mult": 1.5,
        "stability_factor": 2.0,
    },
    "极难": {
        "general_name": "山贼",
        "force": 80,
        "intelligence": 60,
        "charisma": 40,
        "food": 110000,
        "team": [
            {"兵种名称": "轻步兵", "数量": 120},
            {"兵种名称": "轻骑兵", "数量": 40},
            {"兵种名称": "弓箭手", "数量": 40},
            {"兵种名称": "", "数量": 0},
            {"兵种名称": "运输兵", "数量": 40},
        ],
        "exp_mult": 2.0,
        "stability_factor": 2.5,
    },
}

# 剿匪每日次数上限
ROBBER_DAILY_LIMIT = 100

# 黄金剿匪消耗
ROBBER_GOLD_COST = 8

# 黄金剿匪经验加成
ROBBER_GOLD_EXP_BONUS = 1.2
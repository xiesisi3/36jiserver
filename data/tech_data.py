TECH_CONFIG = {
    "世卿世禄": {
        "key": "世卿世禄",
        "max_level": 20,
        "cost_formula": "arithmetic",
        "cost_base": 100,
        "base_limit": 5,
        "limit_per_level": 1,
        "effect_desc": "武将数量上限",
        "category": "limit",
    },
    "列土封疆": {
        "key": "列土封疆",
        "max_level": 23,
        "cost_formula": "arithmetic",
        "cost_base": 1000,
        "base_limit": 1,
        "limit_per_level": 1,
        "effect_desc": "封地数量上限",
        "category": "limit",
    },
    "木牛流马": {
        "key": "木牛流马",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "兵种可携带粮食上限+5%/级",
        "category": "battle",
        "not_implemented": True,
    },
    "武刚军阵": {
        "key": "武刚军阵",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "步兵系攻击力+5%/级",
        "category": "battle",
        "troop_series": "步兵系",
        "bonus_type": "attack",
        "bonus_per_level": 0.05,
    },
    "胡服骑射": {
        "key": "胡服骑射",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "弓兵系攻击力+5%/级",
        "category": "battle",
        "troop_series": "弓兵系",
        "bonus_type": "attack",
        "bonus_per_level": 0.05,
    },
    "风林火山": {
        "key": "风林火山",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "骑兵系攻击力+5%/级",
        "category": "battle",
        "troop_series": "骑兵系",
        "bonus_type": "attack",
        "bonus_per_level": 0.05,
    },
    "步兵协战": {
        "key": "步兵协战",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "步兵系连击概率+1%/级",
        "category": "battle",
        "troop_series": "步兵系",
        "bonus_type": "combo",
        "bonus_per_level": 0.01,
    },
    "弓兵协战": {
        "key": "弓兵协战",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "弓兵系连击概率+1%/级",
        "category": "battle",
        "troop_series": "弓兵系",
        "bonus_type": "combo",
        "bonus_per_level": 0.01,
    },
    "骑兵协战": {
        "key": "骑兵协战",
        "max_level": 20,
        "cost_formula": "fibonacci",
        "cost_base": 5000,
        "cost_base2": 8000,
        "effect_desc": "骑兵系连击概率+1%/级",
        "category": "battle",
        "troop_series": "骑兵系",
        "bonus_type": "combo",
        "bonus_per_level": 0.01,
    },
}

TECH_TYPES = list(TECH_CONFIG.keys())


def calc_arithmetic_cost(level, base):
    """等差数列递增消耗: cost[n] = base * (1 + n*(n-1)/2)"""
    return int(base * (1 + level * (level - 1) / 2))


def calc_fibonacci_cost(level, base1, base2):
    """斐波那契式消耗: 1级base1, 2级base2, 后续cost[n]=cost[n-1]+cost[n-2]"""
    if level <= 0:
        return 0
    if level == 1:
        return base1
    if level == 2:
        return base2
    a, b = base1, base2
    for _ in range(3, level + 1):
        a, b = b, a + b
    return b


def get_tech_cost(tech_type, level):
    """计算科技指定等级升级所需的铜币"""
    config = TECH_CONFIG.get(tech_type)
    if not config:
        return 0
    if level <= 0 or level > config["max_level"]:
        return 0
    formula = config["cost_formula"]
    if formula == "arithmetic":
        return calc_arithmetic_cost(level, config["cost_base"])
    elif formula == "fibonacci":
        return calc_fibonacci_cost(level, config["cost_base"], config["cost_base2"])
    return 0


SERIES_TO_ATTACK_TECH = {
    "步兵系": "武刚军阵",
    "弓兵系": "胡服骑射",
    "骑兵系": "风林火山",
}

SERIES_TO_COMBO_TECH = {
    "步兵系": "步兵协战",
    "弓兵系": "弓兵协战",
    "骑兵系": "骑兵协战",
}
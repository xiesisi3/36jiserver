TOWN_ATTR_EFFECTS = [
    {
        "min": 0, "max": 9999,
        "stability": {"name": "颠沛流离", "effect": "铜币产量+10%"},
        "defense": {"name": "断瓦残垣", "attack_bonus": 0.03, "defense_bonus": 0.02},
        "traffic": {"name": "焦土栈道", "speed_multiplier": 0.65}
    },
    {
        "min": 10000, "max": 19999,
        "stability": {"name": "流离失所", "effect": "铜币产量+20%"},
        "defense": {"name": "千疮百孔", "attack_bonus": 0.06, "defense_bonus": 0.04},
        "traffic": {"name": "崎岖山路", "speed_multiplier": 0.80}
    },
    {
        "min": 20000, "max": 29999,
        "stability": {"name": "动荡不安", "effect": "铜币产量+30%"},
        "defense": {"name": "年久失修", "attack_bonus": 0.09, "defense_bonus": 0.06},
        "traffic": {"name": "泥泞小径", "speed_multiplier": 0.95}
    },
    {
        "min": 30000, "max": 39999,
        "stability": {"name": "兵荒马乱", "effect": "铜币产量+40%"},
        "defense": {"name": "残破不全", "attack_bonus": 0.12, "defense_bonus": 0.08},
        "traffic": {"name": "羊肠小道", "speed_multiplier": 1.10}
    },
    {
        "min": 40000, "max": 49999,
        "stability": {"name": "鸡犬不宁", "effect": "铜币产量+50%"},
        "defense": {"name": "百废待兴", "attack_bonus": 0.15, "defense_bonus": 0.10},
        "traffic": {"name": "平坦大道", "speed_multiplier": 1.25}
    },
    {
        "min": 50000, "max": 59999,
        "stability": {"name": "普普通通", "effect": "铜币产量+60%"},
        "defense": {"name": "修葺一新", "attack_bonus": 0.18, "defense_bonus": 0.12},
        "traffic": {"name": "康庄大道", "speed_multiplier": 1.40}
    },
    {
        "min": 60000, "max": 69999,
        "stability": {"name": "安居乐业", "effect": "铜币产量+70%"},
        "defense": {"name": "固若金汤", "attack_bonus": 0.21, "defense_bonus": 0.14},
        "traffic": {"name": "通衢大道", "speed_multiplier": 1.55}
    },
    {
        "min": 70000, "max": 79999,
        "stability": {"name": "太平盛世", "effect": "铜币产量+80%"},
        "defense": {"name": "牢不可破", "attack_bonus": 0.24, "defense_bonus": 0.16},
        "traffic": {"name": "四通八达", "speed_multiplier": 1.70}
    },
    {
        "min": 80000, "max": 89999,
        "stability": {"name": "夜不闭户", "effect": "铜币产量+90%"},
        "defense": {"name": "铜墙铁壁", "attack_bonus": 0.27, "defense_bonus": 0.18},
        "traffic": {"name": "畅通无阻", "speed_multiplier": 1.85}
    },
    {
        "min": 90000, "max": 100000,
        "stability": {"name": "国泰民安", "effect": "铜币产量+100%"},
        "defense": {"name": "坚如磐石", "attack_bonus": 0.30, "defense_bonus": 0.20},
        "traffic": {"name": "皇家大道", "speed_multiplier": 2.00}
    }
]


# ============================================================
# 民兵（义勇军/连弩）生成配置
# ============================================================
# 当城池发生战斗时，民心(popular_support)会转化为民兵部队参与防御。
# - 义勇军: 每1000民心生成3支，每支500人（每槽100人），最多30支
# - 连弩:   超过10000民心后，每1000民心生成2支，每支150人（每槽30人），无上限
# 两种部队同时存在，义勇军使用山贼武将ID 10002，连弩使用山贼武将ID 10005
# 归属user_id="0"但通过_nation字段标记为城池所属国家，仅防御方生成。
# 战斗结束后民兵部队全部销毁。

MILITIA_VOLUNTEER_GENERAL_ID = 10002
MILITIA_CROSSBOW_GENERAL_ID = 10005
MILITIA_DEFAULT_GRID_X = 10
MILITIA_DEFAULT_GRID_Y = 9

MILITIA_VOLUNTEER = {
    "troop_name": "义勇军",
    "per_slot": 100,
    "slots": 5,
    "per_1000": 3,
    "max": 30,
}

MILITIA_CROSSBOW = {
    "troop_name": "连弩",
    "per_slot": 30,
    "slots": 5,
    "per_1000": 2,
    "max": None,
    "min_popular_support": 10000,
}


def generate_militia_config(popular_support):
    """
    根据民心值计算需要生成的民兵部队配置列表。

    义勇军: 每1000民心 → 3支（最多30支，即10000民心达到上限）
    连弩:   超过10000民心后，每1000民心 → 2支，无上限

    返回: [{"troop_name": "义勇军", "count": N, "per_slot": 100, "slots": 5}, ...]
    """
    if popular_support <= 0:
        return []

    configs = []

    volunteer_count = min(MILITIA_VOLUNTEER["max"], (popular_support // 1000) * MILITIA_VOLUNTEER["per_1000"])
    if volunteer_count > 0:
        configs.append({
            "troop_name": MILITIA_VOLUNTEER["troop_name"],
            "count": volunteer_count,
            "per_slot": MILITIA_VOLUNTEER["per_slot"],
            "slots": MILITIA_VOLUNTEER["slots"],
        })

    excess = popular_support - MILITIA_CROSSBOW["min_popular_support"]
    if excess > 0:
        crossbow_count = (excess // 1000) * MILITIA_CROSSBOW["per_1000"]
        if crossbow_count > 0:
            configs.append({
                "troop_name": MILITIA_CROSSBOW["troop_name"],
                "count": crossbow_count,
                "per_slot": MILITIA_CROSSBOW["per_slot"],
                "slots": MILITIA_CROSSBOW["slots"],
            })

    return configs
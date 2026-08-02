import random

PHASE_NUM_TO_STR = {
    0: None,
    1: "D",
    2: "C",
    3: "B",
    4: "A",
    5: "S",
    6: "SS",
    7: "SSS",
    8: "SSSR",
}

PHASE_STR_TO_NUM = {v: k for k, v in PHASE_NUM_TO_STR.items() if v is not None}


def random_phase():
    return random.randint(0, 3)


def phase2str(phase_num):
    return PHASE_NUM_TO_STR.get(phase_num, None)


def str2phase(phase_str):
    return PHASE_STR_TO_NUM.get(phase_str, 0)


def hero_panel_to_general(hero_panel, user_id):
    if not hero_panel or not isinstance(user_id, (int, str)):
        return None

    insert_data = {
        "user_id": str(user_id),
        "hero_name": hero_panel.get("英雄名称", "未知武将"),
        "level_initial": 1,
        "level": 1,
        "force_initial": int(hero_panel.get("武力（初始）", 20)),
        "intelligence_initial": int(hero_panel.get("智力（初始）", 20)),
        "charisma_initial": int(hero_panel.get("魅力（初始）", 20)),
        "force": int(hero_panel.get("武力（初始）", 20)),
        "intelligence": int(hero_panel.get("智力（初始）", 20)),
        "charisma": int(hero_panel.get("魅力（初始）", 20)),
        "infantry_phase_initial": str2phase(hero_panel.get("步兵相性（初始）", "")),
        "cavalry_phase_initial": str2phase(hero_panel.get("骑兵相性（初始）", "")),
        "archer_phase_initial": str2phase(hero_panel.get("弓兵相性（初始）", "")),
        "governance_phase_initial": str2phase(hero_panel.get("内政相性（初始）", "")),
        "infantry_phase": str2phase(hero_panel.get("步兵相性（初始）", "")),
        "cavalry_phase": str2phase(hero_panel.get("骑兵相性（初始）", "")),
        "archer_phase": str2phase(hero_panel.get("弓兵相性（初始）", "")),
        "governance_phase": str2phase(hero_panel.get("内政相性（初始）", "")),
        "morale": 100,
        "personality": hero_panel.get("性格"),
        "wisdom": int(hero_panel.get("悟性", 0)),
        "exp": 0,
        "skill_points": 0,
        "talent_ygzq": 0,
        "talent_ygsj": 0,
        "talent_djzc": 0,
        "talent_tqtb": 0,
        "talent_skill": 0,
        "exp_bonus": 0.0,
        "attack_bonus": 0.0,
        "defense_bonus": 0.0,
        "hp_bonus": 0.0,
        "morale_bonus": 0.0,
        "combo_rate": 0.0,
        "skill_name": hero_panel.get("技能"),
        "skill_desc": hero_panel.get("技能说明"),
        "status": 0,
        "pos": None,
        "dest": None,
        "death_time": None,
    }
    return insert_data


INITIAL_GENERAL_PANEL = {
    "英雄名称": "",
    "性格": "睿智",
    "武力（初始）": 50,
    "智力（初始）": 50,
    "魅力（初始）": 50,
    "技能": "无",
    "技能说明": "无技能说明",
    "步兵相性（初始）": "B",
    "骑兵相性（初始）": "B",
    "弓兵相性（初始）": "B",
    "内政相性（初始）": "B",
    "悟性": 100,
}


BANDIT_HERO_PANELS = {
    10001: {
        "id": 10001,
        "英雄名称": "山贼低级将领",
        "性格": "鲁莽",
        "武力（初始）": 20,
        "智力（初始）": 20,
        "魅力（初始）": 20,
        "技能": "无",
        "技能说明": "无技能",
        "步兵相性（初始）": "D",
        "骑兵相性（初始）": "D",
        "弓兵相性（初始）": "D",
        "内政相性（初始）": "D",
    },
    10002: {
        "id": 10002,
        "英雄名称": "山贼低级将领",
        "性格": "鲁莽",
        "武力（初始）": 30,
        "智力（初始）": 30,
        "魅力（初始）": 30,
        "技能": "无",
        "技能说明": "无技能",
        "步兵相性（初始）": "C",
        "骑兵相性（初始）": "C",
        "弓兵相性（初始）": "C",
        "内政相性（初始）": "C",
    },
    10003: {
        "id": 10003,
        "英雄名称": "山贼高级将领",
        "性格": "鲁莽",
        "武力（初始）": 45,
        "智力（初始）": 45,
        "魅力（初始）": 45,
        "技能": "无",
        "技能说明": "无技能",
        "步兵相性（初始）": "B",
        "骑兵相性（初始）": "B",
        "弓兵相性（初始）": "B",
        "内政相性（初始）": "B",
    },
    10004: {
        "id": 10004,
        "英雄名称": "山贼高级将领",
        "性格": "鲁莽",
        "武力（初始）": 60,
        "智力（初始）": 60,
        "魅力（初始）": 60,
        "技能": "无",
        "技能说明": "无技能",
        "步兵相性（初始）": "A",
        "骑兵相性（初始）": "A",
        "弓兵相性（初始）": "A",
        "内政相性（初始）": "A",
    },
    10005: {
        "id": 10005,
        "英雄名称": "山贼高级将领",
        "性格": "鲁莽",
        "武力（初始）": 80,
        "智力（初始）": 80,
        "魅力（初始）": 80,
        "技能": "无",
        "技能说明": "无技能",
        "步兵相性（初始）": "S",
        "骑兵相性（初始）": "S",
        "弓兵相性（初始）": "S",
        "内政相性（初始）": "S",
    },
}

BANDIT_HERO_TEMPLATES = {}
for _panel_id, _panel in BANDIT_HERO_PANELS.items():
    _general = hero_panel_to_general(_panel, 0)
    if _general:
        _general["id"] = -_panel_id
        _general["status"] = 1
        BANDIT_HERO_TEMPLATES[-_panel_id] = _general


def get_general_info(general_id):
    """统一获取武将信息
    general_id > 0: 玩家武将，从 generals_cache 查询
    general_id < 0: 山贼模板武将，从 BANDIT_HERO_TEMPLATES 查询
    """
    if general_id is None:
        return None
    if general_id < 0:
        return BANDIT_HERO_TEMPLATES.get(general_id)
    if general_id > 0:
        from data.global_data import generals_cache
        for _user_id, general_list in generals_cache.items():
            for g in general_list:
                if g.get("id") == general_id:
                    return g
    return None
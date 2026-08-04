import random
import logging

from data.hero_data import HEROES
from data.global_data import generals_cache
from general.general_db import get_generals_by_user
from general.general_utils import random_phase

logger = logging.getLogger('36ji-server')

# 百家姓（用于随机武将姓名生成）
BAIXINGJIA = [
    "赵", "钱", "孙", "李", "周", "吴", "郑", "王", "冯", "陈",
    "褚", "卫", "蒋", "沈", "韩", "杨", "朱", "秦", "尤", "许",
    "何", "吕", "施", "张", "孔", "曹", "严", "华", "金", "魏",
    "陶", "姜", "戚", "谢", "邹", "喻", "柏", "水", "窦", "章",
    "云", "苏", "潘", "葛", "奚", "范", "彭", "郎", "鲁", "韦",
    "昌", "马", "苗", "凤", "花", "方", "俞", "任", "袁", "柳",
    "酆", "鲍", "史", "唐", "费", "廉", "岑", "薛", "雷", "贺",
    "倪", "汤", "滕", "殷", "罗", "毕", "郝", "邬", "安", "常",
    "乐", "于", "时", "傅", "皮", "卞", "齐", "康", "伍", "余",
    "元", "卜", "顾", "孟", "平", "黄", "和", "穆", "萧", "尹",
    "姚", "邵", "湛", "汪", "祁", "毛", "禹", "狄", "米", "贝",
    "明", "臧", "计", "伏", "成", "戴", "谈", "宋", "茅", "庞",
    "熊", "纪", "舒", "屈", "项", "祝", "董", "梁", "杜", "阮",
    "蓝", "闵", "席", "季", "麻", "强", "贾", "路", "娄", "危",
    "江", "童", "颜", "郭", "梅", "盛", "林", "刁", "钟", "徐",
    "邱", "骆", "高", "夏", "蔡", "田", "樊", "胡", "凌", "霍",
    "虞", "万", "支", "柯", "昝", "管", "卢", "莫", "经", "房",
    "裘", "缪", "干", "解", "应", "宗", "丁", "宣", "贲", "邓",
    "郁", "单", "杭", "洪", "包", "诸", "左", "石", "崔", "吉",
    "钮", "龚", "程", "嵇", "邢", "滑", "裴", "陆", "荣", "翁",
    "荀", "羊", "於", "惠", "甄", "麴", "家", "封", "芮", "羿",
    "储", "靳", "汲", "邴", "糜", "松", "井", "段", "富", "巫",
    "乌", "焦", "巴", "弓", "牧", "隗", "山", "谷", "车", "侯",
    "宓", "蓬", "全", "郗", "班", "仰", "秋", "仲", "伊", "宫",
    "宁", "仇", "栾", "暴", "甘", "钭", "厉", "戎", "祖", "武",
    "符", "刘", "景", "詹", "束", "龙", "叶", "幸", "司", "韶",
    "郜", "黎", "蓟", "薄", "印", "宿", "白", "怀", "蒲", "邰",
    "从", "鄂", "索", "咸", "籍", "赖", "卓", "蔺", "屠", "蒙",
    "池", "乔", "阴", "鬱", "胥", "能", "苍", "双", "闻", "莘",
    "党", "翟", "谭", "贡", "劳", "逄", "姬", "申", "扶", "堵",
    "冉", "宰", "郦", "雍", "卻", "璩", "桑", "桂", "濮", "牛",
    "寿", "通", "边", "扈", "燕", "冀", "郏", "浦", "尚", "农",
    "温", "别", "庄", "晏", "柴", "瞿", "阎", "充", "慕", "连",
    "茹", "习", "宦", "艾", "鱼", "容", "向", "古", "易", "慎",
    "戈", "廖", "庾", "终", "暨", "居", "衡", "步", "都", "耿",
    "满", "弘", "匡", "国", "文", "寇", "广", "禄", "阙", "东",
    "欧", "殳", "沃", "利", "蔚", "越", "夔", "隆", "师", "巩",
    "厍", "聂", "晁", "勾", "敖", "融", "冷", "訾", "辛", "阚",
    "那", "简", "饶", "空", "曾", "毋", "沙", "乜", "养", "鞠",
    "须", "丰", "巢", "关", "蒯", "相", "查", "后", "荆", "红",
    "游", "竺", "权", "逯", "盖", "益", "桓", "公", "万俟", "司马",
    "上官", "欧阳", "夏侯", "诸葛", "闻人", "东方", "赫连", "皇甫", "尉迟", "公羊",
    "澹台", "公冶", "宗政", "濮阳", "淳于", "单于", "太叔", "申屠", "公孙", "仲孙",
    "轩辕", "令狐", "钟离", "宇文", "长孙", "慕容", "鲜于", "闾丘", "司徒", "司空",
    "丌官", "司寇", "仉", "督", "子车", "颛孙", "端木", "巫马", "公西", "漆雕",
    "乐正", "壤驷", "公良", "拓跋", "夹谷", "宰父", "谷梁", "晋", "楚", "闫",
    "法", "汝", "鄢", "涂", "钦", "段干", "百里", "东郭", "南门", "呼延",
    "归", "海", "羊舌", "微生", "岳", "帅", "缑", "亢", "况", "后",
    "有", "琴", "梁丘", "左丘", "东门", "西门", "商", "牟", "佘", "佴",
    "伯", "赏", "南宫", "墨", "哈", "谯", "笪", "年", "爱", "阳",
    "佟", "第五", "言", "福",
]

# 随机名字用字（100个常见汉字）
RANDOM_NAMES = [
    "勇", "谋", "睿", "杰", "豪", "强", "毅", "辉", "鹏", "彬",
    "轩", "泽", "宇", "辰", "朗", "峻", "谦", "恒", "明", "达",
    "诚", "信", "仁", "义", "礼", "智", "忠", "孝", "廉", "节",
    "刚", "柔", "文", "武", "威", "猛", "烈", "雄", "英", "俊",
    "才", "能", "贤", "良", "善", "美", "乐", "安", "康", "宁",
    "兴", "盛", "昌", "荣", "华", "富", "贵", "福", "禄", "寿",
    "喜", "庆", "贺", "祥", "瑞", "麟", "凤", "龙", "虎", "豹",
    "鹰", "鸿", "鹤", "松", "柏", "梅", "兰", "竹", "菊", "莲",
    "山", "河", "江", "海", "湖", "泽", "林", "森", "峰", "岭",
    "云", "雷", "电", "风", "霜", "雪", "雨", "露", "冰", "火",
]

# 性格池（每项对应一种属性加成描述）
PERSONALITY_NAMES = [
    "勇敢", "睿智", "明媚", "豪迈", "缜密",
    "稳重", "机敏", "洒脱", "果敢", "坚毅",
]

PERSONALITY_BONUS = {
    "勇敢": {"force": 3, "intelligence": 0, "charisma": 0},
    "睿智": {"force": 0, "intelligence": 3, "charisma": 0},
    "明媚": {"force": 0, "intelligence": 0, "charisma": 3},
    "豪迈": {"force": 2, "intelligence": 1, "charisma": 0},
    "缜密": {"force": 0, "intelligence": 2, "charisma": 1},
    "稳重": {"force": 1, "intelligence": 1, "charisma": 1},
    "机敏": {"force": 1, "intelligence": 2, "charisma": 0},
    "洒脱": {"force": 0, "intelligence": 1, "charisma": 2},
    "果敢": {"force": 1, "intelligence": 0, "charisma": 2},
    "坚毅": {"force": 2, "intelligence": 0, "charisma": 1},
}

OLD_PERSONALITY_MAP = {
    "武力+3": "勇敢",
    "智力+3": "睿智",
    "魅力+3": "明媚",
    "武力+2智力+1": "豪迈",
    "武力+2魅力+1": "坚毅",
    "智力+2武力+1": "机敏",
    "智力+2魅力+1": "缜密",
    "魅力+2武力+1": "果敢",
    "魅力+2智力+1": "洒脱",
    "武力+1智力+1魅力+1": "稳重",
}

def _resolve_personality(raw):
    if not raw:
        return "睿智"
    if raw in PERSONALITY_BONUS:
        return raw
    return OLD_PERSONALITY_MAP.get(raw, "睿智")

MAX_LEVEL = 40

TALENT_NAMES = ["一鼓作气", "勇冠三军", "大将之材", "铜墙铁壁"]

TALENT_COSTS = {1: 2, 2: 3, 3: 4}

TALENT_MAX_LEVEL = 3

TALENT_BONUSES = {
    "一鼓作气": {1: 1, 2: 2, 3: 3},
    "勇冠三军": {1: 0.05, 2: 0.15, 3: 0.30},
    "大将之材": {1: 200, 2: 500, 3: 1200},
    "铜墙铁壁": {1: 3, 2: 4, 3: 5},
}

TALENT_DB_FIELDS = {
    "一鼓作气": "talent_ygzq",
    "勇冠三军": "talent_ygsj",
    "大将之材": "talent_djzc",
    "铜墙铁壁": "talent_tqtb",
}

# 状态映射
STATUS_MAP = {
    0: "未编组",
    1: "驻守",
    2: "行军中",
    3: "战斗中",
    4: "死亡等待复活",
}

# 复活等待时间（秒）
RESURRECTION_SECONDS = 8 * 3600


# 固定英雄名称集合（模块加载时从 HEROES 提取，用于重名检查）
_FIXED_HERO_NAMES = {h["hero_name"] for h in HEROES}


def _generate_random_hero_name(excluded_names=None):
    """生成三字随机武将姓名，不与排除列表中的名称重复
    :param excluded_names: 需要排除的名称集合（set），如固定英雄名 + 玩家已有武将名
    :return: 不重复的随机武将姓名
    """
    if excluded_names is None:
        excluded_names = set()
    surname = random.choice(BAIXINGJIA)
    name1 = random.choice(RANDOM_NAMES)
    name2 = random.choice(RANDOM_NAMES)
    return f"{surname}{name1}{name2}"


def _random_character():
    return random.choice(PERSONALITY_NAMES)


def draw_fixed_hero(user_id=None):
    """
    从固定英雄池中等概率随机抽取一个英雄（排除玩家已拥有的）
    :param user_id: 可选，玩家用户ID，用于排除该玩家已有的固定英雄
    :return: 英雄数据字典（与 HEROES 列表中的格式一致），全部已拥有时返回 None
    """
    if not HEROES:
        logger.warning("固定英雄池为空，无法抽取")
        return None

    if user_id and user_id in generals_cache:
        owned_names = {g["hero_name"] for g in generals_cache[user_id] if g.get("hero_name")}
        available = [h for h in HEROES if h["hero_name"] not in owned_names]
    else:
        available = HEROES

    if not available:
        return None
    return random.choice(available).copy()


def generate_random_general(user_id=None):
    """
    生成一个随机武将（非固定英雄，属性固定 + 随机姓名/性格/相性）
    自动排除固定英雄名和玩家已有武将名，确保不重名
    :param user_id: 可选，玩家用户ID，用于排除该玩家已有武将名
    :return: 武将数据字典
    """
    excluded_names = set(_FIXED_HERO_NAMES)
    if user_id and user_id in generals_cache:
        for g in generals_cache[user_id]:
            name = g.get("hero_name")
            if name:
                excluded_names.add(name)

    name = _generate_random_hero_name()
    while name in excluded_names:
        name = _generate_random_hero_name()

    return {
        "hero_name": name,
        "level_initial": 1,
        "force_initial": 20,
        "intelligence_initial": 20,
        "charisma_initial": 20,
        "infantry_phase_initial": random_phase(),
        "cavalry_phase_initial": random_phase(),
        "archer_phase_initial": random_phase(),
        "governance_phase_initial": random_phase(),
        "personality": _random_character(),
        "wisdom": 50,
        "skill_name": "无",
        "skill_desc": "无技能",
    }


def hero_panel_to_db_format(panel, user_id):
    """
    将英雄面板数据（来自 draw_fixed_hero 或 generate_random_general）
    转换为数据库插入格式的字典
    :param panel: 英雄面板字典
    :param user_id: 归属用户ID
    :return: 数据库插入格式的字典
    """
    return {
        "user_id": user_id,
        "hero_name": panel["hero_name"],
        "level_initial": panel["level_initial"],
        "level": panel["level_initial"],
        "force_initial": panel["force_initial"],
        "intelligence_initial": panel["intelligence_initial"],
        "charisma_initial": panel["charisma_initial"],
        "force": panel["force_initial"],
        "intelligence": panel["intelligence_initial"],
        "charisma": panel["charisma_initial"],
        "infantry_phase_initial": panel["infantry_phase_initial"],
        "cavalry_phase_initial": panel["cavalry_phase_initial"],
        "archer_phase_initial": panel["archer_phase_initial"],
        "governance_phase_initial": panel["governance_phase_initial"],
        "infantry_phase": panel["infantry_phase_initial"],
        "cavalry_phase": panel["cavalry_phase_initial"],
        "archer_phase": panel["archer_phase_initial"],
        "governance_phase": panel["governance_phase_initial"],
        "morale": 100,
        "personality": panel.get("personality"),
        "wisdom": panel.get("wisdom", 0),
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
        "skill_name": panel.get("skill_name"),
        "skill_desc": panel.get("skill_desc"),
        "status": 0,
        "pos": None,
        "dest": None,
        "death_time": None,
    }


def calc_exp_for_level(level):
    """
    计算升级所需经验
    公式：160 × level² - 160 × level + 100
    :param level: 当前等级（整数，最低为1）
    :return: 升级所需经验值
    """
    if not isinstance(level, int) or level < 1:
        return 0
    return 160 * (level ** 2) - 160 * level + 100


def calc_level_up(initial_level, gained_exp, current_exp):
    """
    根据初始等级、获得的经验值和当前经验值，计算升级后的等级和剩余经验
    :param initial_level: 当前等级（整数，最低为1）
    :param gained_exp: 获得的经验值（非负整数）
    :param current_exp: 当前经验值（非负整数）
    :return: (最终等级, 升级后剩余经验值)
    """
    if not isinstance(initial_level, int) or initial_level < 1:
        logger.warning(f"[calc_level_up] 非法initial_level: type={type(initial_level)}, value={initial_level}, 返回(0,0)")
        return 0, 0
    gained_exp = int(gained_exp)
    if gained_exp < 0:
        logger.warning(f"[calc_level_up] gained_exp为负数: {gained_exp}, 返回(0,0)")
        return 0, 0
    if not isinstance(current_exp, int) or current_exp < 0:
        logger.warning(f"[calc_level_up] 非法current_exp: type={type(current_exp)}, value={current_exp}, 返回(0,0)")
        return 0, 0

    current_level = initial_level
    total_exp = current_exp + gained_exp

    while current_level < MAX_LEVEL:
        exp_needed = calc_exp_for_level(current_level)
        if total_exp >= exp_needed:
            total_exp -= exp_needed
            current_level += 1
        else:
            break

    if current_level >= MAX_LEVEL:
        total_exp = 0

    return current_level, total_exp


def add_exp(general, gained_exp, use_wisdom=True):
    """
    给武将增加经验，自动处理升级，返回变化信息
    1-30级：每级1技能点+性格加成（共29次），31级起不再给技能点和性格加成
    30-40级：每级1天赋点（共11点）
    :param general: 武将数据字典（会直接修改）
    :param gained_exp: 获得的经验值
    :param use_wisdom: 是否应用悟性加成，默认True（战斗/剿匪等），道具使用时应传False
    :return: {"leveled_up": bool, "new_level": int, "new_exp": int, "levels_gained": int,
              "updates": dict}  updates 可直接传给 update_general
    """
    old_level = general.get("level", 1)
    current_exp = general.get("exp", 0)

    if use_wisdom:
        wisdom = general.get("wisdom", 0)
        if wisdom > 0:
            gained_exp = int(gained_exp * wisdom / 100)

    new_level, remaining_exp = calc_level_up(old_level, gained_exp, current_exp)

    general["level"] = new_level
    general["exp"] = remaining_exp

    levels_gained = new_level - old_level

    updates = {
        "level": new_level,
        "exp": remaining_exp,
    }

    if levels_gained > 0:
        skill_start = max(old_level + 1, 2)
        skill_end = min(new_level, 30)
        skill_points_gained = max(0, skill_end - skill_start + 1)

        talent_start = max(old_level + 1, 30)
        talent_end = min(new_level, MAX_LEVEL)
        talent_points_gained = max(0, talent_end - talent_start + 1)

        if skill_points_gained > 0:
            general["skill_points"] = general.get("skill_points", 0) + skill_points_gained
            updates["skill_points"] = general["skill_points"]

            raw_personality = general.get("personality", "")
            personality = _resolve_personality(raw_personality)
            bonus = PERSONALITY_BONUS.get(personality, {})
            if bonus:
                bonus_force = bonus.get("force", 0) * skill_points_gained
                bonus_intelligence = bonus.get("intelligence", 0) * skill_points_gained
                bonus_charisma = bonus.get("charisma", 0) * skill_points_gained

                if bonus_force:
                    general["force"] = general.get("force", 0) + bonus_force
                if bonus_intelligence:
                    general["intelligence"] = general.get("intelligence", 0) + bonus_intelligence
                if bonus_charisma:
                    general["charisma"] = general.get("charisma", 0) + bonus_charisma

                updates["force"] = general["force"]
                updates["intelligence"] = general["intelligence"]
                updates["charisma"] = general["charisma"]

        if talent_points_gained > 0:
            general["talent_skill"] = general.get("talent_skill", 0) + talent_points_gained
            updates["talent_skill"] = general["talent_skill"]

    return {
        "leveled_up": levels_gained > 0,
        "new_level": new_level,
        "new_exp": remaining_exp,
        "levels_gained": levels_gained,
        "updates": updates,
    }


def add_attribute_point(general, attrs):
    """
    消耗技能点，为武将增加属性点（可同时增加多个属性）
    注意：仅修改当前属性（force/intelligence/charisma），不修改初始属性（_initial），
    洗髓丹等重置道具依赖 _initial 保持为 level 1 原始值。
    :param general: 武将数据字典（会直接修改）
    :param attrs: 属性分配字典，如 {"force": 2, "intelligence": 1}
    :return: (success, message)
    """
    attr_map = {
        "force": "force",
        "intelligence": "intelligence",
        "charisma": "charisma",
    }

    if not isinstance(attrs, dict) or not attrs:
        return False, "请指定要增加的属性"

    total_points = 0
    for attr_name, count in attrs.items():
        if attr_name not in attr_map:
            return False, f"不支持的属性名: {attr_name}"
        if not isinstance(count, int) or count <= 0:
            return False, f"属性 {attr_name} 的点数必须为正整数"
        total_points += count

    skill_points = general.get("skill_points", 0)
    if skill_points < total_points:
        return False, f"技能点不足，需要{total_points}点，当前{skill_points}点"

    for attr_name, count in attrs.items():
        current_attr = attr_map[attr_name]
        general[current_attr] = general.get(current_attr, 0) + count

    general["skill_points"] = skill_points - total_points

    return True, "加点成功"


def upgrade_talent(general, talent_name):
    """
    消耗天赋点，升级武将天赋
    :param general: 武将数据字典（会直接修改）
    :param talent_name: 天赋名（一鼓作气/勇冠三军/大将之材/铜墙铁壁）
    :return: (success, message, updates)  updates 可直接传给 update_general
    """
    if talent_name not in TALENT_DB_FIELDS:
        return False, f"不存在的天赋: {talent_name}", {}

    db_field = TALENT_DB_FIELDS[talent_name]
    current_level = general.get(db_field, 0)

    if current_level >= TALENT_MAX_LEVEL:
        return False, f"{talent_name}已达最高等级", {}

    new_level = current_level + 1
    cost = TALENT_COSTS[new_level]
    talent_skill = general.get("talent_skill", 0)

    if talent_skill < cost:
        return False, f"天赋点不足，需要{cost}点，当前{talent_skill}点", {}

    updates = {}
    general["talent_skill"] = talent_skill - cost
    updates["talent_skill"] = general["talent_skill"]

    general[db_field] = new_level
    updates[db_field] = new_level

    if talent_name == "勇冠三军":
        old_bonus = TALENT_BONUSES["勇冠三军"].get(current_level, 0)
        new_bonus = TALENT_BONUSES["勇冠三军"].get(new_level, 0)
        delta = new_bonus - old_bonus
        general["combo_rate"] = general.get("combo_rate", 0) + delta
        updates["combo_rate"] = general["combo_rate"]

    return True, f"{talent_name}升级成功，当前等级{new_level}", updates


def get_resurrection_remaining(death_time_ms, current_time_ms):
    """
    计算复活剩余时间
    :param death_time_ms: 阵亡时间（毫秒时间戳）
    :param current_time_ms: 当前时间（毫秒时间戳）
    :return: 剩余秒数，0 表示已复活
    """
    if not death_time_ms:
        return 0
    resurrection_time_ms = death_time_ms + RESURRECTION_SECONDS * 1000
    remaining_ms = resurrection_time_ms - current_time_ms
    if remaining_ms <= 0:
        return 0
    return remaining_ms // 1000


def check_and_revive(general, current_time_ms):
    """
    检查武将是否满足复活条件，满足则复活
    :param general: 武将数据字典（会直接修改）
    :param current_time_ms: 当前时间（毫秒时间戳）
    :return: (revived: bool, updates: dict or None)
    """
    if general.get("status") != 4:
        return False, None

    remaining = get_resurrection_remaining(general.get("death_time"), current_time_ms)
    if remaining > 0:
        return False, None

    updates = {
        "status": 0,
        "death_time": None,
        "morale": 100,
    }
    general.update(updates)
    return True, updates


async def load_all_generals_to_cache():
    """服务端启动时，从数据库全量加载所有用户的武将到内存缓存
    缓存结构: generals_cache[user_id] = [general_dict, ...]
    如果某用户没有武将，则缓存为空列表
    """
    from general.general_db import get_all_generals

    generals_cache.clear()
    all_generals = await get_all_generals()

    count = 0
    for general in all_generals:
        user_id = general["user_id"]
        if user_id not in generals_cache:
            generals_cache[user_id] = []
        generals_cache[user_id].append(general)
        count += 1

    user_count = len(generals_cache)
    logger.info(f"武将缓存加载完成: {count} 个武将, {user_count} 个用户")


def sync_cache_insert(general):
    """武将新增后，同步更新内存缓存
    :param general: 数据库返回的完整武将字典（必须包含 user_id 和 id）
    """
    if not general:
        return
    user_id = general.get("user_id")
    if not user_id:
        return
    if user_id not in generals_cache:
        generals_cache[user_id] = []
    generals_cache[user_id].append(general)


def sync_cache_update(general_id, updates):
    """武将更新后，同步更新内存缓存中对应武将的字段
    :param general_id: 武将ID
    :param updates: 更新的字段字典
    """
    if not general_id or not updates:
        return
    for user_id, general_list in generals_cache.items():
        for g in general_list:
            if g.get("id") == general_id:
                g.update(updates)
                return


def sync_cache_delete(user_id, general_id):
    """武将删除后，同步移除内存缓存中对应武将
    :param user_id: 用户ID
    :param general_id: 武将ID
    """
    if not user_id or not general_id:
        return
    general_list = generals_cache.get(user_id)
    if not general_list:
        return
    generals_cache[user_id] = [g for g in general_list if g.get("id") != general_id]
from data.troop_data import TROOP_DATA, TROOP_DATA_SPECIAL
from general.general_core import TALENT_BONUSES


def get_general_max_troop_count(general):
    if not general:
        return 0
    force = general.get("force") or general.get("force_initial", 0)
    charisma = general.get("charisma") or general.get("charisma_initial", 0)
    base_count = force * 10 + charisma * 20
    talent_level = general.get("talent_djzc", 0)
    talent_bonus = TALENT_BONUSES.get("大将之材", {}).get(talent_level, 0)
    return base_count + talent_bonus


def calculate_max_carry_food(team):
    max_food = 0
    for slot in team:
        if slot is None:
            continue
        name = slot.get("兵种名称")
        count = slot.get("数量", 0)
        if not name or count <= 0:
            continue
        troop_info = next((t for t in TROOP_DATA if t["兵种名称"] == name), None)
        if troop_info is None:
            troop_info = next((t for t in TROOP_DATA_SPECIAL if t["兵种名称"] == name), None)
        if troop_info:
            max_food += troop_info["可携带粮食"] * count
    return max_food


def calculate_total_troops(team):
    total = 0
    for slot in team:
        if slot is None:
            continue
        total += slot.get("数量", 0)
    return total
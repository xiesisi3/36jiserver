import logging

logger = logging.getLogger("36ji-server")


def accumulate_round_stats(town_id, round_num, troop_order, dynamic_troops, attack_sequences):
    stats = {}
    return stats


async def persist_round_stats(town_id, round_num, stats):
    pass


async def get_combat_final_stats(town_id):
    return {}
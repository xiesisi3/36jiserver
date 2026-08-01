from data.global_data import log_dic_cache
from system_log.system_log_db import get_all_log_dic


async def load_log_dic_to_cache():
    rows = await get_all_log_dic()
    log_dic_cache.clear()
    for row in rows:
        log_dic_cache[row["type_name"]] = row["id"]


def get_log_id(type_name):
    return log_dic_cache.get(type_name)
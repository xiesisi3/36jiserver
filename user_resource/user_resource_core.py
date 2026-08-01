import logging
from data.global_data import user_resource_cache, player_name_index
from user_resource.user_resource_db import (
    get_all_user_resources,
    get_user_resource_by_user_id,
    get_user_resource_by_player_name,
    insert_user_resource,
    update_player_name,
)

logger = logging.getLogger('36ji-server')


async def load_all_user_resources_to_cache():
    rows = await get_all_user_resources()
    user_resource_cache.clear()
    player_name_index.clear()
    for row in rows:
        user_resource_cache[row["user_id"]] = dict(row)
        if row.get("player_name"):
            player_name_index[row["player_name"]] = row["user_id"]
    logger.info(f"用户资源加载完成，共 {len(user_resource_cache)} 条")


async def create_user_resource(user_id):
    resource_id = await insert_user_resource(user_id)
    row = await get_user_resource_by_user_id(user_id)
    if row:
        user_resource_cache[user_id] = dict(row)
    return resource_id


def get_user_resource_from_cache(user_id):
    return user_resource_cache.get(user_id)


def is_player_name_exists(player_name):
    return player_name in player_name_index


async def set_player_name(user_id, player_name):
    if is_player_name_exists(player_name):
        return False, "游戏名称已存在"
    await update_player_name(user_id, player_name)
    if user_id in user_resource_cache:
        user_resource_cache[user_id]["player_name"] = player_name
    player_name_index[player_name] = user_id
    return True, "设置成功"


async def check_user_exists_by_player_name(player_name):
    exists = is_player_name_exists(player_name)
    user_id = player_name_index.get(player_name, "")
    return exists, user_id
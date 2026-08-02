import asyncio
import signal
import logging
import warnings
from websockets import serve

warnings.filterwarnings("ignore", message=".*Table.*already exists.*")

from core.connection import register_client, unregister_client
from message.router import message_handler
from core.database import init_pool, close_pool
from system_user.system_user_db import create_table as create_system_user_table
from system_user.system_user_core import load_all_users_to_cache
from system_log.system_log_db import create_tables as create_system_log_tables
from system_log.system_log_dic import load_log_dic_to_cache
from towns.towns_db import create_table as create_towns_table
from towns.towns_core import init_towns
from towns.town_levels import diffuse_town_levels, LEVEL_ATTRS, random_resource
from towns.towns_db import batch_update_town_levels
from roads.roads_db import create_table as create_roads_table
from roads.roads_core import init_roads
from terrain.terrain_db import create_tables as create_terrain_tables
from terrain.terrain_core import init_terrain, expand_mountain_vertices
from nations.nation_core import init_nations, load_all_user_nations_to_cache
from user_resource.user_resource_db import create_table as create_user_resource_table
from user_resource.user_resource_core import load_all_user_resources_to_cache
from server_timer.server_timer_db import create_table as create_server_timer_table
from server_timer.server_timer_core import init_timer, shutdown_timer
from general.general_db import create_table as create_generals_table
from general.general_core import load_all_generals_to_cache
from notification.notification_db import create_tables as create_notification_tables
from fief.fief_db import create_tables as create_fief_tables
from fief.fief_core import init_fiefs
from troop.troop_db import create_tables as create_troop_tables
from troop.troop_core import init_troops
from towns.towns_outer.town_outer_grid_core import init_outer_grid
from towns.towns_outer.town_outer_combat.combat_db import create_tables as create_combat_tables
from towns.towns_outer.town_outer_combat.combat_recovery import recover_combat_state
from treasure.treasure_db import create_table as create_treasure_table
from treasure.treasure_core import load_all_treasures_to_cache
from items.item_db import create_table as create_items_table
from items.item_core import load_all_items_to_cache
from data.global_data import towns_cache
from mission.mission_db import create_table as create_mission_table
from mission.mission_core import load_all_missions_to_cache
from tech.tech_db import create_table as create_tech_table
from tech.tech_core import load_all_techs_to_cache
from legion.legion_core import init_legions
from legion.legion_db import create_tables as create_legion_tables

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SERVER] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('36ji-server')


async def connection_handler(websocket):
    client_id = await register_client(websocket)
    try:
        await message_handler(websocket, client_id)
    finally:
        await unregister_client(client_id)


async def init_town_levels():
    if any(t.get("level", 1) > 1 for t in towns_cache.values()):
        logger.info("城池等级已存在，跳过初始化")
        return

    assigned = diffuse_town_levels()

    updates = []
    for tid, lv in assigned.items():
        attrs = LEVEL_ATTRS[lv]
        updates.append({
            "id": tid,
            "level": lv,
            "forest": random_resource(*attrs["forest"]),
            "fertile": random_resource(*attrs["fertile"]),
            "mine": random_resource(*attrs["mine"]),
            "stability": attrs["stability"],
            "defense": attrs["defense"],
            "traffic": attrs["traffic"],
        })
        if tid in towns_cache:
            towns_cache[tid]["level"] = lv
            towns_cache[tid]["forest"] = updates[-1]["forest"]
            towns_cache[tid]["fertile"] = updates[-1]["fertile"]
            towns_cache[tid]["mine"] = updates[-1]["mine"]
            towns_cache[tid]["stability"] = updates[-1]["stability"]
            towns_cache[tid]["defense"] = updates[-1]["defense"]
            towns_cache[tid]["traffic"] = updates[-1]["traffic"]

    await batch_update_town_levels(updates)
    logger.info(f"城池等级与属性初始化完成，共 {len(updates)} 城")


async def main():
    host, port = "0.0.0.0", 8765
    await init_pool()

    await create_system_user_table()
    await create_system_log_tables()
    await create_towns_table()
    await create_roads_table()
    await create_terrain_tables()

    await create_user_resource_table()
    await create_server_timer_table()
    await create_generals_table()
    await create_notification_tables()
    await create_fief_tables()
    await create_troop_tables()
    await create_combat_tables()
    await create_treasure_table()

    await create_items_table()

    await create_mission_table()

    await create_tech_table()
    await create_legion_tables()

    await load_all_users_to_cache()
    await load_log_dic_to_cache()
    await init_terrain()
    await init_towns()
    await expand_mountain_vertices()
    await init_roads()
    await init_nations()
    await init_town_levels()

    await load_all_user_resources_to_cache()
    await load_all_user_nations_to_cache()
    await load_all_generals_to_cache()
    await load_all_treasures_to_cache()
    await load_all_items_to_cache()
    await load_all_missions_to_cache()
    await load_all_techs_to_cache()
    await init_legions()
    await init_timer()
    await init_fiefs()
    await init_troops()
    await init_outer_grid()
    await recover_combat_state()

    logger.info(f"三十六计游戏服务器启动在 ws://{host}:{port}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        async with serve(connection_handler, host, port, compression="deflate"):
            await stop_event.wait()
    finally:
        await shutdown_timer()
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务器已终止")
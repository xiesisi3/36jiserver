import time
import asyncio
import logging
from datetime import datetime
from server_timer.server_timer_db import load_timer, save_timer

logger = logging.getLogger('36ji-server')

_uptime_ms = 0
_cycle_count = 1
_start_monotonic = 0.0
_last_start_time = None
_sync_task = None
_last_fief_income_time = 0


def get_uptime_ms():
    return _uptime_ms


def get_cycle_count():
    return _cycle_count


def get_last_start_time():
    return _last_start_time


async def init_timer():
    global _uptime_ms, _cycle_count, _start_monotonic, _last_start_time, _sync_task

    row = await load_timer()
    _uptime_ms = row["uptime_ms"]
    _cycle_count = row["cycle_count"]
    _start_monotonic = time.monotonic()
    _last_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _sync_task = asyncio.create_task(_sync_loop())

    logger.info(f"计时器初始化完成，当前累计运行时长: {_uptime_ms}ms")


async def _sync_loop():
    try:
        while True:
            await asyncio.sleep(5)
            _update_from_monotonic()
            await save_timer(_uptime_ms, _cycle_count)
            await _update_fiefs()
            await _update_marching_troops()
            await _update_combat()
            await _revive_dead_generals()
    except asyncio.CancelledError:
        pass


async def _update_fiefs():
    global _last_fief_income_time

    try:
        from fief.fief_core import (
            _check_and_complete_builds,
            _check_and_complete_training,
            _check_and_apply_income,
            sync_fief_data_to_db,
        )
        from data.global_data import fief_cache, user_resource_cache
        from user_resource.user_resource_db import batch_update_user_resources

        now_ms = get_uptime_ms()
        if _last_fief_income_time == 0:
            _last_fief_income_time = now_ms

        elapsed_ms = now_ms - _last_fief_income_time
        minutes_elapsed = elapsed_ms / 60000.0

        changed_fiefs = set()
        income_users = set()

        for fief_id in list(fief_cache.keys()):
            build_changed = await _check_and_complete_builds(fief_id)
            train_changed = _check_and_complete_training(fief_id)
            income_changed = False

            if minutes_elapsed >= 1.0:
                income_changed = _check_and_apply_income(fief_id, minutes_elapsed)

            if build_changed or train_changed or income_changed:
                changed_fiefs.add(fief_id)

            if income_changed:
                fief = fief_cache.get(fief_id)
                if fief:
                    income_users.add(fief["user_id"])

        if income_users:
            user_updates = {}
            for user_id in income_users:
                user_resource = user_resource_cache.get(user_id)
                if user_resource:
                    user_updates[user_id] = {
                        "wood": user_resource["wood"],
                        "grain": user_resource["grain"],
                        "iron": user_resource["iron"],
                        "copper": user_resource["copper"],
                    }
            await batch_update_user_resources(user_updates)

        for fief_id in changed_fiefs:
            await sync_fief_data_to_db(fief_id)

        if minutes_elapsed >= 1.0:
            _last_fief_income_time = now_ms
    except Exception as e:
        logger.error(f"封地定时更新异常: {e}")


async def _update_marching_troops():
    try:
        from data.global_data import troop_cache, troops_arrived_at_town, towns_cache, user_nation_cache
        from troop.troop_march_db import update_troop_arrive_status
        from towns.towns_outer.town_outer_grid_core import add_troop_to_grid
        from towns.towns_outer.town_outer_combat.combat_state import enter_combat_if_needed

        now_ms = get_uptime_ms()

        for troop_id, troop in list(troop_cache.items()):
            if troop.get("status") != 2:
                continue

            arrive_time = troop.get("arrive_time", 0) or 0
            if arrive_time <= 0:
                continue

            if now_ms < arrive_time:
                continue

            dest = troop.get("dest")
            grid_x = troop.get("gate_x")
            grid_y = troop.get("gate_y")

            if dest is None:
                continue

            town = towns_cache.get(dest)
            town_owner = town.get("owner") if town else None
            troop_owner = user_nation_cache.get(troop.get("user_id", ""))

            general_id = troop.get("general_id")

            if troop_owner is not None and town_owner is not None and troop_owner == town_owner:
                troop["status"] = 1
                troop["pos"] = dest
                troop["dest"] = None
                troop["grid_x"] = grid_x
                troop["grid_y"] = grid_y
                troop.pop("gate_x", None)
                troop.pop("gate_y", None)

                if grid_x is not None and grid_y is not None:
                    await add_troop_to_grid(dest, troop_id, grid_x, grid_y)

                from core.database import get_pool as get_pool_
                pool_ = get_pool_()
                async with pool_.acquire() as txn_conn:
                    await txn_conn.begin()
                    try:
                        await update_troop_arrive_status(troop_id, 1, grid_x, grid_y, pos=dest, dest=None, conn=txn_conn)

                        if general_id:
                            from general.general_db import update_general
                            from general.general_core import sync_cache_update
                            await update_general(general_id, {"status": 1, "pos": dest, "dest": None}, conn=txn_conn)
                            sync_cache_update(general_id, {"status": 1, "pos": dest, "dest": None})

                        await txn_conn.commit()
                    except Exception:
                        await txn_conn.rollback()
                        raise

                if dest is not None:
                    troops_arrived_at_town.setdefault(dest, []).append(troop_id)

                logger.info(f"部队 {troop_id} 行军到达己方城池 {dest}，状态变更为驻守")
            else:
                troop["status"] = 3
                troop["pos"] = dest
                troop["dest"] = None
                troop["grid_x"] = grid_x
                troop["grid_y"] = grid_y
                troop.pop("gate_x", None)
                troop.pop("gate_y", None)

                if grid_x is not None and grid_y is not None and dest is not None:
                    await add_troop_to_grid(dest, troop_id, grid_x, grid_y)

                from core.database import get_pool as get_pool_
                pool_ = get_pool_()
                async with pool_.acquire() as txn_conn:
                    await txn_conn.begin()
                    try:
                        await update_troop_arrive_status(troop_id, 3, grid_x, grid_y, pos=dest, dest=None, conn=txn_conn)

                        if general_id:
                            from general.general_db import update_general
                            from general.general_core import sync_cache_update
                            await update_general(general_id, {"status": 3, "pos": dest, "dest": None}, conn=txn_conn)
                            sync_cache_update(general_id, {"status": 3, "pos": dest, "dest": None})

                        await txn_conn.commit()
                    except Exception:
                        await txn_conn.rollback()
                        raise

                if dest is not None:
                    troops_arrived_at_town.setdefault(dest, []).append(troop_id)

                logger.info(f"部队 {troop_id} 行军到达敌方城池 {dest}，状态变更为战斗中")

                await enter_combat_if_needed(dest)

    except Exception as e:
        logger.error(f"行军到达检测异常: {e}")


async def _update_combat():
    try:
        from towns.towns_outer.town_outer_combat.combat_state import _update_combat_triggers
        await _update_combat_triggers()
    except Exception as e:
        logger.error(f"战斗定时检测异常: {e}")


async def _revive_dead_generals():
    try:
        from data.global_data import generals_cache
        from general.general_db import update_general
        from general.general_core import RESURRECTION_SECONDS, sync_cache_update

        now_ms = get_uptime_ms()
        threshold_ms = RESURRECTION_SECONDS * 1000

        for user_id, generals in list(generals_cache.items()):
            for general in generals:
                if general.get("status") != 4:
                    continue
                death_time = general.get("death_time")
                if death_time is None:
                    continue
                if now_ms - death_time < threshold_ms:
                    continue

                general_id = general["id"]
                general["status"] = 0
                general["death_time"] = None
                await update_general(general_id, {"status": 0, "death_time": None})
                sync_cache_update(general_id, {"status": 0, "death_time": None})
                logger.info(f"武将 {general_id}（{general.get('general_name', '')}）复活，状态恢复为未编组")
    except Exception as e:
        logger.error(f"武将复活检测异常: {e}")


def _update_from_monotonic():
    global _uptime_ms, _start_monotonic
    elapsed = int((time.monotonic() - _start_monotonic) * 1000)
    _uptime_ms += elapsed
    _start_monotonic = time.monotonic()


async def shutdown_timer():
    global _sync_task
    if _sync_task is not None:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        _sync_task = None
    _update_from_monotonic()
    await save_timer(_uptime_ms, _cycle_count)
    logger.info(f"计时器已保存，累计运行时长: {_uptime_ms}ms")
import logging

from core.connection import send_message
from message.protocol import make_response
from server_timer.server_timer_core import get_uptime_ms
from data.global_data import towns_cache, fight_round_vars
from towns.towns_core import get_town_by_id_from_cache

logger = logging.getLogger("36ji-server")


async def handle_town_combat_detail(websocket, client_id, msg):
    data = msg.get("data", {})
    town_id = data.get("town_id")

    if not town_id:
        await send_message(websocket, make_response("error", "缺少城池ID", ""))
        return

    town = get_town_by_id_from_cache(town_id)
    if town is None:
        await send_message(websocket, make_response("error", "城池不存在", ""))
        return

    status = town.get("status", 0)

    if status == 0:
        await send_message(websocket, make_response("success", "城池详情", dict(town)))
        return

    now_ms = get_uptime_ms()

    if status == 1:
        frv = fight_round_vars.get(town_id)
        preload_end_ms = frv.get("preload_end_ms", 0) if frv else 0
        await send_message(websocket, make_response("success", "城池战斗准备中", {
            "town_id": town_id,
            "status": 1,
            "state": "preparing",
            "round_num": 0,
            "preload_end_ms": preload_end_ms,
            "town": dict(town),
        }))
        return

    if status == 3:
        frv = fight_round_vars.get(town_id)
        end_prepare_ms = frv.get("end_prepare_ms", 0) if frv else 0
        await send_message(websocket, make_response("success", "城池战斗结束中", {
            "town_id": town_id,
            "status": 3,
            "state": "ending",
            "end_prepare_ms": end_prepare_ms,
            "town": dict(town),
        }))
        return

    if status == 2:
        frv = fight_round_vars.get(town_id)
        if not frv or not frv.get("calc_completed"):
            logger.warning(f"[战斗] 城池{town_id} 状态=2但calc_completed未就绪, frv={bool(frv)}")
            await send_message(websocket, make_response("success", "城池详情", dict(town)))
            return

        tm = frv.get("tm", [])
        ss = frv.get("ss", [])
        is_ = frv.get("is", {})
        round_start_ms = frv.get("start_time", now_ms)
        round_num = frv.get("round_num", 0)
        elapsed = now_ms - round_start_ms

        ci = 0
        for i, entry in enumerate(tm):
            if entry.get("s", 0) <= elapsed < entry.get("e", float("inf")):
                ci = i
                break
        else:
            if tm and elapsed >= tm[-1].get("e", 0):
                ci = len(tm)

        if ci == 0:
            ts = is_
        else:
            ts = {}
            for tid in is_:
                ts[tid] = dict(is_[tid])
                ts[tid].pop("g", None)

            apply_count = min(ci, len(ss))
            for i in range(apply_count):
                action = ss[i]
                aid = action["id"]
                if aid in ts:
                    if action.get("ph"):
                        ts[aid]["p"] = list(action["ph"][-1])
                    if action.get("atk"):
                        for atk in action["atk"]:
                            if atk.get("t") is not None:
                                si = atk["s"]
                                if si < len(ts[aid]["t"]):
                                    ts[aid]["t"][si][1] -= atk.get("k", 0)
                                    if ts[aid]["t"][si][1] < 0:
                                        ts[aid]["t"][si][1] = 0
                            if atk.get("ct"):
                                for ct in atk["ct"]:
                                    csi = ct["t"]
                                    if csi < len(ts[aid]["t"]):
                                        ts[aid]["t"][csi][1] -= ct.get("k", 0)
                                        if ts[aid]["t"][csi][1] < 0:
                                            ts[aid]["t"][csi][1] = 0
                    tg = action.get("tg")
                    if tg and tg in ts and action.get("atk"):
                        for atk in action["atk"]:
                            if atk.get("t") is not None:
                                ti = atk["t"]
                                if ti < len(ts[tg]["t"]):
                                    ts[tg]["t"][ti][1] -= atk.get("k", 0)
                                    if ts[tg]["t"][ti][1] < 0:
                                        ts[tg]["t"][ti][1] = 0
                            if atk.get("mt"):
                                for mt in atk["mt"]:
                                    mi = mt["t"]
                                    if mi < len(ts[tg]["t"]):
                                        ts[tg]["t"][mi][1] -= mt.get("k", 0)
                                        if ts[tg]["t"][mi][1] < 0:
                                            ts[tg]["t"][mi][1] = 0

        remaining_as = ss[ci:]
        remaining_tm = tm[ci:]

        client_user_id = None
        from data.global_data import clients
        client_info = clients.get(client_id)
        if client_info:
            client_user_id = client_info.get("user_id")

        all_stats = frv.get("stats", {})
        player_stats = (all_stats.get("players", {}).get(client_user_id)
                        if client_user_id else None)

        await send_message(websocket, make_response("success", "城池战斗回合数据", {
            "ci": ci,
            "ts": ts,
            "is": is_,
            "as": remaining_as,
            "tm": remaining_tm,
            "rn": round_num,
            "rss": round_start_ms,
            "ree": frv.get("estimated_end_time", round_start_ms),
            "stats": {
                "player": player_stats,
                "owners": all_stats.get("owners", {}),
            },
            "town": dict(town),
        }))
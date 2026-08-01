# -*- coding: utf-8 -*-
import logging

from data.global_data import towns_cache, user_nation_cache, nation_cache, user_resource_cache, troop_cache
from data.troop_data import TROOP_DATA
from data.combat_reward_config import (
    TROOP_LEVEL_SCORE, REWARD_TIERS, TICKET_SCORE, CHEST_SCORE,
    VICTORY_FACTOR, MVP_REWARD, SVP_REWARD, BUDGET_SPLIT,
)
from towns.towns_outer.town_outer_combat.combat_db import (
    get_all_combat_rounds_by_history,
    get_general_kills_by_history,
    get_combat_history,
)
from notification.notification_core import publish_system_message
from items.item_core import add_item_to_user
from user_resource.user_resource_db import update_user_resource_field
from general.general_utils import get_general_info
from mission.mission_core import add_combat_score

logger = logging.getLogger("36ji-server")


def _build_troop_level_map():
    level_map = {}
    for item in TROOP_DATA:
        name = item.get("兵种名称")
        if name:
            level_map[name] = item.get("兵种等级", "")
    return level_map


def _build_gain_death_exp_map():
    gain_map = {}
    death_map = {}
    for item in TROOP_DATA:
        name = item.get("兵种名称")
        if name:
            if item.get("gain_exp", 0):
                gain_map[name] = item["gain_exp"]
            if item.get("death_exp", 0):
                death_map[name] = item["death_exp"]
    return gain_map, death_map


def _aggregate_participation(rounds):
    seen_troops = {}
    for rd in rounds:
        initial_troops = rd.get("initial_troops") or {}
        for tid_str, info in initial_troops.items():
            tid = int(tid_str) if isinstance(tid_str, str) else tid_str
            if tid not in seen_troops:
                if isinstance(info, dict):
                    seen_troops[tid] = info
                else:
                    seen_troops[tid] = {"s": info, "u": ""}
    return seen_troops


def _aggregate_losses(troop_participation, rounds):
    """统计各部队的阵亡情况（部队数 + 士兵数）

    通过比对汇总的初始兵力(troop_participation，已跨回合去重，首次出现为准)和
    最后一回合的结束状态(round_data.troops)，计算每支部队的阵亡部队数和阵亡士兵数。
    不依赖town_combat_general_kills表，因此山贼部队的损失也能正确统计。

    Args:
        troop_participation: _aggregate_participation的返回值，{troop_id: {"s": 初始士兵数, "u": user_id}}
        rounds: 所有回合数据列表

    Returns:
        dict: {troop_id: {"troops_lost": 0或1, "soldiers_lost": 士兵损失数}}
    """
    if not rounds:
        return {}

    last_round = rounds[-1]
    final_data = last_round.get("round_data") or {}
    final_troops = final_data.get("troops") or {}

    result = {}
    for tid, info in troop_participation.items():
        init_count = info.get("s", 0) if isinstance(info, dict) else info

        final_troop = final_troops.get(str(tid)) or final_troops.get(tid)
        if final_troop:
            final_count = sum(
                slot.get("数量", 0) for slot in final_troop.get("team", []) if slot
            )
            result[tid] = {"troops_lost": 0, "soldiers_lost": max(0, init_count - final_count)}
        else:
            result[tid] = {"troops_lost": 1, "soldiers_lost": init_count}

    return result


def _aggregate_kills(all_kills, level_map, gain_exp_map, death_exp_map):
    user_stats = {}
    general_exp = {}

    for row in all_kills:
        user_id = str(row["user_id"])
        if user_id == "0":
            continue

        kills = row.get("kills") or []
        losses = row.get("losses") or []
        eliminated_troops = row.get("eliminated_troops") or []
        general_id = row.get("general_id")

        if user_id not in user_stats:
            user_stats[user_id] = {
                "kills": {},
                "losses": {},
                "eliminated_troops": set(),
                "score": 0.0,
            }
        if user_id not in general_exp:
            general_exp[user_id] = {}

        us = user_stats[user_id]

        for entry in kills:
            name = entry.get("兵种名称", "")
            count = entry.get("数量", 0)
            if name and count > 0:
                us["kills"][name] = us["kills"].get(name, 0) + count
                level = level_map.get(name, "")
                if level:
                    us["score"] += count * TROOP_LEVEL_SCORE.get(level, {}).get("kill", 0)

        for entry in losses:
            name = entry.get("兵种名称", "")
            count = entry.get("数量", 0)
            if name and count > 0:
                us["losses"][name] = us["losses"].get(name, 0) + count
                level = level_map.get(name, "")
                if level:
                    us["score"] += count * TROOP_LEVEL_SCORE.get(level, {}).get("death", 0)

        for etid in eliminated_troops:
            us["eliminated_troops"].add(etid)

        if general_id:
            if general_id not in general_exp[user_id]:
                general_exp[user_id][general_id] = {"kills": {}, "soldiers_killed": 0, "exp": 0}
            ge = general_exp[user_id][general_id]
            for entry in kills:
                name = entry.get("兵种名称", "")
                count = entry.get("数量", 0)
                if name and count > 0:
                    ge["kills"][name] = ge["kills"].get(name, 0) + count
                    ge["soldiers_killed"] += count
                    ge["exp"] += count * gain_exp_map.get(name, 0)
            for entry in losses:
                name = entry.get("兵种名称", "")
                count = entry.get("数量", 0)
                if name and count > 0:
                    ge["exp"] += count * death_exp_map.get(name, 0)

    for user_id, ge_dict in general_exp.items():
        for general_id, ge in ge_dict.items():
            if general_id > 0:
                general = get_general_info(general_id)
                if general:
                    wisdom = general.get("wisdom", 0)
                    if wisdom > 0:
                        ge["exp"] = int(ge["exp"] * wisdom / 100)
                    else:
                        ge["exp"] = int(ge["exp"])

    return user_stats, general_exp


def _calculate_nation_stats(user_stats, bandit_stats=None, troop_losses=None, troop_to_nation=None):
    nation_stats = {}

    for user_id, us in user_stats.items():
        nation_id = user_nation_cache.get(user_id)
        if nation_id is None:
            continue
        if nation_id not in nation_stats:
            nation_stats[nation_id] = {
                "troops": 0,
                "soldiers": 0,
                "eliminated_troops": set(),
                "soldiers_killed": 0,
                "troops_lost": 0,
                "soldiers_lost": 0,
            }
        ns = nation_stats[nation_id]
        ns["troops"] += len(us.get("_participating_troops", []))
        ns["soldiers"] += us.get("_participating_soldiers", 0)
        ns["eliminated_troops"] |= us.get("eliminated_troops", set())
        ns["soldiers_killed"] += sum(us.get("kills", {}).values())
        ns["troops_lost"] += us.get("_troops_lost", 0)
        ns["soldiers_lost"] += us.get("_soldiers_lost", 0)

    # 山贼集团（nation_id=1）不统计击杀数（eliminated_troops/soldiers_killed）和得分，
    # 因为山贼是NPC，其击杀记录在_aggregate_kills中已被跳过（user_id=="0"），
    # 击杀数据、经验、积分对NPC无意义。
    # 但阵亡数据（troops_lost/soldiers_lost）通过回合初始/结束状态比对可以正常统计。
    if bandit_stats and (bandit_stats["troops"] > 0 or bandit_stats["soldiers"] > 0):
        bandit_troops_lost = 0
        bandit_soldiers_lost = 0
        if troop_losses and troop_to_nation:
            for tid, loss in troop_losses.items():
                if troop_to_nation.get(tid) == 1:
                    bandit_troops_lost += loss["troops_lost"]
                    bandit_soldiers_lost += loss["soldiers_lost"]
        nation_stats[1] = {
            "troops": bandit_stats["troops"],
            "soldiers": bandit_stats["soldiers"],
            "eliminated_troops": set(),
            "soldiers_killed": 0,
            "troops_lost": bandit_troops_lost,
            "soldiers_lost": bandit_soldiers_lost,
        }

    return nation_stats


def _get_attack_defense_label(nation_id, original_town_owner):
    if nation_id is None or original_town_owner is None:
        return "未知"
    return "进攻" if int(nation_id) != int(original_town_owner) else "防御"


def _get_victory_factor(user_id, victory_type, winner):
    nation_id = user_nation_cache.get(user_id)
    if nation_id is None:
        return 1.0
    if victory_type in ("防御成功", "占领"):
        if nation_id == winner:
            return VICTORY_FACTOR.get(victory_type, 1.0)
    return 1.0


def _calculate_rewards(user_stats, victory_type, winner):
    rewards = {}
    for user_id, us in user_stats.items():
        score = us["score"]
        if score <= 0:
            continue

        tier_idx = -1
        for i, tier in enumerate(REWARD_TIERS):
            if score >= tier[0]:
                tier_idx = i
        if tier_idx < 0:
            continue

        tier_name, ticket_name, chest_name = REWARD_TIERS[tier_idx][1:]

        vf = _get_victory_factor(user_id, victory_type, winner)
        eff_score = score * vf

        ticket_budget = eff_score * BUDGET_SPLIT
        chest_budget = eff_score * BUDGET_SPLIT

        max_score = TICKET_SCORE.get(ticket_name, 0)

        sorted_tickets = sorted(TICKET_SCORE.items(), key=lambda x: x[1], reverse=True)
        extra_tickets = {}
        for t_name, t_score in sorted_tickets:
            if t_score > max_score:
                continue
            while ticket_budget >= t_score:
                extra_tickets[t_name] = extra_tickets.get(t_name, 0) + 1
                ticket_budget -= t_score

        sorted_chests = sorted(CHEST_SCORE.items(), key=lambda x: x[1], reverse=True)
        extra_chests = {}
        for c_name, c_score in sorted_chests:
            if c_score > max_score:
                continue
            while chest_budget >= c_score:
                extra_chests[c_name] = extra_chests.get(c_name, 0) + 1
                chest_budget -= c_score

        final_items = {}
        final_items[ticket_name] = final_items.get(ticket_name, 0) + 1
        final_items[chest_name] = final_items.get(chest_name, 0) + 1
        for t_name, qty in extra_tickets.items():
            final_items[t_name] = final_items.get(t_name, 0) + qty
        for c_name, qty in extra_chests.items():
            final_items[c_name] = final_items.get(c_name, 0) + qty

        rewards[user_id] = {
            "score": int(score),
            "merit": int(score),
            "tier_name": tier_name,
            "items": final_items,
            "is_mvp": False,
            "is_svp": False,
        }

    return rewards


def _assign_mvp_svp(rewards, user_stats, victory_type, winner):
    mvp_user_id = None
    mvp_score = 0
    svp_user_id = None
    svp_score = 0

    for user_id, us in user_stats.items():
        if user_id not in rewards:
            continue
        nation_id = user_nation_cache.get(user_id)
        if nation_id is None:
            continue
        score = us["score"]
        is_winner = (nation_id == winner)

        if is_winner and score >= MVP_REWARD["min_score"] and score > mvp_score:
            mvp_user_id = user_id
            mvp_score = score
        if not is_winner and score >= SVP_REWARD["min_score"] and score > svp_score:
            svp_user_id = user_id
            svp_score = score

    if mvp_user_id:
        r = rewards[mvp_user_id]
        r["is_mvp"] = True
        tier_idx = -1
        for i, tier in enumerate(REWARD_TIERS):
            if r["score"] >= tier[0]:
                tier_idx = i
        if tier_idx >= 0:
            ticket_name = REWARD_TIERS[tier_idx][2]
            chest_name = REWARD_TIERS[tier_idx][3]
            r["items"][ticket_name] = r["items"].get(ticket_name, 0) + 1
            r["items"][chest_name] = r["items"].get(chest_name, 0) + 1
            r["_mvp_bonus"] = {ticket_name: 1, chest_name: 1}

    if svp_user_id:
        r = rewards[svp_user_id]
        r["is_svp"] = True
        tier_idx = -1
        for i, tier in enumerate(REWARD_TIERS):
            if r["score"] >= tier[0]:
                tier_idx = i
        if tier_idx >= 0:
            chest_name = REWARD_TIERS[tier_idx][3]
            r["items"][chest_name] = r["items"].get(chest_name, 0) + 1
            r["_svp_bonus"] = {chest_name: 1}

    return mvp_user_id, svp_user_id


def _build_notification_content(user_id, reward, rewards, stats, nation_stats, town_id, total_rounds, victory_type, winner, general_exp, mvp_user_id, svp_user_id, original_town_owner):
    player_name = user_resource_cache.get(user_id, {}).get("player_name", user_id)
    town_name = (towns_cache.get(town_id) or {}).get("name", str(town_id))
    winner_name = nation_cache.get(winner, {}).get("name", str(winner)) if winner else "山贼集团"

    def _get_nation_name(nid):
        if nid == 1:
            return "山贼集团"
        return nation_cache.get(nid, {}).get("name", str(nid))

    player_nation = user_nation_cache.get(user_id)
    nation_list = sorted(nation_stats.keys(), key=lambda n: (n != player_nation, n))

    lines = []
    lines.append(f"尊敬的玩家{player_name}你好：")
    lines.append(f"你在【{town_name}】的战斗持续了[red]{total_rounds}[/red]回合，参与的国家包含【{'、'.join(_get_nation_name(n) for n in nation_list)}】，最终【{winner_name}】取得了胜利。阵亡情况如下：")

    for nation_id in nation_list:
        ns = nation_stats.get(nation_id, {})
        nation_name = _get_nation_name(nation_id)
        ad_label = _get_attack_defense_label(nation_id, original_town_owner)
        lines.append(f"【{nation_name}】为【{ad_label}】方，共参与部队[green]{ns.get('troops', 0)}[/green]支，参与士兵共[green]{ns.get('soldiers', 0)}[/green]人，消灭敌军部队[green]{len(ns.get('eliminated_troops', set()))}[/green]支，消灭敌军士兵[green]{ns.get('soldiers_killed', 0)}[/green]人，阵亡部队[red]{ns.get('troops_lost', 0)}[/red]支，阵亡士兵[red]{ns.get('soldiers_lost', 0)}[/red]人。")

    us = stats.get(user_id, {})
    lines.append(f"你在此次战斗中，参与部队[green]{len([t for t in us.get('_participating_troops', [])])}[/green]支，参与士兵[green]{us.get('_participating_soldiers', 0)}[/green]名，消灭敌军部队[green]{len(us.get('eliminated_troops', set()))}[/green]支，消灭敌军士兵[green]{sum(us.get('kills', {}).values())}[/green]人，阵亡部队[red]{us.get('_troops_lost', 0)}[/red]支，阵亡士兵[red]{us.get('_soldiers_lost', 0)}[/red]人，各武将获得经验如下：")

    ge = general_exp.get(user_id, {})
    for general_id, ge_data in ge.items():
        gen_name = str(general_id)
        ginfo = get_general_info(general_id)
        if ginfo:
            gen_name = ginfo.get("hero_name", str(general_id))
        lines.append(f"【{gen_name}】，消灭[red]{ge_data['soldiers_killed']}[/red]人，获得经验[green]{ge_data['exp']}[/green]。")

    items_str = "、".join(f"【{name}】×{qty}" for name, qty in reward["items"].items())
    lines.append(f"你获得[green]{reward['score']}[/green]战斗积分，[green]{reward['merit']}[/green]功勋，获得奖励道具{items_str}。")

    if mvp_user_id:
        mvp_name = user_resource_cache.get(mvp_user_id, {}).get("player_name", mvp_user_id)
        mvp_nation = user_nation_cache.get(mvp_user_id)
        ad_label = _get_attack_defense_label(mvp_nation, original_town_owner) if mvp_nation is not None else ""
        mvp_bonus = rewards.get(mvp_user_id, {}).get("_mvp_bonus", {})
        mvp_items_str = "、".join(f"【{name}】×{qty}" for name, qty in mvp_bonus.items())
        lines.append(f"【{mvp_name}】为本场战斗【{ad_label}】方的[green]MVP[/green]，特此额外奖励道具{mvp_items_str}")

    if svp_user_id:
        svp_name = user_resource_cache.get(svp_user_id, {}).get("player_name", svp_user_id)
        svp_nation = user_nation_cache.get(svp_user_id)
        ad_label = _get_attack_defense_label(svp_nation, original_town_owner) if svp_nation is not None else ""
        svp_bonus = rewards.get(svp_user_id, {}).get("_svp_bonus", {})
        svp_items_str = "、".join(f"【{name}】×{qty}" for name, qty in svp_bonus.items())
        lines.append(f"【{svp_name}】为本场战斗【{ad_label}】方的[red]SVP[/red]，特此额外奖励道具{svp_items_str}")

    return "\n".join(lines)


async def settle_combat(town_id, history_id, winner, victory_type, original_town_owner=None):
    rounds = await get_all_combat_rounds_by_history(history_id)
    if not rounds:
        return

    all_kills = await get_general_kills_by_history(history_id)
    history = await get_combat_history(history_id)
    total_rounds = history.get("total_rounds", 0) if history else len(rounds)

    level_map = _build_troop_level_map()
    gain_exp_map, death_exp_map = _build_gain_death_exp_map()

    troop_participation = _aggregate_participation(rounds)
    user_stats, general_exp = _aggregate_kills(all_kills, level_map, gain_exp_map, death_exp_map)

    for user_id in list(user_stats.keys()):
        user_stats[user_id]["_participating_troops"] = []
        user_stats[user_id]["_participating_soldiers"] = 0
        user_stats[user_id]["_troops_lost"] = 0
        user_stats[user_id]["_soldiers_lost"] = 0

    # 统计各部队阵亡情况（基于 troop_participation 初始状态 + 最后一回合 round_data 结束状态比对，
    # 不依赖 town_combat_general_kills 表，因此山贼部队的损失也能正确统计）
    troop_losses = _aggregate_losses(troop_participation, rounds)

    # 构建部队→所属用户映射（troop_participation 已包含 user_id 的 u 字段）
    troop_to_user = {tid: str(info.get("u", "")) for tid, info in troop_participation.items()}

    # 构建部队→所属国家映射（山贼 user_id="0" 归属 nation_id=1 山贼集团）
    troop_to_nation = {}
    for tid, uid in troop_to_user.items():
        if uid == "0":
            troop_to_nation[tid] = 1
        else:
            nid = user_nation_cache.get(uid)
            if nid is not None:
                troop_to_nation[tid] = nid

    # 将阵亡数据聚合到各玩家（山贼 user_id="0" 跳过，不参与玩家统计）
    for tid, loss in troop_losses.items():
        uid = troop_to_user.get(tid)
        if uid and uid != "0" and uid in user_stats:
            user_stats[uid]["_troops_lost"] += loss["troops_lost"]
            user_stats[uid]["_soldiers_lost"] += loss["soldiers_lost"]

    bandit_stats = {"troops": 0, "soldiers": 0}

    for tid, info in troop_participation.items():
        if isinstance(info, dict):
            user_id = str(info.get("u", ""))
            count = info.get("s", 0)
        else:
            count = info
            tc = troop_cache.get(tid)
            if not tc:
                continue
            user_id = str(tc.get("user_id", ""))
        if user_id == "0" or not user_id:
            if user_id == "0":
                bandit_stats["troops"] += 1
                bandit_stats["soldiers"] += count
            continue
        if user_id not in user_stats:
            continue
        user_stats[user_id]["_participating_troops"].append(tid)
        user_stats[user_id]["_participating_soldiers"] += count

    nation_stats = _calculate_nation_stats(user_stats, bandit_stats, troop_losses, troop_to_nation)

    rewards = _calculate_rewards(user_stats, victory_type, winner)
    mvp_user_id, svp_user_id = _assign_mvp_svp(rewards, user_stats, victory_type, winner)

    for user_id, reward in rewards.items():
        player_name = user_resource_cache.get(user_id, {}).get("player_name", user_id)
        content = _build_notification_content(
            user_id, reward, rewards, user_stats, nation_stats,
            town_id, total_rounds, victory_type, winner,
            general_exp, mvp_user_id, svp_user_id, original_town_owner,
        )
        title = f"战斗结算 - {(towns_cache.get(town_id) or {}).get('name', str(town_id))}"

        await publish_system_message(
            receiver_id=user_id,
            receiver_name=player_name,
            title=title,
            content=content,
            category="战斗",
        )

        for item_name, quantity in reward["items"].items():
            result = await add_item_to_user(user_id, item_name, quantity)
        #     if result and "error" not in result:
        #         logger.info(f"[结算] 发放道具: user_id={user_id}, item={item_name}×{quantity}")

        if reward["merit"] > 0:
            current_merit = user_resource_cache.get(user_id, {}).get("merit", 0)
            new_merit = current_merit + reward["merit"]
            await update_user_resource_field(user_id, "merit", new_merit)
            if user_id in user_resource_cache:
                user_resource_cache[user_id]["merit"] = new_merit
            #logger.info(f"[结算] 更新功勋: user_id={user_id}, +{reward['merit']}, 总计={new_merit}")

        if reward["score"] > 0:
            await add_combat_score(user_id, int(reward["score"]))

    #logger.info(f"[结算] 战斗 history_id={history_id} 结算完成，共{len(rewards)}名玩家获得奖励")
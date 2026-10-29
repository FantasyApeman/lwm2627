import json
import datetime
import pandas as pd
import numpy as np
import requests
import os
from espn_api.basketball import League

# 從 GitHub Secrets 或本地環境安全讀取金鑰
LEAGUE_ID = 1697903242
YEAR = 2027
SWID = os.environ.get("SWID", "{2F303C3E-7439-43CB-B35A-5330424C062A}")
ESPN_S2 = os.environ.get("ESPN_S2", "AECyWklZiLxSSsqCo%2BmaNpP5E5V31Q08Q3OmPWP9DTJPmDC%2BEdsKDs7iBWmtrQ2z2XR%2Ba4JpqMACvkWY9NbFkZgrWCA2NQSwxmb9PkWTtw%2BZHgPzhdetRySt1YwCkEGMlzpm%2FguqIYl%2FNXVplraXQMOsRlvAYG%2F2eG4qzpHxdW1Biq7bT3WXaan1h61xyKgFe%2BNlLc4LWJvKU9z9LA9ZClWq%2FCPwAjkUQZNLauXC8fh4q%2Bfc45oXXNodZ6QXrGIxoltv1d7q58lstRY8bAyrSLV0phe%2B8HpxGiJBUlreNMv3bb5jbKpvO0N9ZErV%2BZ1Ja8g4gZgH0Ols4eaUrbePzRvu")

TEAM_MAPPING = {
    "UTA": "UTAH", "UTAH": "UTAH",
    "NOP": "NO", "NO": "NO", "NOH": "NO",
    "NYK": "NY", "NY": "NY",
    "GSW": "GS", "GS": "GS",
    "PHX": "PHX", "PHO": "PHX", "SUNS": "PHX",
    "PHI": "PHI", "PHL": "PHI", "SIXERS": "PHI", "76ERS": "PHI",
    "SAS": "SA", "SA": "SA",
    "WAS": "WSH", "WSH": "WSH"
}

EXACT_NAME_ALIAS = {
    "nic claxton": "nicolas claxton",
    "alperen sengun": "alperen sengün",
    "moussa diabate": "moussa diabaté",
    "alex sarr": "alexandre sarr"
}

VALID_POSITIONS = ["PG", "SG", "G", "SF", "PF", "F", "C"]

def clean_team_name(name):
    if not name: return ""
    return str(name).replace("Team", "").strip()

def clean_positions(pos_input):
    if not pos_input or str(pos_input) == 'nan':
        return "Util"
    raw_str = str(pos_input).replace('/', ' ').replace(',', ' ')
    tokens = raw_str.split()
    cleaned = []
    for t in tokens:
        t_upper = t.strip().upper()
        if t_upper in VALID_POSITIONS and t_upper not in cleaned:
            cleaned.append(t_upper)
    return ", ".join(cleaned) if cleaned else "Util"

def normalize_team(team_code):
    if not team_code:
        return "OKC"
    tc = str(team_code).strip().upper()
    return TEAM_MAPPING.get(tc, tc)

print("🚀 [1/5] Reading projection from Google Sheets...")
sheet_url = "https://docs.google.com/spreadsheets/d/1J9KnGlHBjjBmUy0GNIXDNmh5BdS8EMucl8FkD9lwg3c/export?format=csv"
df_proj = pd.read_csv(sheet_url)

excel_proj_dict = {}
player_team_map = {}
all_player_names = []

for _, row in df_proj.iterrows():
    p_name = str(row.get('PLAYER', row.get('Player', ''))).strip()
    if not p_name or p_name == 'nan': continue
    all_player_names.append(p_name)
    p_key = p_name.lower()
    team_name = normalize_team(row.get('TEAM', row.get('Team', 'FA')))
    player_team_map[p_key] = team_name
    pos_raw = row.get('POS', row.get('Position', row.get('POSITION', 'Util')))
    cleaned_pos = clean_positions(pos_raw)
    
    excel_proj_dict[p_key] = {
        "raw_name": p_name,
        "PTS": float(row.get('PTS', 12.0)), 
        "REB": float(row.get('TREB', row.get('REB', 5.0))), 
        "AST": float(row.get('AST', 3.0)),
        "3PTM": float(row.get('3PTM', row.get('3PM', 1.5))), 
        "STL": float(row.get('STL', 1.0)), 
        "BLK": float(row.get('BLK', 0.5)),
        "FG%": float(row.get('FG%', 0.46)), 
        "FT%": float(row.get('FT%', 0.78)), 
        "TO": float(row.get('TO', 1.8)),
        "FGM": float(row.get('FGM', 4.5)),
        "FGA": float(row.get('FGA', 10.0)),
        "FTM": float(row.get('FTM', 3.0)),
        "FTA": float(row.get('FTA', 3.8)),
        "SCORE": float(row.get('TOTAL', row.get('Score', row.get('TOTAL SCORE', 0.0)))),
        "proTeam": team_name,
        "position": cleaned_pos
    }

df_top150 = df_proj[df_proj['RANK'] <= 150] if 'RANK' in df_proj.columns else df_proj.head(150)
stats_meta = {}
cat_cols = {'PTS': 'PTS', 'REB': 'TREB', 'AST': 'AST', '3PTM': '3PTM', 'STL': 'STL', 'BLK': 'BLK', 'TO': 'TO', 'FG%': 'FG%', 'FT%': 'FT%'}

for cat, col in cat_cols.items():
    col_name = col if col in df_top150.columns else ('REB' if cat == 'REB' and 'REB' in df_top150.columns else cat)
    if col_name in df_top150.columns:
        vals = df_top150[col_name].dropna().values
        stats_meta[cat] = {'mean': float(np.mean(vals)), 'std': float(np.std(vals)) if np.std(vals) > 0 else 1.0}

print("🚀 [2/5] Initializing ESPN League connection...")
league = League(league_id=LEAGUE_ID, year=YEAR, espn_s2=ESPN_S2, swid=SWID)
current_week = getattr(league, 'current_week', 1)

print("🚀 [3/5] Building schedule, matchups, actual stats, and lineup slot positions...")
start_date_w1 = datetime.date(2026, 10, 19)
weeks_config = {}
global_nba_schedule = {}

def parse_lineup_stats(lineup):
    t_pts = t_reb = t_ast = t_tpt = t_stl = t_blk = t_to = 0.0
    t_fgm = t_fga = t_ftm = t_fta = 0.0
    played_gp = 0

    for p in lineup:
        p_stats_dict = getattr(p, 'stats', {})
        tot = {}
        if isinstance(p_stats_dict, dict):
            tot = p_stats_dict.get('0', {}).get('total', {})

        p_gp = tot.get('GP', 0)
        if p_gp > 0:
            played_gp += int(p_gp)
            t_pts += float(tot.get('PTS', 0))
            t_reb += float(tot.get('REB', 0))
            t_ast += float(tot.get('AST', 0))
            t_tpt += float(tot.get('3PM', tot.get('3PTM', 0)))
            t_stl += float(tot.get('STL', 0))
            t_blk += float(tot.get('BLK', 0))
            t_to  += float(tot.get('TO', 0))
            t_fgm += float(tot.get('FGM', 0))
            t_fga += float(tot.get('FGA', 0))
            t_ftm += float(tot.get('FTM', 0))
            t_fta += float(tot.get('FTA', 0))

    fg_pct = t_fgm / t_fga if t_fga > 0 else 0.0
    ft_pct = t_ftm / t_fta if t_fta > 0 else 0.0

    return {
        "PTS": t_pts, "REB": t_reb, "AST": t_ast, "3PTM": t_tpt,
        "STL": t_stl, "BLK": t_blk, "TO": t_to,
        "FGM": t_fgm, "FGA": t_fga, "FTM": t_ftm, "FTA": t_fta,
        "FG%": fg_pct, "FT%": ft_pct, "GP": played_gp
    }

matchups_by_week = {}
actual_stats_by_team = {}
player_slot_map = {}

for w in range(1, 24):
    w_str = str(w)
    matchups_by_week[w_str] = []
    actual_stats_by_team[w_str] = {}
    
    w_start = start_date_w1 + datetime.timedelta(days=(w-1)*7)
    days_list = []
    day_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    
    for d_idx in range(7):
        curr_d = w_start + datetime.timedelta(days=d_idx)
        date_str = curr_d.strftime("%Y%m%d")
        iso_date = curr_d.strftime("%Y-%m-%d")
        days_list.append({"day_name": day_names[d_idx], "date_str": curr_d.strftime("%b %d").upper(), "iso_date": iso_date})
        
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}"
            resp = requests.get(url, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                for ev in data.get('events', []):
                    for comp in ev.get('competitions', []):
                        competitors = comp.get('competitors', [])
                        if len(competitors) == 2:
                            raw_t1, h1 = competitors[0]['team']['abbreviation'], competitors[0]['homeAway']
                            raw_t2, h2 = competitors[1]['team']['abbreviation'], competitors[1]['homeAway']
                            t1, t2 = normalize_team(raw_t1), normalize_team(raw_t2)
                            global_nba_schedule.setdefault(iso_date, {})
                            if h1 == 'away':
                                global_nba_schedule[iso_date][t1] = f"@{t2}"
                                global_nba_schedule[iso_date][t2] = t1
                            else:
                                global_nba_schedule[iso_date][t2] = f"@{t1}"
                                global_nba_schedule[iso_date][t1] = t2
        except Exception:
            pass

    weeks_config[w_str] = {
        "week_num": w,
        "period_str": f"{w_start.strftime('%b %d')} – {(w_start + datetime.timedelta(days=6)).strftime('%b %d, %Y')}",
        "days": days_list
    }

    seen_pairs = set()
    for team in league.teams:
        t_name = clean_team_name(team.team_name)
        if hasattr(team, 'schedule') and len(team.schedule) >= w:
            opp_obj = team.schedule[w-1]
            opp_name = ""
            if hasattr(opp_obj, 'team_name'):
                opp_name = clean_team_name(opp_obj.team_name)
            elif hasattr(opp_obj, 'home_team') and hasattr(opp_obj, 'away_team'):
                h = clean_team_name(opp_obj.home_team.team_name if hasattr(opp_obj.home_team, 'team_name') else opp_obj.home_team)
                a = clean_team_name(opp_obj.away_team.team_name if hasattr(opp_obj.away_team, 'team_name') else opp_obj.away_team)
                opp_name = a if h == t_name else h
            else:
                raw_str = str(opp_obj)
                for t in league.teams:
                    cleaned_t = clean_team_name(t.team_name)
                    if cleaned_t in raw_str and cleaned_t != t_name:
                        opp_name = cleaned_t
                        break

            if opp_name:
                pair_key = tuple(sorted([t_name, opp_name]))
                if pair_key not in seen_pairs and t_name != opp_name:
                    seen_pairs.add(pair_key)
                    matchups_by_week[w_str].append({"home_team": t_name, "away_team": opp_name})

    try:
        boxes = league.box_scores(matchup_period=w)
        for box in boxes:
            if box.home_team and box.away_team:
                h_name = clean_team_name(box.home_team.team_name if hasattr(box.home_team, 'team_name') else str(box.home_team))
                a_name = clean_team_name(box.away_team.team_name if hasattr(box.away_team, 'team_name') else str(box.away_team))
                actual_stats_by_team[w_str][h_name] = parse_lineup_stats(box.home_lineup)
                actual_stats_by_team[w_str][a_name] = parse_lineup_stats(box.away_lineup)
                
                # 提取當週所有球員在 ESPN 陣容中的 slot_position
                if w == current_week:
                    for bp in (box.home_lineup + box.away_lineup):
                        bp_name_clean = bp.name.strip().lower()
                        slot = getattr(bp, 'slot_position', None) or getattr(bp, 'lineupSlot', 'UTIL')
                        if slot == 'BE':
                            slot = 'Bench'
                        player_slot_map[bp_name_clean] = slot
    except Exception:
        pass

print("🚀 [4/5] Integrating Rosters and Standings...")
teams_sorted = sorted(league.teams, key=lambda x: (x.wins / max(1, x.wins + x.losses)), reverse=True)
team_standings = {clean_team_name(t.team_name): f"{idx+1}{'st' if idx==0 else 'nd' if idx==1 else 'rd' if idx==2 else 'th'} Place" for idx, t in enumerate(teams_sorted)}

teams_data = []
for team in league.teams:
    roster_list = []
    cleaned_team_name = clean_team_name(team.team_name)
    for player in team.roster:
        p_name = player.name
        stats = excel_proj_dict.get(p_name.strip().lower(), {"PTS": 12.0, "REB": 5.0, "AST": 3.0, "3PTM": 1.5, "STL": 1.0, "BLK": 0.5, "FG%": 0.46, "FT%": 0.78, "TO": 1.8, "SCORE": 0.0})
        injury_status = getattr(player, 'injuryStatus', None) or getattr(player, 'status', 'ACTIVE')

        raw_pro_team = getattr(player, 'pro_team', None) or getattr(player, 'proTeam', None)
        lower_pname = p_name.strip().lower()
        mapped_key = EXACT_NAME_ALIAS.get(lower_pname, lower_pname)

        if not raw_pro_team or str(raw_pro_team).upper() in ['FA', 'NONE', 'NAN']:
            pro_team = player_team_map.get(mapped_key, 'OKC')
        else:
            pro_team = normalize_team(raw_pro_team)

        pos_raw = getattr(player, 'eligibleSlots', None) or getattr(player, 'eligible_positions', None) or getattr(player, 'position', None)
        pos_str = excel_proj_dict.get(mapped_key, {}).get("position", clean_positions(pos_raw))

        # 讀取 ESPN 陣容即時 Slot Position (如 PG, SG, Bench, IR, UTIL)
        raw_slot = player_slot_map.get(
            lower_pname,
            getattr(player, 'slot_position', getattr(player, 'lineupSlot', 'UTIL'))
        )
        slot_pos = 'Bench' if raw_slot == 'BE' else (raw_slot if raw_slot else 'UTIL')
        is_bench = (slot_pos == 'Bench' or slot_pos == 'BE')

        schedules_by_week = {}
        for w_str, w_info in weeks_config.items():
            w_sched = {}
            for d_info in w_info["days"]:
                day_name = d_info["day_name"]
                iso_date = d_info["iso_date"]
                opp = global_nba_schedule.get(iso_date, {}).get(pro_team, None)
                w_sched[day_name] = opp
            schedules_by_week[w_str] = w_sched

        roster_list.append({
            "name": p_name,
            "position": pos_str,
            "slot_position": slot_pos,
            "isBench": is_bench,
            "proTeam": pro_team,
            "injuryStatus": injury_status,
            "stats": stats,
            "schedules_by_week": schedules_by_week
        })
        
    teams_data.append({
        "team_id": team.team_id,
        "team_name": cleaned_team_name,
        "wins": team.wins,
        "losses": team.losses,
        "record": f"{team.wins}-{team.losses}",
        "standing": team_standings.get(cleaned_team_name, "6th Place"),
        "roster": roster_list
    })

full_data = {
    "league_info": {
        "name": league.settings.name,
        "current_week": current_week,
        "team_count": len(league.teams)
    },
    "my_team_name": "Novel Fergus",
    "stats_meta": stats_meta,
    "team_top10_averages_meta": {},
    "all_projections": excel_proj_dict,
    "all_player_names": sorted(all_player_names),
    "weeks_config": weeks_config,
    "global_nba_schedule": global_nba_schedule,
    "teams": teams_data,
    "matchups_by_week": matchups_by_week,
    "actual_stats_by_team": actual_stats_by_team
}

print("🚀 [5/5] Compiling and Writing to data.json...")
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(full_data, f, ensure_ascii=False)

print("✅ SUCCESS! data.json generated successfully from Google Sheets & ESPN API.")

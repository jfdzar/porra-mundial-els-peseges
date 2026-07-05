#!/usr/bin/env python3
"""Fetch finished World Cup matches from Zafronix and update data.json.

Source endpoints:
- https://api.zafronix.com/live-feed/predictions (contains final results + upcoming)
- Fallback: https://api.zafronix.com/live-feed (live/recentlyFinished/upcoming)

The web app uses Spanish team names from the porra template, so this script maps
Zafronix English names to those names, merges actual scores, and calculates:
- hit_1x2: predicted local/draw/away winner correctly
- hit_exact: predicted exact score correctly
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / 'data.json'
RESULTS_PATH = HERE / 'actual_results.json'
ZAFRONIX_PREDICTIONS = 'https://api.zafronix.com/live-feed/predictions'
ZAFRONIX_LIVE = 'https://api.zafronix.com/live-feed'

TEAM_ALIASES = {
    'Algeria': 'Argelia',
    'Argentina': 'Argentina',
    'Australia': 'Australia',
    'Austria': 'Austria',
    'Belgium': 'Bélgica',
    'Bosnia and Herzegovina': 'Bosnia y Herzegovina',
    'Brazil': 'Brasil',
    'Cabo Verde': 'Cabo Verde',
    'Canada': 'Canadá',
    'Colombia': 'Colombia',
    "Côte d'Ivoire": 'Costa de Marfil',
    'Congo DR': 'RD Congo',
    'Croatia': 'Croacia',
    'Curaçao': 'Curazao',
    'Czechia': 'República Checa',
    'DR Congo': 'RD Congo',
    'Ecuador': 'Ecuador',
    'Egypt': 'Egipto',
    'England': 'Inglaterra',
    'France': 'Francia',
    'Germany': 'Alemania',
    'Ghana': 'Ghana',
    'Haiti': 'Haití',
    'Iran': 'Irán',
    'IR Iran': 'Irán',
    'Iraq': 'Irak',
    'Japan': 'Japón',
    'Jordan': 'Jordania',
    'Korea Republic': 'Corea del Sur',
    'Mexico': 'México',
    'Morocco': 'Marruecos',
    'Netherlands': 'Países Bajos',
    'New Zealand': 'Nueva Zelanda',
    'Norway': 'Noruega',
    'Panama': 'Panamá',
    'Paraguay': 'Paraguay',
    'Portugal': 'Portugal',
    'Qatar': 'Catar',
    'Saudi Arabia': 'Arabia Saudita',
    'Scotland': 'Escocia',
    'Senegal': 'Senegal',
    'South Africa': 'Sudáfrica',
    'Spain': 'España',
    'Sweden': 'Suecia',
    'Switzerland': 'Suiza',
    'Tunisia': 'Túnez',
    'Türkiye': 'Turquía',
    'Turkey': 'Turquía',
    'Uruguay': 'Uruguay',
    'USA': 'Estados Unidos',
    'United States': 'Estados Unidos',
    'Uzbekistan': 'Uzbekistán',
}


def fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 PorraMundial/1.0',
            'Accept': 'application/json',
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))


GROUP_POINTS_1X2 = 4
GROUP_POINTS_EXACT = 2
KNOCKOUT_SCORING = {
    'Dieciseisavos': {'next_round': 'Octavos', 'team': 7, 'sign': 3, 'exact': 2},
    'Octavos': {'next_round': 'Cuartos', 'team': 10, 'sign': 4, 'exact': 3},
    'Cuartos': {'next_round': 'Semifinales', 'team': 15, 'sign': 7, 'exact': 6},
    'Semifinales': {'next_round': 'Final', 'team': 20, 'sign': 9, 'exact': 8},
    '3º/4º puesto': {'next_round': None, 'team': 0, 'sign': 10, 'exact': 9},
    'Final': {'next_round': None, 'team': 0, 'sign': 13, 'exact': 12},
}


def pair_key(home, away):
    return sorted([home, away])


def predicted_sign_and_score_for_actual(prediction, actual_home, actual_away):
    """Return predicted sign/result in actual match orientation, or (None, None)."""
    if not prediction.get('local') or not prediction.get('visitante'):
        return None, None
    if pair_key(prediction.get('local'), prediction.get('visitante')) != pair_key(actual_home, actual_away):
        return None, None
    gl = prediction.get('goles_local')
    gv = prediction.get('goles_visitante')
    if gl is None or gv is None:
        return None, None
    if prediction.get('local') == actual_home and prediction.get('visitante') == actual_away:
        home_goals, away_goals = int(gl), int(gv)
    else:
        home_goals, away_goals = int(gv), int(gl)
    return result_sign(home_goals, away_goals), f'{home_goals}-{away_goals}'

def result_sign(home_goals, away_goals):
    if home_goals > away_goals:
        return '1'
    if home_goals == away_goals:
        return 'X'
    return '2'


def spanish_name(name):
    return TEAM_ALIASES.get(name, name)


def partido_key(home, away):
    return f'{spanish_name(home)}-{spanish_name(away)}'


def zafronix_winner_name(result, home, away):
    winner = result.get('winner')
    if winner == 'home':
        return spanish_name(home)
    if winner == 'away':
        return spanish_name(away)
    penalties = result.get('penalties') or {}
    if penalties.get('home') is not None and penalties.get('away') is not None:
        if int(penalties['home']) > int(penalties['away']):
            return spanish_name(home)
        if int(penalties['away']) > int(penalties['home']):
            return spanish_name(away)
    home_score = result.get('homeScore')
    away_score = result.get('awayScore')
    if home_score is not None and away_score is not None:
        if int(home_score) > int(away_score):
            return spanish_name(home)
        if int(away_score) > int(home_score):
            return spanish_name(away)
    return None


def collect_finished_results():
    results = {}
    source_payload = fetch_json(ZAFRONIX_PREDICTIONS)
    for item in source_payload.get('items', []):
        result = item.get('result') or {}
        status = (item.get('status') or result.get('status') or '').lower()
        if status not in {'final', 'finished'}:
            continue
        if 'homeScore' not in result or 'awayScore' not in result:
            continue
        home = item.get('home', {}).get('name')
        away = item.get('away', {}).get('name')
        if not home or not away:
            continue
        results[partido_key(home, away)] = {
            'local': spanish_name(home),
            'visitante': spanish_name(away),
            'goles_local': int(result['homeScore']),
            'goles_visitante': int(result['awayScore']),
            'winner': zafronix_winner_name(result, home, away),
            'penalties': result.get('penalties'),
            'source': ZAFRONIX_PREDICTIONS,
            'zafronix_match_no': item.get('matchNo'),
            'zafronix_label': item.get('label'),
            'zafronix_as_of': source_payload.get('asOf'),
        }

    # Fallback/extra source for recently finished matches only.
    # Do NOT import the `live` section: those scores are provisional while
    # the match is still in play and must not count in the standings.
    live_payload = fetch_json(ZAFRONIX_LIVE)
    for item in live_payload.get('recentlyFinished', []):
        if item.get('homeScore') is None or item.get('awayScore') is None:
            continue
        if (item.get('status') or '').lower() not in {'finished', 'final'}:
            continue
        key = partido_key(item.get('homeTeam'), item.get('awayTeam'))
        home_team = item.get('homeTeam')
        away_team = item.get('awayTeam')
        results.setdefault(key, {
            'local': spanish_name(home_team),
            'visitante': spanish_name(away_team),
            'goles_local': int(item['homeScore']),
            'goles_visitante': int(item['awayScore']),
            'winner': zafronix_winner_name({
                'homeScore': item.get('homeScore'),
                'awayScore': item.get('awayScore'),
                'winner': item.get('winner'),
                'penalties': item.get('penalties'),
            }, home_team, away_team),
            'penalties': item.get('penalties'),
            'source': ZAFRONIX_LIVE,
            'zafronix_match_no': item.get('matchNo'),
            'zafronix_label': item.get('matchId'),
            'zafronix_as_of': live_payload.get('asOf'),
        })
    return results


def result_points_for_match(match):
    gl = int(match['actual_goles_local'])
    gv = int(match['actual_goles_visitante'])
    if gl > gv:
        return 3, 0
    if gl < gv:
        return 0, 3
    return 1, 1


def rank_group_played(matches):
    table = {}
    for match in matches:
        for team in (match['local'], match['visitante']):
            table.setdefault(team, {'team': team, 'pts': 0, 'gf': 0, 'ga': 0, 'gd': 0})
        if not match.get('played'):
            continue
        gl = int(match['actual_goles_local'])
        gv = int(match['actual_goles_visitante'])
        home = table[match['local']]
        away = table[match['visitante']]
        home['gf'] += gl; home['ga'] += gv
        away['gf'] += gv; away['ga'] += gl
        hp, ap = result_points_for_match(match)
        home['pts'] += hp; away['pts'] += ap
    for row in table.values():
        row['gd'] = row['gf'] - row['ga']
    return sorted(table.values(), key=lambda r: (-r['pts'], -r['gd'], -r['gf'], r['team'].casefold()))


def guaranteed_top2_by_points(matches):
    """Return teams already guaranteed top-2 in a group.

    Third-place qualification is intentionally NOT evaluated here, per Juan's
    instruction, because best thirds cannot be known until enough groups finish.
    For completed groups we use the actual ranked top 2. For incomplete groups
    we only award teams that are top-2 in every W/D/L completion by points.
    """
    teams = sorted({m['local'] for m in matches} | {m['visitante'] for m in matches})
    ranking = rank_group_played(matches)
    remaining = [m for m in matches if not m.get('played')]
    if not remaining:
        return [r['team'] for r in ranking[:2]]

    base = {r['team']: r['pts'] for r in ranking}
    guaranteed = []
    for team in teams:
        ok = True
        # Outcomes: 0 home win, 1 draw, 2 away win. We only need points; exact
        # score/tiebreaks are not safe for future matches, so tied cutoffs are
        # treated conservatively.
        for outcomes in __import__('itertools').product((0, 1, 2), repeat=len(remaining)):
            pts = dict(base)
            for match, outcome in zip(remaining, outcomes):
                if outcome == 0:
                    pts[match['local']] += 3
                elif outcome == 1:
                    pts[match['local']] += 1
                    pts[match['visitante']] += 1
                else:
                    pts[match['visitante']] += 3
            better = sum(1 for other in teams if pts[other] > pts[team])
            tied_or_better = sum(1 for other in teams if pts[other] >= pts[team])
            if better > 1 or tied_or_better > 2:
                ok = False
                break
        if ok:
            guaranteed.append(team)
    return guaranteed


def current_r32_qualified_top2(group_matches):
    by_group = {}
    for match in group_matches:
        by_group.setdefault(match['grupo'], []).append(match)
    qualified = []
    by_group_out = {}
    for group, matches in sorted(by_group.items()):
        teams = guaranteed_top2_by_points(matches)
        by_group_out[group] = teams
        qualified.extend(teams)
    return sorted(set(qualified)), by_group_out


def current_r32_qualified_teams(group_matches):
    """Return currently scorable R32 qualified teams.

    Before all groups finish, only guaranteed top-2 teams are safe. Once every
    group is complete, add the eight best third-place teams.
    """
    by_group = {}
    for match in group_matches:
        by_group.setdefault(match['grupo'], []).append(match)
    if not by_group or not all(all(match.get('played') for match in matches) for matches in by_group.values()):
        return current_r32_qualified_top2(group_matches)

    qualified = []
    by_group_out = {}
    thirds = []
    for group, matches in sorted(by_group.items()):
        ranking = rank_group_played(matches)
        teams = [ranking[0]['team'], ranking[1]['team']]
        by_group_out[group] = teams
        qualified.extend(teams)
        third = dict(ranking[2])
        third['group'] = group
        thirds.append(third)
    best_thirds = sorted(thirds, key=lambda r: (-r['pts'], -r['gd'], -r['gf'], r['team'].casefold()))[:8]
    for row in best_thirds:
        by_group_out[row['group']].append(row['team'])
        qualified.append(row['team'])
    return sorted(set(qualified)), by_group_out


OCTAVOS_MATCHNO_BY_PREDICTION_ORDER = {
    # The prediction copy-row order has the first two Octavos slots swapped
    # relative to Zafronix/FIFA match numbers: row 89 predicts Canada-Morocco
    # (actual match 90), while row 90 predicts the France-side match (actual 89).
    89: 90,
    90: 89,
}

MATCHUP_POINTS_BY_ROUND = {
    'Octavos': 3,
    'Cuartos': 6,
    'Semifinales': 8,
    '3º/4º puesto': 9,
    'Final': 12,
}

R32_MATCHNO_BY_PREDICTION_ORDER = {
    73: 73, 74: 76, 75: 74, 76: 75,
    77: 78, 78: 77, 79: 79, 80: 80,
    81: 82, 82: 81, 83: 84, 84: 83,
    85: 85, 86: 88, 87: 86, 88: 87,
}

R32_BRACKET_DEFS = [
    (73, '2A', '2B'),
    (74, '1E', '3D'),
    (75, '1F', '2C'),
    (76, '1C', '2F'),
    (77, '1I', '3F'),
    (78, '2E', '2I'),
    (79, '1A', '3E'),
    (80, '1L', '3K'),
    (81, '1D', '3B'),
    (82, '1G', '3I'),
    (83, '2K', '2L'),
    (84, '1H', '2J'),
    (85, '1B', '3J'),
    (86, '1J', '2H'),
    (87, '1K', '3L'),
    (88, '2D', '2G'),
]


def current_r32_matchups(group_matches):
    by_group = {}
    for match in group_matches:
        by_group.setdefault(match['grupo'], []).append(match)
    if not by_group or not all(all(match.get('played') for match in matches) for matches in by_group.values()):
        return {}
    positions = {group: [row['team'] for row in rank_group_played(matches)] for group, matches in by_group.items()}
    matchups = {}
    def team_for(code):
        pos = int(code[0]) - 1
        group = code[1]
        return positions[group][pos]
    for match_no, left, right in R32_BRACKET_DEFS:
        home = team_for(left)
        away = team_for(right)
        matchups[match_no] = {'home': home, 'away': away, 'teams': sorted([home, away])}
    return matchups


def completed_group_positions(group_matches):
    by_group = {}
    for match in group_matches:
        by_group.setdefault(match['grupo'], []).append(match)
    positions = {}
    for group, matches in sorted(by_group.items()):
        if matches and all(match.get('played') for match in matches):
            positions[group] = [row['team'] for row in rank_group_played(matches)]
    return positions


def predicted_group_positions_by_person(data):
    out = {}
    for summary in data.get('knockout_summaries', []):
        positions = summary.get('group_positions') or {}
        if positions:
            out[summary['persona']] = positions
    return out


def predicted_r32_teams_by_person(data):
    out = {}
    for summary in data.get('knockout_summaries', []):
        teams = summary.get('r32_qualified_teams') or []
        if teams:
            out[summary['persona']] = set(teams)
    for prediction in data['predictions']:
        if not prediction.get('is_knockout') or prediction.get('jornada') != 'Dieciseisavos':
            continue
        teams = out.setdefault(prediction['persona'], set())
        if prediction.get('local'):
            teams.add(prediction['local'])
        if prediction.get('visitante'):
            teams.add(prediction['visitante'])
    return out


def collect_known_knockout_fixtures():
    """Return known Zafronix knockout fixtures, including scheduled future games.

    Finished results are still imported separately; this only keeps the public
    bracket/team labels aligned with Zafronix so exact matchup points for later
    rounds can be calculated as soon as a fixture is known.
    """
    fixtures = {}
    live_payload = fetch_json(ZAFRONIX_LIVE)
    for section in ('recentlyFinished', 'live', 'upcoming'):
        for item in live_payload.get(section, []):
            match_no = item.get('matchNo')
            home = item.get('homeTeam')
            away = item.get('awayTeam')
            if match_no is None or not home or not away:
                continue
            if int(match_no) < 73:
                continue
            fixtures[int(match_no)] = {
                'local': spanish_name(home),
                'visitante': spanish_name(away),
                'source': ZAFRONIX_LIVE,
            }
    return fixtures


def merge_results(data, actual_results, known_knockout_fixtures=None):
    # Only real group-stage fixtures should be scored for match result points.
    known_knockout_fixtures = known_knockout_fixtures or {}
    group_matches = [m for m in data['matches'] if not m.get('is_knockout')]
    all_known_partidos = {m['partido'] for m in data['matches']}
    known_partidos = {m['partido'] for m in group_matches}
    results_by_match_no = {
        int(v['zafronix_match_no']): v
        for v in actual_results.values()
        if v.get('zafronix_match_no') is not None
    }
    unknown = sorted(
        key for key, result in actual_results.items()
        if key not in all_known_partidos and result.get('zafronix_match_no') not in {m.get('chronological_order') for m in data['matches']}
    )
    if unknown:
        print('Aviso: resultados de Zafronix no encontrados en la porra:')
        for key in unknown:
            print(f'  - {key}')

    valid_results = {k: v for k, v in actual_results.items() if k in known_partidos}

    for match in data['matches']:
        if match.get('is_knockout'):
            actual = results_by_match_no.get(int(match.get('chronological_order') or 0)) or actual_results.get(match['partido'])
            if actual:
                gl = int(actual['goles_local'])
                gv = int(actual['goles_visitante'])
                match['local'] = actual.get('local') or match['local']
                match['visitante'] = actual.get('visitante') or match['visitante']
                match['partido'] = f"{match['local']}-{match['visitante']}"
                match['played'] = True
                match['actual_goles_local'] = gl
                match['actual_goles_visitante'] = gv
                match['actual_resultado'] = f'{gl}-{gv}'
                match['actual_signo'] = result_sign(gl, gv)
                match['actual_winner'] = actual.get('winner')
                match['actual_penalties'] = actual.get('penalties')
                match['actual_source'] = actual.get('source', 'zafronix')
            else:
                fixture = known_knockout_fixtures.get(int(match.get('chronological_order') or 0))
                if fixture:
                    match['local'] = fixture['local']
                    match['visitante'] = fixture['visitante']
                    match['partido'] = f"{match['local']}-{match['visitante']}"
                match['played'] = False
                match['actual_goles_local'] = None
                match['actual_goles_visitante'] = None
                match['actual_resultado'] = None
                match['actual_signo'] = None
                match['actual_winner'] = None
                match['actual_penalties'] = None
                match['actual_source'] = None
            continue
        actual = valid_results.get(match['partido'])
        if actual:
            gl = int(actual['goles_local'])
            gv = int(actual['goles_visitante'])
            match['played'] = True
            match['actual_goles_local'] = gl
            match['actual_goles_visitante'] = gv
            match['actual_resultado'] = f'{gl}-{gv}'
            match['actual_signo'] = result_sign(gl, gv)
            match['actual_winner'] = actual.get('winner')
            match['actual_penalties'] = actual.get('penalties')
            match['actual_source'] = actual.get('source', 'zafronix')
        else:
            match['played'] = False
            match['actual_goles_local'] = None
            match['actual_goles_visitante'] = None
            match['actual_resultado'] = None
            match['actual_signo'] = None
            match['actual_winner'] = None
            match['actual_penalties'] = None
            match['actual_source'] = None

    matches_by_name = {m['partido']: m for m in group_matches}
    knockout_matches_by_order = {int(m['chronological_order']): m for m in data['matches'] if m.get('is_knockout')}
    for prediction in data['predictions']:
        if prediction.get('is_knockout'):
            prediction_order = int(prediction.get('chronological_order') or 0)
            if prediction.get('jornada') == 'Dieciseisavos':
                actual_order = R32_MATCHNO_BY_PREDICTION_ORDER.get(prediction_order, prediction_order)
            elif prediction.get('jornada') == 'Octavos':
                actual_order = OCTAVOS_MATCHNO_BY_PREDICTION_ORDER.get(prediction_order, prediction_order)
            else:
                actual_order = prediction_order
            actual_match = knockout_matches_by_order.get(actual_order)
            prediction['played'] = bool(actual_match and actual_match.get('played'))
            prediction['actual_resultado'] = actual_match.get('actual_resultado') if prediction['played'] else None
            prediction['actual_signo'] = actual_match.get('actual_signo') if prediction['played'] else None
            prediction['hit_1x2'] = False if prediction['played'] else None
            prediction['hit_exact'] = False if prediction['played'] else None
            prediction['points_1x2'] = 0
            prediction['points_exact'] = 0
            prediction['points_total'] = 0
            if prediction['played']:
                pred_sign, pred_result = predicted_sign_and_score_for_actual(prediction, actual_match['local'], actual_match['visitante'])
                if pred_sign is not None:
                    prediction['hit_1x2'] = pred_sign == actual_match['actual_signo']
                    prediction['hit_exact'] = pred_result == actual_match['actual_resultado']
                    scoring = KNOCKOUT_SCORING.get(prediction.get('jornada'), {})
                    prediction['points_1x2'] = int(scoring.get('sign', 0)) if prediction['hit_1x2'] else 0
                    prediction['points_exact'] = int(scoring.get('exact', 0)) if prediction['hit_exact'] else 0
                    prediction['points_total'] = prediction['points_1x2'] + prediction['points_exact']
            continue
        match = matches_by_name[prediction['partido']]
        prediction['played'] = match['played']
        prediction['actual_resultado'] = match['actual_resultado']
        prediction['actual_signo'] = match['actual_signo']
        if match['played']:
            prediction['hit_1x2'] = prediction['signo'] == match['actual_signo']
            prediction['hit_exact'] = prediction['resultado'] == match['actual_resultado']
            prediction['points_1x2'] = GROUP_POINTS_1X2 if prediction['hit_1x2'] else 0
            prediction['points_exact'] = GROUP_POINTS_EXACT if prediction['hit_exact'] else 0
            prediction['points_total'] = prediction['points_1x2'] + prediction['points_exact']
        else:
            prediction['hit_1x2'] = None
            prediction['hit_exact'] = None
            prediction['points_1x2'] = 0
            prediction['points_exact'] = 0
            prediction['points_total'] = 0

    qualified_teams, qualified_by_group = current_r32_qualified_teams(group_matches)
    r32_matchups = current_r32_matchups(group_matches)
    completed_positions_by_group = completed_group_positions(group_matches)
    predicted_positions_by_person = predicted_group_positions_by_person(data)
    predicted_qualified_by_person = predicted_r32_teams_by_person(data)

    standings = {}
    for prediction in data['predictions']:
        if prediction.get('is_knockout'):
            continue
        person = prediction['persona']
        row = standings.setdefault(person, {
            'persona': person,
            'points': 0,
            'played': 0,
            'hits_1x2': 0,
            'hits_exact': 0,
            'points_1x2': 0,
            'points_exact': 0,
            'points_group_positions': 0,
            'hits_group_positions': 0,
            'matched_group_positions': [],
            'points_qualified_r32': 0,
            'hits_qualified_r32': 0,
            'matched_qualified_r32': [],
            'points_r32_matchups': 0,
            'hits_r32_matchups': 0,
            'matched_r32_matchups': [],
        })
        if prediction.get('played'):
            row['played'] += 1
            row['hits_1x2'] += int(bool(prediction.get('hit_1x2')))
            row['hits_exact'] += int(bool(prediction.get('hit_exact')))
            row['points_1x2'] += int(prediction.get('points_1x2') or 0)
            row['points_exact'] += int(prediction.get('points_exact') or 0)
            row['points'] += int(prediction.get('points_total') or 0)

    for person, predicted_positions in predicted_positions_by_person.items():
        row = standings.setdefault(person, {
            'persona': person,
            'points': 0,
            'played': 0,
            'hits_1x2': 0,
            'hits_exact': 0,
            'points_1x2': 0,
            'points_exact': 0,
            'points_group_positions': 0,
            'hits_group_positions': 0,
            'matched_group_positions': [],
            'points_qualified_r32': 0,
            'hits_qualified_r32': 0,
            'matched_qualified_r32': [],
            'points_r32_matchups': 0,
            'hits_r32_matchups': 0,
            'matched_r32_matchups': [],
        })
        matched_positions = []
        for group, actual_positions in completed_positions_by_group.items():
            predicted_group = predicted_positions.get(group, [])
            for index, actual_team in enumerate(actual_positions):
                if index < len(predicted_group) and predicted_group[index] == actual_team:
                    matched_positions.append(f'{group}{index + 1}:{actual_team}')
        row['hits_group_positions'] = len(matched_positions)
        row['points_group_positions'] = 2 * len(matched_positions)
        row['matched_group_positions'] = matched_positions
        row['points'] += row['points_group_positions']

    for person, predicted_teams in predicted_qualified_by_person.items():
        row = standings.setdefault(person, {
            'persona': person,
            'points': 0,
            'played': 0,
            'hits_1x2': 0,
            'hits_exact': 0,
            'points_1x2': 0,
            'points_exact': 0,
            'points_group_positions': 0,
            'hits_group_positions': 0,
            'matched_group_positions': [],
            'points_qualified_r32': 0,
            'hits_qualified_r32': 0,
            'matched_qualified_r32': [],
            'points_r32_matchups': 0,
            'hits_r32_matchups': 0,
            'matched_r32_matchups': [],
        })
        matched = sorted(set(qualified_teams) & set(predicted_teams))
        row['hits_qualified_r32'] = len(matched)
        row['points_qualified_r32'] = 4 * len(matched)
        row['matched_qualified_r32'] = matched
        row['points'] += row['points_qualified_r32']

    if r32_matchups:
        for prediction in data['predictions']:
            if not prediction.get('is_knockout') or prediction.get('jornada') != 'Dieciseisavos':
                continue
            person = prediction['persona']
            row = standings.get(person)
            if not row:
                continue
            match_no = R32_MATCHNO_BY_PREDICTION_ORDER.get(int(prediction.get('chronological_order') or 0))
            actual = r32_matchups.get(match_no)
            if not actual:
                continue
            predicted_pair = sorted([prediction.get('local'), prediction.get('visitante')])
            if predicted_pair == actual['teams']:
                row['hits_r32_matchups'] += 1
                row['matched_r32_matchups'].append(f"{match_no}:{actual['home']}-{actual['away']}")
        for row in standings.values():
            row['points_r32_matchups'] = 2 * row['hits_r32_matchups']
            row['points'] += row['points_r32_matchups']

    known_fixture_orders = set(known_knockout_fixtures)
    knockout_matchups = {
        int(m.get('chronological_order') or 0): m
        for m in data['matches']
        if m.get('is_knockout')
        and m.get('jornada') in MATCHUP_POINTS_BY_ROUND
        and m.get('local')
        and m.get('visitante')
        and (m.get('played') or int(m.get('chronological_order') or 0) in known_fixture_orders)
    }
    if knockout_matchups:
        for row in standings.values():
            row.setdefault('points_knockout_matchups', 0)
            row.setdefault('hits_knockout_matchups', 0)
            row.setdefault('matched_knockout_matchups', [])
        for prediction in data['predictions']:
            if not prediction.get('is_knockout') or prediction.get('jornada') not in MATCHUP_POINTS_BY_ROUND:
                continue
            prediction_order = int(prediction.get('chronological_order') or 0)
            if prediction.get('jornada') == 'Octavos':
                actual_order = OCTAVOS_MATCHNO_BY_PREDICTION_ORDER.get(prediction_order, prediction_order)
            else:
                actual_order = prediction_order
            actual = knockout_matchups.get(actual_order)
            if not actual:
                continue
            predicted_pair = sorted([prediction.get('local'), prediction.get('visitante')])
            actual_pair = sorted([actual.get('local'), actual.get('visitante')])
            if predicted_pair == actual_pair:
                row = standings.get(prediction['persona'])
                if not row:
                    continue
                points = int(MATCHUP_POINTS_BY_ROUND[prediction.get('jornada')])
                row['hits_knockout_matchups'] += 1
                row['points_knockout_matchups'] += points
                row['points'] += points
                row['matched_knockout_matchups'].append(f"{actual_order}:{actual['local']}-{actual['visitante']}")

    knockout_played = [m for m in data['matches'] if m.get('is_knockout') and m.get('played')]
    if knockout_played:
        for row in standings.values():
            row.setdefault('points_knockout_teams', 0)
            row.setdefault('hits_knockout_teams', 0)
            row.setdefault('matched_knockout_teams', [])
            row.setdefault('points_knockout_results', 0)
            row.setdefault('hits_knockout_1x2', 0)
            row.setdefault('hits_knockout_exact', 0)
            row.setdefault('matched_knockout_results', [])

        predictions_by_person = {}
        for prediction in data['predictions']:
            if prediction.get('is_knockout'):
                predictions_by_person.setdefault(prediction['persona'], []).append(prediction)

        for match in knockout_played:
            scoring = KNOCKOUT_SCORING.get(match.get('jornada'), {})
            gl = int(match['actual_goles_local'])
            gv = int(match['actual_goles_visitante'])
            if gl == gv:
                winner = match.get('actual_winner')
            else:
                winner = match['local'] if gl > gv else match['visitante']
            next_round = scoring.get('next_round')
            team_points = int(scoring.get('team', 0) or 0)
            for person, person_predictions in predictions_by_person.items():
                row = standings.get(person)
                if not row:
                    continue
                if winner and next_round and team_points:
                    next_round_teams = {
                        team
                        for pr in person_predictions
                        if pr.get('jornada') == next_round
                        for team in (pr.get('local'), pr.get('visitante'))
                        if team
                    }
                    if winner in next_round_teams:
                        row['hits_knockout_teams'] += 1
                        row['points_knockout_teams'] += team_points
                        row['points'] += team_points
                        row['matched_knockout_teams'].append(f"{next_round}:{winner}")

        for prediction in data['predictions']:
            if not prediction.get('is_knockout') or not prediction.get('played'):
                continue
            row = standings.get(prediction['persona'])
            if not row:
                continue
            points_total = int(prediction.get('points_total') or 0)
            if points_total:
                row['points_knockout_results'] += points_total
                row['points'] += points_total
                row['hits_knockout_1x2'] += int(bool(prediction.get('hit_1x2')))
                row['hits_knockout_exact'] += int(bool(prediction.get('hit_exact')))
                row['hits_1x2'] += int(bool(prediction.get('hit_1x2')))
                row['hits_exact'] += int(bool(prediction.get('hit_exact')))
                row['matched_knockout_results'].append(f"{prediction.get('chronological_order')}:{prediction.get('partido')}")

    ranking = sorted(standings.values(), key=lambda r: (-r['points'], -r['hits_exact'], -r['hits_1x2'], -r['hits_group_positions'], -r['hits_qualified_r32'], -r['hits_r32_matchups'], r['persona'].casefold()))
    for pos, row in enumerate(ranking, start=1):
        row['position'] = pos
    data['standings'] = ranking
    data['scoring'] = {
        'group_stage': {
            'sign_1x2': GROUP_POINTS_1X2,
            'exact_result': GROUP_POINTS_EXACT,
            'note': 'Fase de grupos: 4 puntos por acertar signo 1X2 y 2 puntos adicionales por resultado exacto.'
        },
        'group_positions_current': {
            'exact_position': 2,
            'completed_group_positions': completed_positions_by_group,
            'note': 'Puntos por posición exacta 1º-4º solo en grupos ya completados.'
        },
        'round_of_32_qualification_current': {
            'team_qualified': 4,
            'qualified_teams': qualified_teams,
            'qualified_by_group': qualified_by_group,
            'note': 'Puntos actuales por equipos clasificados a dieciseisavos. Antes de cerrar todos los grupos solo se evalúan top 2; con todos los grupos completos se incluyen los ocho mejores terceros.'
        },
        'round_of_32_matchups_current': {
            'exact_matchup': 2,
            'matchups': r32_matchups,
            'prediction_order_to_match_no': R32_MATCHNO_BY_PREDICTION_ORDER,
            'note': 'Cruces exactos de 1/16: 2 puntos por acertar el emparejamiento exacto en su número de partido.'
        },
        'knockout_matchups_current': {
            'exact_matchup_by_round': MATCHUP_POINTS_BY_ROUND,
            'matchups': {
                str(order): {
                    'jornada': match.get('jornada'),
                    'home': match.get('local'),
                    'away': match.get('visitante'),
                    'played': bool(match.get('played')),
                }
                for order, match in sorted(knockout_matchups.items())
            },
            'octavos_prediction_order_to_match_no': OCTAVOS_MATCHNO_BY_PREDICTION_ORDER,
            'note': 'Cruces exactos de eliminatorias posteriores: puntos por acertar el emparejamiento exacto cuando Zafronix ya ha definido el partido.'
        },
        'knockout_results_current': {
            'scoring': KNOCKOUT_SCORING,
            'played_matches': [m for m in data['matches'] if m.get('is_knockout') and m.get('played')],
            'note': 'Puntos actuales de eliminatorias: equipos que alcanzan la siguiente ronda, signo y resultado exacto cuando el cruce del participante coincide con el cruce real.'
        }
    }

    data['actualResults'] = actual_results
    data['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    data['actual_results_source'] = 'zafronix'
    return len([m for m in data['matches'] if m.get('played')])


def main():
    data = json.loads(DATA_PATH.read_text(encoding='utf-8'))
    # Preserve previously imported final results if the upstream feed temporarily
    # omits older matches. Zafronix can roll historical items out of the current
    # predictions payload; dropping them would incorrectly remove points.
    previous_results = json.loads(RESULTS_PATH.read_text(encoding='utf-8')) if RESULTS_PATH.exists() else {}
    actual_results = {**previous_results, **collect_finished_results()}
    known_knockout_fixtures = collect_known_knockout_fixtures()
    count = merge_results(data, actual_results, known_knockout_fixtures)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    RESULTS_PATH.write_text(json.dumps(actual_results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Actualizados {count} partidos finalizados desde Zafronix')
    for partido, result in sorted(actual_results.items(), key=lambda kv: kv[1].get('zafronix_match_no') or 9999):
        print(f"- {partido}: {result['goles_local']}-{result['goles_visitante']}")


if __name__ == '__main__':
    main()

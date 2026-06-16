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
            'goles_local': int(result['homeScore']),
            'goles_visitante': int(result['awayScore']),
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
        results.setdefault(key, {
            'goles_local': int(item['homeScore']),
            'goles_visitante': int(item['awayScore']),
            'source': ZAFRONIX_LIVE,
            'zafronix_match_no': item.get('matchNo'),
            'zafronix_label': item.get('matchId'),
            'zafronix_as_of': live_payload.get('asOf'),
        })
    return results


def merge_results(data, actual_results):
    # Only real group-stage fixtures should be scored right now. Knockout rows
    # are participant-specific projected brackets, so they must remain visible
    # but unscored until Juan defines knockout scoring rules.
    group_matches = [m for m in data['matches'] if not m.get('is_knockout')]
    known_partidos = {m['partido'] for m in group_matches}
    unknown = sorted(set(actual_results) - known_partidos)
    if unknown:
        print('Aviso: resultados de Zafronix no encontrados en la fase de grupos de la porra:')
        for key in unknown:
            print(f'  - {key}')

    valid_results = {k: v for k, v in actual_results.items() if k in known_partidos}

    for match in data['matches']:
        if match.get('is_knockout'):
            match['played'] = False
            match['actual_goles_local'] = None
            match['actual_goles_visitante'] = None
            match['actual_resultado'] = None
            match['actual_signo'] = None
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
            match['actual_source'] = actual.get('source', 'zafronix')
        else:
            match['played'] = False
            match['actual_goles_local'] = None
            match['actual_goles_visitante'] = None
            match['actual_resultado'] = None
            match['actual_signo'] = None
            match['actual_source'] = None

    matches_by_name = {m['partido']: m for m in group_matches}
    for prediction in data['predictions']:
        if prediction.get('is_knockout'):
            prediction['played'] = False
            prediction['actual_resultado'] = None
            prediction['actual_signo'] = None
            prediction['hit_1x2'] = None
            prediction['hit_exact'] = None
            prediction['points_1x2'] = 0
            prediction['points_exact'] = 0
            prediction['points_total'] = 0
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
        })
        if prediction.get('played'):
            row['played'] += 1
            row['hits_1x2'] += int(bool(prediction.get('hit_1x2')))
            row['hits_exact'] += int(bool(prediction.get('hit_exact')))
            row['points_1x2'] += int(prediction.get('points_1x2') or 0)
            row['points_exact'] += int(prediction.get('points_exact') or 0)
            row['points'] += int(prediction.get('points_total') or 0)

    ranking = sorted(standings.values(), key=lambda r: (-r['points'], -r['hits_exact'], -r['hits_1x2'], r['persona'].casefold()))
    for pos, row in enumerate(ranking, start=1):
        row['position'] = pos
    data['standings'] = ranking
    data['scoring'] = {
        'group_stage': {
            'sign_1x2': GROUP_POINTS_1X2,
            'exact_result': GROUP_POINTS_EXACT,
            'note': 'Fase de grupos: 4 puntos por acertar signo 1X2 y 2 puntos adicionales por resultado exacto.'
        }
    }

    data['actualResults'] = actual_results
    data['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    data['actual_results_source'] = 'zafronix'
    return len(valid_results)


def main():
    data = json.loads(DATA_PATH.read_text(encoding='utf-8'))
    actual_results = collect_finished_results()
    count = merge_results(data, actual_results)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    RESULTS_PATH.write_text(json.dumps(actual_results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Actualizados {count} partidos finalizados desde Zafronix')
    for partido, result in sorted(actual_results.items(), key=lambda kv: kv[1].get('zafronix_match_no') or 9999):
        print(f"- {partido}: {result['goles_local']}-{result['goles_visitante']}")


if __name__ == '__main__':
    main()

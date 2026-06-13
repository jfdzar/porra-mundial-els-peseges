#!/usr/bin/env python3
"""Merge actual match results into web/data.json.

Edit actual_results.json with entries like:
{
  "México-Sudáfrica": {"goles_local": 2, "goles_visitante": 1, "source": "FIFA"}
}
Then run: python3 merge_actual_results.py
"""
import json
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
DATA_PATH = HERE / 'data.json'
RESULTS_PATH = HERE / 'actual_results.json'

def result_sign(gl, gv):
    if gl > gv:
        return '1'
    if gl == gv:
        return 'X'
    return '2'

def main():
    data = json.loads(DATA_PATH.read_text(encoding='utf-8'))
    actual_results = json.loads(RESULTS_PATH.read_text(encoding='utf-8')) if RESULTS_PATH.exists() else {}

    valid_results = {}
    for partido, result in actual_results.items():
        gl = result.get('goles_local')
        gv = result.get('goles_visitante')
        if gl is None or gv is None:
            continue
        gl = int(gl)
        gv = int(gv)
        valid_results[partido] = {
            'goles_local': gl,
            'goles_visitante': gv,
            'resultado': f'{gl}-{gv}',
            'signo': result_sign(gl, gv),
            'source': result.get('source', 'manual'),
        }

    for match in data['matches']:
        actual = valid_results.get(match['partido'])
        if actual:
            match['played'] = True
            match['actual_goles_local'] = actual['goles_local']
            match['actual_goles_visitante'] = actual['goles_visitante']
            match['actual_resultado'] = actual['resultado']
            match['actual_signo'] = actual['signo']
            match['actual_source'] = actual['source']
        else:
            match['played'] = False
            match['actual_goles_local'] = None
            match['actual_goles_visitante'] = None
            match['actual_resultado'] = None
            match['actual_signo'] = None
            match['actual_source'] = None

    matches_by_name = {m['partido']: m for m in data['matches']}
    for prediction in data['predictions']:
        match = matches_by_name[prediction['partido']]
        prediction['played'] = match['played']
        prediction['actual_resultado'] = match['actual_resultado']
        prediction['actual_signo'] = match['actual_signo']
        if match['played']:
            prediction['hit_1x2'] = prediction['signo'] == match['actual_signo']
            prediction['hit_exact'] = prediction['resultado'] == match['actual_resultado']
        else:
            prediction['hit_1x2'] = None
            prediction['hit_exact'] = None

    data['actualResults'] = actual_results
    data['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Actualizados {len(valid_results)} partidos con resultado real en {DATA_PATH}")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Add knockout-stage predictions from the original Excel files to local data.json.

This is a local build helper for Juan's PorraMundial static site. It keeps the
existing group-stage data/scoring and appends participant-specific knockout
predictions extracted from the Pool/Sheet1 ranges.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_JSON = ROOT / 'data.json'
PORRAS = Path('/hermes-workspace/PorraMundial/porras')
OUT_CSV = ROOT / 'predicciones_eliminatorias_consolidado.csv'

NS = {
    'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
}

ROUND_DEFS_POOL = [
    ('Dieciseisavos', range(164, 180), 73),
    ('Octavos', range(200, 208), 89),
    ('Cuartos', range(220, 224), 97),
    ('Semifinales', range(232, 234), 101),
    ('3º/4º puesto', [244], 103),
    ('Final', [247], 104),
]
ROUND_DEFS_HECTOR = [
    ('Dieciseisavos', range(160, 176), 73),
    ('Octavos', range(196, 204), 89),
    ('Cuartos', range(216, 220), 97),
    ('Semifinales', range(228, 230), 101),
    ('3º/4º puesto', [240], 103),
    ('Final', [243], 104),
]
AWARDS_POOL = {'campeon': 'C250', 'subcampeon': 'C251', 'tercero': 'C252', 'bota_oro': 'C253', 'balon_oro': 'C256'}
AWARDS_HECTOR = {'campeon': 'A246', 'subcampeon': 'A247', 'tercero': 'A248', 'bota_oro': 'A249', 'balon_oro': 'A252'}
QUALS_POOL = {'Finalistas': range(240, 242), 'Semifinalistas': range(226, 230)}
QUALS_HECTOR = {'Finalistas': range(236, 238), 'Semifinalistas': range(222, 226)}
GROUP_POSITION_ROWS_POOL = range(80, 128)
GROUP_POSITION_ROWS_HECTOR = range(76, 124)
R32_QUALIFIER_ROWS_POOL = range(130, 162)
R32_QUALIFIER_ROWS_HECTOR = range(126, 158)


def load_sheets(path: Path) -> dict[str, dict[str, str]]:
    with zipfile.ZipFile(path) as zf:
        shared: list[str] = []
        if 'xl/sharedStrings.xml' in zf.namelist():
            root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
            for si in root.findall('a:si', NS):
                shared.append(''.join(t.text or '' for t in si.findall('.//a:t', NS)))

        wb = ET.fromstring(zf.read('xl/workbook.xml'))
        rels = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        rel_map = {rel.get('Id'): rel.get('Target') for rel in rels}
        sheets: dict[str, dict[str, str]] = {}

        for sheet in wb.findall('.//a:sheet', NS):
            name = sheet.get('name') or 'Sheet'
            target = rel_map[sheet.get(f'{{{NS["r"]}}}id')]
            xml_path = 'xl/' + target.lstrip('/') if not target.startswith('xl/') else target
            if xml_path not in zf.namelist():
                xml_path = 'xl/worksheets/' + target.split('/')[-1]
            root = ET.fromstring(zf.read(xml_path))
            cells: dict[str, str] = {}
            for cell in root.findall('.//a:c', NS):
                ref = cell.get('r')
                if not ref:
                    continue
                cell_type = cell.get('t')
                value_node = cell.find('a:v', NS)
                formula_node = cell.find('a:f', NS)
                value = None
                if value_node is not None:
                    value = value_node.text
                    if cell_type == 's' and value and value.isdigit():
                        value = shared[int(value)]
                elif formula_node is not None:
                    # Cached formula values are already handled by <v>; formulas without
                    # cached values are not useful for this extraction.
                    value = None
                if value not in (None, ''):
                    cells[ref] = str(value).strip()
            sheets[name] = cells
        return sheets


def split_match(match: str) -> tuple[str, str]:
    if '-' not in match:
        return match, ''
    local, visitante = match.split('-', 1)
    return local.strip(), visitante.strip()


def parse_prediction(raw: str, fallback_match: str = '') -> dict[str, str | int | bool | None]:
    raw = (raw or '').strip()
    match, rest = fallback_match, raw
    if '·' in raw:
        match, rest = raw.split('·', 1)
    parsed = re.match(r'^([12X])\|(\d+)\-(\d+)$', rest.strip())
    local, visitante = split_match(match)
    result = {
        'partido': match,
        'local': local,
        'visitante': visitante,
        'signo': '',
        'resultado': '',
        'goles_local': '',
        'goles_visitante': '',
    }
    if parsed:
        result.update({
            'signo': parsed.group(1),
            'resultado': f'{parsed.group(2)}-{parsed.group(3)}',
            'goles_local': int(parsed.group(2)),
            'goles_visitante': int(parsed.group(3)),
        })
    return result


def extract_group_positions(cells: dict[str, str], column: str, rows) -> dict[str, list[str]]:
    positions: dict[str, list[str]] = {}
    for idx, row_num in enumerate(rows):
        group = chr(ord('A') + idx // 4)
        team = cells.get(f'{column}{row_num}', '').strip()
        if team:
            positions.setdefault(group, []).append(team)
    return positions


def extract_team_list(cells: dict[str, str], column: str, rows) -> list[str]:
    return [cells.get(f'{column}{row_num}', '').strip() for row_num in rows if cells.get(f'{column}{row_num}', '').strip()]


def extract_one(path: Path) -> tuple[str, list[dict], dict]:
    sheets = load_sheets(path)
    if 'Pool' in sheets:
        cells = sheets['Pool']
        persona = cells.get('C5') or path.stem
        round_defs = ROUND_DEFS_POOL
        awards = {key: cells.get(ref, '') for key, ref in AWARDS_POOL.items()}
        finalistas = [cells.get(f'C{r}', '') for r in QUALS_POOL['Finalistas'] if cells.get(f'C{r}', '')]
        semifinalistas = [cells.get(f'C{r}', '') for r in QUALS_POOL['Semifinalistas'] if cells.get(f'C{r}', '')]
        group_positions = extract_group_positions(cells, 'C', GROUP_POSITION_ROWS_POOL)
        r32_qualified_teams = extract_team_list(cells, 'C', R32_QUALIFIER_ROWS_POOL)
        raw_for_row = lambda r: cells.get(f'C{r}', '')
        fallback_match = lambda r: cells.get(f'B{r}', '')
    else:
        cells = sheets.get('Sheet1') or next(iter(sheets.values()))
        persona = cells.get('A1') or path.stem
        round_defs = ROUND_DEFS_HECTOR
        awards = {key: cells.get(ref, '') for key, ref in AWARDS_HECTOR.items()}
        finalistas = [cells.get(f'A{r}', '') for r in QUALS_HECTOR['Finalistas'] if cells.get(f'A{r}', '')]
        semifinalistas = [cells.get(f'A{r}', '') for r in QUALS_HECTOR['Semifinalistas'] if cells.get(f'A{r}', '')]
        group_positions = extract_group_positions(cells, 'A', GROUP_POSITION_ROWS_HECTOR)
        r32_qualified_teams = extract_team_list(cells, 'A', R32_QUALIFIER_ROWS_HECTOR)
        raw_for_row = lambda r: cells.get(f'A{r}', '')
        fallback_match = lambda r: cells.get(f'A{r}', '').split('·', 1)[0] if '·' in cells.get(f'A{r}', '') else ''

    rows: list[dict] = []
    for fase, excel_rows, first_order in round_defs:
        for offset, row_num in enumerate(excel_rows):
            pred = parse_prediction(raw_for_row(row_num), fallback_match(row_num))
            order = first_order + offset
            rows.append({
                'id': f'KO-{persona}-{order}',
                'persona': persona,
                'archivo': path.name,
                'fase': 'Eliminatorias',
                'jornada': fase,
                'round_label': fase,
                'grupo': 'Eliminatorias',
                'codigo': fase,
                'chronological_order': order,
                'datetime_label': fase,
                **pred,
                'played': False,
                'actual_resultado': '',
                'actual_signo': '',
                'hit_1x2': False,
                'hit_exact': False,
                'points_1x2': 0,
                'points_exact': 0,
                'points_total': 0,
                'is_knockout': True,
            })
    summary = {
        'persona': persona,
        **awards,
        'group_positions': group_positions,
        'r32_qualified_teams': r32_qualified_teams,
        'finalistas': finalistas,
        'semifinalistas': semifinalistas,
    }
    return persona, rows, summary


def make_knockout_matches(rows: list[dict]) -> list[dict]:
    # Knockout matchups are participant-specific because they depend on each
    # person's predicted group table. The global `matches` list therefore stores
    # one representative slot per knockout order/round for statistics/future UI.
    seen: dict[int, str] = {}
    labels: dict[int, str] = {}
    for row in rows:
        order = int(row['chronological_order'])
        labels[order] = str(row['jornada'])
        seen.setdefault(order, str(row['partido']))
    return [
        {
            'id': f'KO-{order}',
            'phase': 'Eliminatorias',
            'jornada': labels[order],
            'grupo': 'Eliminatorias',
            'partido': seen[order],
            'chronological_order': order,
            'datetime_label': labels[order],
            'local': split_match(seen[order])[0],
            'visitante': split_match(seen[order])[1],
            'is_knockout': True,
        }
        for order in sorted(seen)
    ]


def main() -> None:
    data = json.loads(DATA_JSON.read_text(encoding='utf-8'))

    # Keep original group-stage data intact; drop any previous local KO trial rows.
    data['predictions'] = [p for p in data['predictions'] if not p.get('is_knockout')]
    data['matches'] = [m for m in data['matches'] if not m.get('is_knockout')]

    all_rows: list[dict] = []
    summaries: list[dict] = []
    incidents: list[str] = []
    for file_name in sorted(glob.glob(str(PORRAS / '*.xls*'))):
        persona, rows, summary = extract_one(Path(file_name))
        all_rows.extend(rows)
        summaries.append(summary)
        if len(rows) != 32 or any(not r['signo'] for r in rows):
            incidents.append(f'{persona}: {len(rows)} filas, signos vacíos={sum(1 for r in rows if not r["signo"])}')

    data['predictions'].extend(all_rows)
    data['matches'].extend(make_knockout_matches(all_rows))
    data['knockout_summaries'] = sorted(summaries, key=lambda s: s['persona'].lower())
    data['rounds'] = ['all', 'J1', 'J2', 'J3', 'Dieciseisavos', 'Octavos', 'Cuartos', 'Semifinales', '3º/4º puesto', 'Final']
    data['metadata'] = data.get('metadata', {})
    data['metadata']['local_knockout_trial'] = True
    data['metadata']['knockout_prediction_rows'] = len(all_rows)
    data['metadata']['knockout_incidents'] = incidents

    DATA_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    with OUT_CSV.open('w', newline='', encoding='utf-8-sig') as fp:
        fieldnames = ['persona', 'archivo', 'jornada', 'chronological_order', 'partido', 'local', 'visitante', 'signo', 'resultado', 'goles_local', 'goles_visitante']
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({key: row.get(key, '') for key in fieldnames})

    print(json.dumps({
        'people': len(data['people']),
        'matches': len(data['matches']),
        'predictions': len(data['predictions']),
        'knockout_predictions': len(all_rows),
        'knockout_matches': len(data['matches']) - 72,
        'incidents': incidents,
        'csv': str(OUT_CSV),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

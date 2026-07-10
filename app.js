const state = {
  data: null,
  person: null,
  round: 'all',
  query: '',
  expandedMatchKey: null,
};

const $ = (id) => document.getElementById(id);

function normalize(text) {
  return String(text || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatDateParts(label) {
  if (!label) return { day: 'Sin fecha', time: '' };
  const [date, time] = label.split(' ');
  return { day: date, time: time ? `${time} CET` : '' };
}

function predictionText(p) {
  const signMap = { '1': `gana ${p.local}`, 'X': 'empate', '2': `gana ${p.visitante}` };
  return signMap[p.signo] || 'sin signo';
}

function roundLabel(round) {
  return round === 'all' ? 'Todas' : round;
}

function daysSinceEpochInMadrid() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Madrid',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return Math.floor(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day)) / 86400000);
}

function normalizeQuote(raw) {
  if (typeof raw === 'string') {
    return { texto: raw, autor: '' };
  }
  return {
    texto: raw?.texto || raw?.text || raw?.frase || raw?.quote || '',
    autor: raw?.autor || raw?.author || '',
  };
}

async function renderDailyQuote() {
  const quoteBox = $('dailyQuote');
  if (!quoteBox) return;

  try {
    const response = await fetch(`frases.json?v=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`No se pudo cargar frases.json (${response.status})`);
    const rawQuotes = await response.json();
    const quotes = (Array.isArray(rawQuotes) ? rawQuotes : rawQuotes.frases || rawQuotes.quotes || [])
      .map(normalizeQuote)
      .filter((quote) => quote.texto);
    if (!quotes.length) return;

    const quote = quotes[daysSinceEpochInMadrid() % quotes.length];
    $('dailyQuoteText').textContent = `“${quote.texto}”`;
    $('dailyQuoteAuthor').textContent = quote.autor ? quote.autor : '';
    quoteBox.hidden = false;
  } catch (error) {
    console.warn('No se pudo cargar la frase del día', error);
  }
}

function matchPhaseLabel(p) {
  return p.is_knockout ? 'Eliminatorias' : `Grupo ${p.grupo}`;
}

function matchKey(p) {
  // Group-stage fixtures are shared by everyone, so the match name is enough.
  // Knockout rows are participant-specific brackets; for now we compare exact
  // same matchup names when they happen to coincide between participants.
  return `${p.is_knockout ? 'KO' : 'GR'}|${p.partido}`;
}

function filteredPredictions() {
  const q = normalize(state.query);
  return state.data.predictions
    .filter((p) => p.persona === state.person)
    .filter((p) => state.round === 'all' || p.jornada === state.round)
    .filter((p) => !q || normalize(`${p.partido} ${p.local} ${p.visitante} ${p.grupo} ${p.jornada} ${p.fase || ''}`).includes(q))
    .sort((a, b) => Number(a.chronological_order) - Number(b.chronological_order));
}

function renderSummary(rows) {
  const played = rows.filter((r) => r.played);
  const hits1x2 = played.filter((r) => r.hit_1x2).length;
  const hitsExact = played.filter((r) => r.hit_exact).length;
  $('summaryStrip').innerHTML = `
    <div class="summary-item"><b>${rows.length}</b><span>partidos visibles</span></div>
    <div class="summary-item"><b>${played.length}</b><span>con resultado real</span></div>
    <div class="summary-item"><b>${hits1x2}</b><span>aciertos 1X2</span></div>
    <div class="summary-item"><b>${hitsExact}</b><span>resultados exactos</span></div>
  `;
}

function actualStatusHtml(p) {
  if (!p.played) {
    return '<span class="status pending">Sin resultado real todavía</span>';
  }
  const oneXtwo = p.hit_1x2 ? '✅ 1X2' : '❌ 1X2';
  const exact = p.hit_exact ? '🎯 exacto' : '❌ exacto';
  return `<span class="status actual">Real: ${escapeHtml(p.actual_resultado)}</span><span class="status ${p.hit_1x2 ? 'ok' : 'bad'}">${oneXtwo}</span><span class="status ${p.hit_exact ? 'exact' : 'bad'}">${exact}</span>`;
}

function participantPredictionStatus(p) {
  if (!p.played) return '<span class="mini-status pending">Pendiente</span>';
  const oneXtwo = p.hit_1x2 ? '<span class="mini-status ok">1X2</span>' : '<span class="mini-status bad">1X2</span>';
  const exact = p.hit_exact ? '<span class="mini-status exact">Exacto</span>' : '';
  const points = `<span class="mini-status points">${Number(p.points_total || 0)} pts</span>`;
  return `${oneXtwo}${exact}${points}`;
}

function comparisonRowsFor(matchPrediction) {
  const key = matchKey(matchPrediction);
  return state.data.predictions
    .filter((p) => matchKey(p) === key)
    .sort((a, b) => {
      if (a.persona === state.person) return -1;
      if (b.persona === state.person) return 1;
      return a.persona.localeCompare(b.persona, 'es');
    });
}

function renderComparisonHtml(matchPrediction) {
  const rows = comparisonRowsFor(matchPrediction);
  const otherCount = Math.max(rows.length - 1, 0);
  const title = matchPrediction.is_knockout
    ? `Predicciones para este cruce (${otherCount} más)`
    : `Predicciones de los participantes (${otherCount} más)`;

  const rowsHtml = rows.map((row) => `
    <div class="comparison-row ${row.persona === state.person ? 'current-person' : ''}">
      <span class="comparison-person">${escapeHtml(row.persona)}</span>
      <span class="comparison-score">${escapeHtml(row.resultado)}</span>
      <span class="comparison-sign">${escapeHtml(predictionText(row))}</span>
      <span class="comparison-status">${participantPredictionStatus(row)}</span>
    </div>
  `).join('');

  const knockoutHint = matchPrediction.is_knockout && rows.length < state.data.people.length
    ? '<p class="comparison-hint">En eliminatorias algunos participantes tienen cruces distintos según su bracket, así que aquí solo aparecen quienes tienen este mismo cruce.</p>'
    : '';

  return `
    <div class="match-comparison" aria-label="Predicciones de otros participantes">
      <div class="comparison-head">
        <strong>${title}</strong>
        <span>Toca el partido otra vez para cerrar</span>
      </div>
      ${rowsHtml}
      ${knockoutHint}
    </div>
  `;
}

function pct(value, total) {
  if (!total) return '0%';
  return `${Math.round((Number(value || 0) * 100) / total)}%`;
}

function currentDisputedInfo() {
  const playedGroupMatches = (state.data.matches || []).filter((m) => m.played && !m.is_knockout).length;
  const completedGroups = Object.keys(state.data.scoring?.group_positions_current?.completed_group_positions || {}).length;
  const qualifiedTeams = (state.data.scoring?.round_of_32_qualification_current?.qualified_teams || []).length;
  const r32Matchups = Object.keys(state.data.scoring?.round_of_32_matchups_current?.matchups || {}).length;
  const knockoutMatchupsByRound = Object.values(state.data.scoring?.knockout_matchups_current?.matchups || {})
    .reduce((acc, match) => {
      acc[match.jornada] = Number(acc[match.jornada] || 0) + 1;
      return acc;
    }, {});
  const knockoutMatchups = Object.values(knockoutMatchupsByRound).reduce((sum, count) => sum + Number(count || 0), 0);
  const knockoutMatchupPoints = Object.entries(knockoutMatchupsByRound)
    .reduce((sum, [jornada, count]) => {
      const points = Number(state.data.scoring?.knockout_matchups_current?.exact_matchup_by_round?.[jornada] || 0);
      return sum + (Number(count || 0) * points);
    }, 0);
  const disputed = playedGroupMatches * 6 + completedGroups * 4 * 2 + qualifiedTeams * 4 + r32Matchups * 2 + knockoutMatchupPoints;
  const totalTournament = 1323;
  return {
    playedGroupMatches,
    completedGroups,
    completedPositions: completedGroups * 4,
    qualifiedTeams,
    r32Matchups,
    knockoutMatchups,
    knockoutMatchupsByRound,
    knockoutMatchupPoints,
    disputed,
    percent: totalTournament ? `${((disputed * 100) / totalTournament).toFixed(2).replace('.', ',')}%` : '',
  };
}

const AUDIT_KNOCKOUT_ROUNDS = [
  { key: 'octavos', label: 'Octavos', jornada: 'Octavos' },
  { key: 'cuartos', label: 'Cuartos', jornada: 'Cuartos' },
  { key: 'semis', label: 'Semis', jornada: 'Semifinales' },
  { key: 'tercero', label: '3º/4º', jornada: '3º/4º puesto' },
  { key: 'final', label: 'Final', jornada: 'Final' },
];

function exactKnockoutMatchupsByRound(row) {
  const matchups = state.data.scoring?.knockout_matchups_current?.matchups || {};
  const counts = Object.fromEntries(AUDIT_KNOCKOUT_ROUNDS.map((round) => [round.key, 0]));
  (row.matched_knockout_matchups || []).forEach((entry) => {
    const matchNo = String(entry).split(':')[0];
    const jornada = matchups[matchNo]?.jornada;
    const round = AUDIT_KNOCKOUT_ROUNDS.find((item) => item.jornada === jornada);
    if (round) counts[round.key] += 1;
  });
  return counts;
}

function renderScoreAuditTable() {
  const mount = $('scoreAuditTable');
  if (!mount) return;
  const standings = state.data.standings || [];
  const info = currentDisputedInfo();
  const rows = standings.map((row) => {
    const posClass = row.position <= 3 ? `podium podium-${row.position}` : '';
    const selectedClass = row.persona === state.person ? 'selected-audit' : '';
    const knockoutExact = exactKnockoutMatchupsByRound(row);
    const knockoutCells = AUDIT_KNOCKOUT_ROUNDS
      .map((round) => `<td>${Number(knockoutExact[round.key] || 0)}</td>`)
      .join('');
    return `
      <tr class="${posClass} ${selectedClass}" data-person="${escapeHtml(row.persona)}">
        <td class="audit-pos">${row.position}</td>
        <td class="audit-name">${escapeHtml(row.persona)}</td>
        <td class="audit-points">${Number(row.points || 0)}</td>
        <td>${Number(row.hits_1x2 || 0)}</td>
        <td>${pct(row.hits_1x2, info.playedGroupMatches)}</td>
        <td>${Number(row.hits_exact || 0)}</td>
        <td>${pct(row.hits_exact, info.playedGroupMatches)}</td>
        <td>${Number(row.hits_group_positions || 0)}</td>
        <td>${pct(row.hits_group_positions, info.completedPositions)}</td>
        <td>${Number(row.hits_qualified_r32 || 0)}</td>
        <td>${Number(row.hits_r32_matchups || 0)}</td>
        ${knockoutCells}
      </tr>
    `;
  }).join('');
  mount.innerHTML = `
    <table class="score-audit-table">
      <thead>
        <tr class="audit-superhead">
          <th colspan="2">Puntos<br>disputados</th>
          <th>${info.percent}</th>
          <th colspan="6">Fase de Grupos</th>
          <th colspan="2">1/16</th>
          <th colspan="${AUDIT_KNOCKOUT_ROUNDS.length}">Cruces exactos eliminatorias</th>
        </tr>
        <tr>
          <th>POS</th>
          <th>NOMBRE</th>
          <th>PUNTOS</th>
          <th>1X2</th>
          <th>%</th>
          <th>Res.<br>Exact</th>
          <th>%</th>
          <th>Pos.<br>Exacta</th>
          <th>%</th>
          <th>Eq.<br>Clasif</th>
          <th>1/16<br>cruces</th>
          ${AUDIT_KNOCKOUT_ROUNDS.map((round) => `<th>${round.label}<br>cruces</th>`).join('')}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="audit-footnote">Cálculo actual: ${info.playedGroupMatches} partidos de grupo jugados, ${info.completedGroups} grupos completos para posición exacta, ${info.qualifiedTeams} equipos clasificados a 1/16, ${info.r32Matchups} cruces definidos de 1/16 y ${info.knockoutMatchups} cruces definidos de eliminatorias posteriores (${info.knockoutMatchupPoints} pts de partido exacto).</p>
  `;
  mount.querySelectorAll('tbody tr').forEach((row) => {
    row.addEventListener('click', () => {
      state.person = row.dataset.person;
      state.expandedMatchKey = null;
      $('personSelect').value = state.person;
      renderTimeline();
    });
  });
}

function renderStandings() {
  const standings = state.data.standings || [];
  const selected = state.person;
  const medalMap = { 1: '🥇', 2: '🥈', 3: '🥉' };
  $('standingsTable').innerHTML = standings.map((row) => `
    <button class="standing-row ${row.persona === selected ? 'selected' : ''}" data-person="${escapeHtml(row.persona)}">
      <span class="rank">${medalMap[row.position] || `#${row.position}`}</span>
      <span class="standing-name">${escapeHtml(row.persona)}</span>
      <span class="standing-points">${row.points}<small>pts</small></span>
      <span class="standing-details"><span class="standing-stat"><b>${row.hits_1x2}</b> 1X2</span><span class="standing-stat"><b>${row.hits_exact}</b> exactos</span>${Number(row.points_group_positions || 0) ? `<span class="standing-stat"><b>${row.points_group_positions}</b> pos.</span>` : ''}${Number(row.points_qualified_r32 || 0) ? `<span class="standing-stat"><b>${row.points_qualified_r32}</b> clasif.</span>` : ''}${(Number(row.points_r32_matchups || 0) + Number(row.points_knockout_matchups || 0)) ? `<span class="standing-stat"><b>${Number(row.points_r32_matchups || 0) + Number(row.points_knockout_matchups || 0)}</b> cruces</span>` : ''}</span>
    </button>
  `).join('');
  document.querySelectorAll('.standing-row').forEach((button) => {
    button.addEventListener('click', () => {
      state.person = button.dataset.person;
      state.expandedMatchKey = null;
      $('personSelect').value = state.person;
      renderTimeline();
    });
  });
}

function renderTimeline() {
  const rows = filteredPredictions();
  renderStandings();
  renderScoreAuditTable();
  renderSummary(rows);
  const timeline = $('timeline');
  timeline.innerHTML = '';
  if (!rows.length) {
    timeline.innerHTML = '<div class="empty">No hay partidos para esos filtros.</div>';
    return;
  }
  const tpl = $('matchTemplate');
  for (const p of rows) {
    const node = tpl.content.cloneNode(true);
    const card = node.querySelector('.match-card');
    const key = matchKey(p);
    const isExpanded = state.expandedMatchKey === key;
    card.classList.add(`sign-${p.signo}`);
    card.classList.toggle('played', Boolean(p.played));
    card.classList.toggle('expanded', isExpanded);
    card.dataset.matchKey = key;
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-expanded', String(isExpanded));
    card.setAttribute('title', 'Haz click para ver las predicciones de los demás');
    const date = formatDateParts(p.datetime_label);
    node.querySelector('.date-day').textContent = date.day;
    node.querySelector('.date-time').textContent = date.time;
    node.querySelector('.group-badge').textContent = matchPhaseLabel(p);
    node.querySelector('.jornada-badge').textContent = p.jornada;
    node.querySelector('.order').textContent = `#${p.chronological_order}`;
    node.querySelector('.local').textContent = p.local;
    node.querySelector('.away').textContent = p.visitante;
    node.querySelector('.local-goals').textContent = p.goles_local;
    node.querySelector('.away-goals').textContent = p.goles_visitante;
    node.querySelector('.prediction-line').innerHTML = `<strong>${escapeHtml(p.persona)}</strong> puso <strong>${escapeHtml(p.resultado)}</strong> · ${escapeHtml(predictionText(p))} <span class="status-row">${actualStatusHtml(p)}</span><span class="open-hint">Ver demás predicciones</span>`;
    if (isExpanded) {
      node.querySelector('.match-body').insertAdjacentHTML('beforeend', renderComparisonHtml(p));
    }
    card.addEventListener('click', () => {
      state.expandedMatchKey = state.expandedMatchKey === key ? null : key;
      renderTimeline();
    });
    card.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        state.expandedMatchKey = state.expandedMatchKey === key ? null : key;
        renderTimeline();
      }
    });
    timeline.appendChild(node);
  }
}

function initControls() {
  const select = $('personSelect');
  select.innerHTML = state.data.people.map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
  state.person = state.data.people.includes('Juan') ? 'Juan' : state.data.people[0];
  select.value = state.person;
  select.addEventListener('change', (event) => {
    state.person = event.target.value;
    state.expandedMatchKey = null;
    renderTimeline();
  });
  $('searchInput').addEventListener('input', (event) => {
    state.query = event.target.value;
    state.expandedMatchKey = null;
    renderTimeline();
  });
  const rounds = state.data.rounds || ['all', 'J1', 'J2', 'J3'];
  $('roundChips').innerHTML = rounds.map((round) => `<button class="chip ${round === state.round ? 'active' : ''}" data-round="${escapeHtml(round)}">${escapeHtml(roundLabel(round))}</button>`).join('');
  document.querySelectorAll('.chip').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.chip').forEach((b) => b.classList.remove('active'));
      button.classList.add('active');
      state.round = button.dataset.round;
      state.expandedMatchKey = null;
      renderTimeline();
    });
  });
}

async function main() {
  const response = await fetch(`data.json?v=${Date.now()}`, { cache: 'no-store' });
  if (!response.ok) throw new Error(`No se pudo cargar data.json (${response.status})`);
  state.data = await response.json();
  $('statPeople').textContent = state.data.people.length;
  $('statMatches').textContent = state.data.matches.length;
  await renderDailyQuote();
  initControls();
  renderTimeline();
}

main().catch((error) => {
  console.error(error);
  $('timeline').innerHTML = `<div class="empty">Error cargando la aplicación: ${escapeHtml(error.message)}</div>`;
});

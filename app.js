const state = {
  data: null,
  person: null,
  round: 'all',
  query: '',
};

const $ = (id) => document.getElementById(id);

function normalize(text) {
  return String(text || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function formatDateParts(label) {
  if (!label) return { day: 'Sin fecha', time: '' };
  const [date, time] = label.split(' ');
  return { day: date, time };
}

function predictionText(p) {
  const signMap = { '1': `gana ${p.local}`, 'X': 'empate', '2': `gana ${p.visitante}` };
  return signMap[p.signo] || 'sin signo';
}

function filteredPredictions() {
  const q = normalize(state.query);
  return state.data.predictions
    .filter((p) => p.persona === state.person)
    .filter((p) => state.round === 'all' || p.jornada === state.round)
    .filter((p) => !q || normalize(`${p.partido} ${p.local} ${p.visitante} ${p.grupo} ${p.jornada}`).includes(q))
    .sort((a, b) => Number(a.chronological_order) - Number(b.chronological_order));
}

function renderSummary(rows) {
  const winsLocal = rows.filter((r) => r.signo === '1').length;
  const draws = rows.filter((r) => r.signo === 'X').length;
  const winsAway = rows.filter((r) => r.signo === '2').length;
  $('summaryStrip').innerHTML = `
    <div class="summary-item"><b>${rows.length}</b><span>partidos visibles</span></div>
    <div class="summary-item"><b>${winsLocal}</b><span>victorias local</span></div>
    <div class="summary-item"><b>${draws}</b><span>empates</span></div>
    <div class="summary-item"><b>${winsAway}</b><span>victorias visitante</span></div>
  `;
}

function renderTimeline() {
  const rows = filteredPredictions();
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
    card.classList.add(`sign-${p.signo}`);
    const date = formatDateParts(p.datetime_label);
    node.querySelector('.date-day').textContent = date.day;
    node.querySelector('.date-time').textContent = date.time;
    node.querySelector('.group-badge').textContent = `Grupo ${p.grupo}`;
    node.querySelector('.jornada-badge').textContent = p.jornada;
    node.querySelector('.order').textContent = `#${p.chronological_order}`;
    node.querySelector('.local').textContent = p.local;
    node.querySelector('.away').textContent = p.visitante;
    node.querySelector('.local-goals').textContent = p.goles_local;
    node.querySelector('.away-goals').textContent = p.goles_visitante;
    node.querySelector('.prediction-line').innerHTML = `<strong>${p.persona}</strong> puso <strong>${p.resultado}</strong> · ${predictionText(p)}`;
    timeline.appendChild(node);
  }
}

function initControls() {
  const select = $('personSelect');
  select.innerHTML = state.data.people.map((p) => `<option value="${p}">${p}</option>`).join('');
  state.person = state.data.people.includes('Juan') ? 'Juan' : state.data.people[0];
  select.value = state.person;
  select.addEventListener('change', (event) => {
    state.person = event.target.value;
    renderTimeline();
  });
  $('searchInput').addEventListener('input', (event) => {
    state.query = event.target.value;
    renderTimeline();
  });
  document.querySelectorAll('.chip').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.chip').forEach((b) => b.classList.remove('active'));
      button.classList.add('active');
      state.round = button.dataset.round;
      renderTimeline();
    });
  });
}

async function main() {
  const response = await fetch('data.json');
  if (!response.ok) throw new Error(`No se pudo cargar data.json (${response.status})`);
  state.data = await response.json();
  $('statPeople').textContent = state.data.people.length;
  $('statMatches').textContent = state.data.matches.length;
  initControls();
  renderTimeline();
}

main().catch((error) => {
  console.error(error);
  $('timeline').innerHTML = `<div class="empty">Error cargando la aplicación: ${error.message}</div>`;
});

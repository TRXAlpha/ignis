// IGNIS frontend. Plain ES module, no build step.
// Reads only public/data/*.json. ?fixtures=1 switches to ../dev-fixtures/ (fake values).

const FIXTURES = new URLSearchParams(location.search).get('fixtures') === '1';
const BASE = FIXTURES ? '../dev-fixtures/' : 'data/';
const FILES = ['bundle', 'model', 'validation', 'recommendations', 'habitats', 'contradictions', 'material_screen', 'video_spread', 'test_outcomes', 'analyst_runs'];

const $ = (id) => document.getElementById(id);
const fmtDate = (iso) => { const d = new Date(iso); return isNaN(d) ? String(iso) : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(d); };

const COL = {
  bg: '#0b0e14', paper: '#0e1320', grid: '#26304a', text: '#e7ecf4', muted: '#9aa6bb',
  accent: '#7aa2f7', ok: '#3ddc84', bad: '#ff6b6b', star: '#ffd166', other: '#9aa6bb',
};
const CS = 'YlOrRd';
const STATE_STYLE = {
  burns_sustained: { color: COL.ok, symbol: 'circle', label: 'burns sustained' },
  blowoff_extinction: { color: '#000000', symbol: 'x', label: 'blowoff extinction' },
  quench_extinction: { color: COL.bad, symbol: 'circle', label: 'quench extinction' },
};
const DEFAULT_STYLE = { color: COL.other, symbol: 'circle' };
const PLOT_CFG = { responsive: true, displaylogo: false };

// ---------- state ----------
const D = {};          // name -> parsed json, or null
const ERR = {};        // name -> reason string
const OBS = new Map();
const SRC = new Map();
const CAMP = new Map();
const MAT = new Map();

// ---------- helpers ----------
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function safeUrl(u) { return typeof u === 'string' && /^https?:\/\//.test(u) ? esc(u) : null; }
function fmt(v, d = 3) {
  if (v == null || v === '' || Number.isNaN(Number(v))) return '-';
  const n = Number(v);
  if (n !== 0 && (Math.abs(n) < 1e-3 || Math.abs(n) >= 1e6)) return n.toExponential(2);
  const s = n.toFixed(d);
  return s.includes('.') ? s.replace(/\.?0+$/, '') : s;
}
function pct(frac, d = 1) { return frac == null || Number.isNaN(Number(frac)) ? '-' : fmt(Number(frac) * 100, d) + '%'; }
function shortId(id) { return id ? String(id).slice(0, 16) + (String(id).length > 16 ? '…' : '') : '-'; }
function noData(what, reason) {
  return `<div class="empty"><strong>No digitized data yet</strong>${esc(what)}${reason ? ` <span class="muted">(${esc(reason)})</span>` : ''}</div>`;
}
function srcTitle(id) { const s = SRC.get(id); return s ? s.title : id; }
function srcLink(id) {
  const s = SRC.get(id);
  const title = esc(srcTitle(id));
  const u = s && safeUrl(s.url);
  return u ? `<a href="${u}" target="_blank" rel="noopener">${title}</a>` : title;
}
function logTicks(xs) {
  const pos = xs.filter((v) => v > 0);
  if (!pos.length) return { tickvals: [], ticktext: [] };
  const lg = pos.map(Math.log10);
  const lo = Math.min(...lg), hi = Math.max(...lg);
  const dec = [];
  for (let k = Math.ceil(lo); k <= Math.floor(hi); k++) dec.push(k);
  if (dec.length >= 2) return { tickvals: dec, ticktext: dec.map((k) => String(Math.pow(10, k))) };
  const uniq = [...new Set(pos)].sort((a, b) => a - b);
  return { tickvals: uniq.map(Math.log10), ticktext: uniq.map((v) => String(v)) };
}

async function loadJSON(name) {
  try {
    const r = await fetch(BASE + name + '.json', { cache: 'no-store' });
    if (!r.ok) return { ok: false, reason: `${name}.json HTTP ${r.status}` };
    return { ok: true, data: await r.json() };
  } catch (e) {
    return { ok: false, reason: `${name}.json: ${e.message}` };
  }
}

// ---------- boot ----------
async function boot() {
  if (FIXTURES) $('fixtureBanner').hidden = false;
  const results = await Promise.all(FILES.map(loadJSON));
  FILES.forEach((name, i) => {
    if (results[i].ok) D[name] = results[i].data;
    else { D[name] = null; ERR[name] = results[i].reason; }
  });
  const b = D.bundle;
  (b?.sources || []).forEach((s) => SRC.set(s.id, s));
  (b?.campaigns || []).forEach((c) => CAMP.set(c.id, c));
  (b?.materials || []).forEach((m) => MAT.set(m.id, m));
  (b?.observations || []).forEach((o) => OBS.set(o.id, o));

  if (!window.Plotly) {
    document.querySelectorAll('.plot').forEach((el) => { el.innerHTML = noData('Plotly failed to load from CDN.'); });
  }

  const steps = [
    ['envelope', renderEnvelope],
    ['provenance', renderProvenance],
    ['validation', renderValidation],
    ['experiments', renderExperiments],
    ['habitats', renderHabitats],
    ['screen', renderScreen],
    ['tests', renderTests],
    ['data', renderData],
    ['video', renderVideo],
    ['checks', renderChecks],
    ['analyst', renderAnalyst],
    ['stats', renderStats],
    ['footer', renderFooter],
  ];
  for (const [label, fn] of steps) {
    try { fn(); } catch (e) {
      console.error(`[ignis] ${label} failed`, e);
      const target = { envelope: 'envelopeStatus', provenance: 'obsStatus', validation: 'validationBody', experiments: 'experimentsBody', habitats: 'habitatsBody', screen: 'screenBody', tests: 'testsBody', data: 'dataBody', checks: 'checksBody', video: 'videoBody', analyst: 'analystBody', footer: null }[label];
      if (target) $(target).innerHTML = `<div class="empty"><strong>Render error</strong>${esc(e.message)}</div>`;
    }
  }
}

// 2D boundary. group = model.json groups entry (material/geometry subgroup), or null for the primary fit.
function draw2D(group) {
  const m = D.model;
  const recItems = D.recommendations?.items || [];
  const isGroup = !!group;
  const pts = isGroup ? group.points : m.points;
  const bnd = isGroup ? group.boundary : m.boundary;
  const xs = bnd.x;
  const xUnit = isGroup ? (group.key.x_var === 'flow_velocity' ? 'cm/s' : '1/s') : '1/s';
  const xLabel = isGroup ? (group.key.x_var === 'flow_velocity' ? 'Flow velocity' : 'Stretch rate a') : 'Stretch rate a';
  const baselines = isGroup ? [] : (m.baselines || []);
  const cs = { bg: COL.bg, paper: COL.paper, text: COL.text, grid: COL.grid };

  const traces = [];
  // 90% band: p05 (no fill) then p95 filled back to p05
  if (bnd && bnd.x) {
    traces.push({ type: 'scatter', mode: 'lines', x: xs, y: bnd.o2_p05.map((v) => v * 100), line: { width: 0 }, hoverinfo: 'skip', showlegend: false });
    traces.push({ type: 'scatter', mode: 'lines', x: xs, y: bnd.o2_p95.map((v) => v * 100), line: { width: 0 }, fill: 'tonexty', fillcolor: 'rgba(122,162,247,0.22)', name: '90% band (p05 to p95)', hoverinfo: 'skip' });
    traces.push({ type: 'scatter', mode: 'lines', x: xs, y: bnd.o2_p50.map((v) => v * 100), line: { color: COL.accent, width: 3 }, name: 'O2 boundary (p50)', hovertemplate: `x=%{x:.3g} ${xUnit}<br>p50 O2=%{y:.1f}%<extra></extra>` });
  }
  // observation points, grouped by state
  const byState = new Map();
  for (const p of pts) {
    if (!byState.has(p.state)) byState.set(p.state, []);
    byState.get(p.state).push(p);
  }
  for (const [state, list] of byState) {
    const st = STATE_STYLE[state] || { ...DEFAULT_STYLE, label: state };
    if (state === 'blowoff_extinction') {
      // white disc behind the black X so it stays visible on the heatmap
      traces.push({ type: 'scatter', mode: 'markers', x: list.map((p) => p.x), y: list.map((p) => p.y * 100), marker: { symbol: 'circle', size: 16, color: '#ffffff', opacity: 0.55 }, hoverinfo: 'skip', showlegend: false });
    }
    traces.push({
      type: 'scatter', mode: 'markers', name: st.label || state,
      x: list.map((p) => p.x), y: list.map((p) => p.y * 100),
      customdata: list.map((p) => p.id),
      text: list.map((p) => `${p.id}<br>${p.series || p.campaign || ''}`),
      marker: state === 'blowoff_extinction'
        ? { symbol: 'x', size: 13, color: '#000000', line: { color: '#000000', width: 3 } }
        : { symbol: st.symbol, size: 11, color: st.color, line: { color: '#000', width: 1 } },
      hovertemplate: `%{text}<br>${esc(st.label || state)}<br>x=%{x:.3g} ${xUnit}, O2=%{y:.1f}%<br><i>click for provenance</i><extra></extra>`,
    });
  }
  // next-experiment stars (primary fit only; recommendations are per primary constraint set)
  if (!isGroup && recItems.length) {
    traces.push({
      type: 'scatter', mode: 'markers', name: 'Next experiments',
      x: recItems.map((r) => r.x), y: recItems.map((r) => (r.conditions?.o2_mole_fraction ?? NaN) * 100),
      customdata: recItems.map((r) => `rec:${r.rank}`),
      text: recItems.map((r) => `Rank ${r.rank}<br>p_burns ${pct(r.p_burns, 0)}<br>EIG ${fmt(r.expected_information_gain_nats, 2)} nats`),
      marker: { symbol: 'star', size: 18, color: COL.star, line: { color: '#000', width: 1 } },
      hovertemplate: '%{text}<br>a=%{x:.3g} 1/s, O2=%{y:.1f}%<extra></extra>',
    });
  }
  // baselines
  const shapesText = [];
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  for (const bl of baselines) {
    const y = bl.o2 * 100;
    traces.push({ type: 'scatter', mode: 'lines', x: [xMin, xMax], y: [y, y], line: { color: COL.muted, width: 1.5, dash: 'dash' }, showlegend: false, hoverinfo: 'skip' });
    shapesText.push({ x: xMax, y, xref: 'x', yref: 'y', text: `${bl.label} (${fmt(y, 1)}%)`, showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { color: COL.muted, size: 11 } });
  }
  const allY = pts.map((p) => p.y * 100).concat(bnd ? bnd.o2_p05.map((v) => v * 100) : [], bnd ? bnd.o2_p95.map((v) => v * 100) : []);
  const yLo = Math.min(...allY) - 0.5, yHi = Math.max(...allY) + 0.5;

  const layout2d = {
    paper_bgcolor: cs.paper, plot_bgcolor: cs.paper, font: { color: cs.text },
    margin: { l: 56, r: 10, t: 10, b: 50 }, height: 500,
    xaxis: {
      type: 'log', title: `${xLabel} (${xUnit})`, color: cs.text, gridcolor: cs.grid, zerolinecolor: cs.grid,
      range: [Math.log10(xMin) - 0.05, Math.log10(xMax) + 0.05], autorange: false,
    },
    yaxis: { title: 'O2 (%)', range: [yLo, yHi], color: cs.text, gridcolor: cs.grid },
    legend: { orientation: 'h', x: 0, y: -0.2, font: { color: cs.text, size: 11 } },
    annotations: shapesText,
    hovermode: 'closest',
  };
  Plotly.react('plot2d', traces, layout2d, PLOT_CFG).then((el) => {
    el.removeAllListeners && el.removeAllListeners('plotly_click');
    el.on('plotly_click', (ev) => {
      const id = ev.points?.[0]?.customdata;
      if (typeof id === 'string' && !id.startsWith('rec:')) openProvenance(id);
    });
  });
}

// ---------- 2. envelope ----------
let envelopeReady = false;
function renderEnvelope() {
  const m = D.model;
  const status = $('envelopeStatus');
  const pts = m?.points || [];
  if (!m || !m.grid || !pts.length) {
    status.innerHTML = noData('Flammability envelope needs model.json with at least one digitized point.', ERR.model);
    return;
  }
  $('envelopeBody').hidden = false;
  status.innerHTML = '';

  // min O2 callout
  const mo = m.min_o2;
  $('minO2').innerHTML = mo
    ? `<strong>Minimum O2 (p50): ${pct(mo.p50)}</strong> at stretch rate a = ${fmt(mo.at_x, 1)} 1/s.
       90% band (p05 to p95): ${pct(mo.p05)} to ${pct(mo.p95)}.`
    : '<span class="muted">No min_o2 in model.json.</span>';

  $('envelopeCaption').textContent = m.description || '';
  if (m.flow_conversion?.note) {
    $('envelopeCaption').textContent += ` Flow for the base rod = a × ${fmt(m.flow_conversion.u_m_s_per_x, 5)} m/s. ${m.flow_conversion.note}`;
  }

  const recItems = D.recommendations?.items || [];
  const xs = m.grid.x, ysPct = m.grid.y.map((v) => v * 100);
  const cs = { bg: COL.bg, paper: COL.paper, text: COL.text, grid: COL.grid };

  // 3D surface, log x via transformed coordinates
  const lg = xs.map((v) => (v > 0 ? Math.log10(v) : null));
  const t3 = logTicks(xs);
  Plotly.newPlot('plot3d', [{
    type: 'surface', x: lg, y: ysPct, z: m.grid.p_burns,
    colorscale: CS, cmin: 0, cmax: 1,
    colorbar: { title: 'P(burns)', tickformat: '.0%', tickfont: { color: cs.text }, titlefont: { color: cs.text } },
    hovertemplate: 'log10 a=%{x:.2f} (1/s)<br>O2=%{y:.1f}%<br>P(burns)=%{z:.2f}<extra></extra>',
  }], {
    paper_bgcolor: cs.paper, font: { color: cs.text },
    margin: { l: 0, r: 0, t: 10, b: 0 }, height: 460,
    scene: {
      xaxis: { title: 'Stretch rate a (1/s, log)', tickvals: t3.tickvals, ticktext: t3.ticktext, color: cs.text, gridcolor: cs.grid },
      yaxis: { title: 'O2 (%)', color: cs.text, gridcolor: cs.grid },
      zaxis: { title: 'P(burns)', range: [0, 1], tickformat: '.0%', color: cs.text, gridcolor: cs.grid },
      bgcolor: cs.paper,
    },
  }, PLOT_CFG);

  // 2D boundary (primary fit or selected group)
  const groups = m.groups || [];
  const sel = $('groupSelect');
  if (groups.length) {
    $('groupPicker').hidden = false;
    sel.innerHTML = '<option value="">Primary fit (PMMA rods, stretch rate)</option>'
      + groups.map((g, i) => `<option value="${i}">${esc(g.label)}</option>`).join('');
    $('groupInfo').textContent = `${(m.points || []).length} points`;
    sel.onchange = () => {
      const g = sel.value === '' ? null : groups[Number(sel.value)];
      draw2D(g);
      if (g) {
        const nc = Object.keys(g.n_by_campaign).length;
        $('groupInfo').textContent = `${g.n} points, ${nc} campaign${nc === 1 ? '' : 's'}`
          + (g.min_o2 ? ` · min O2 p50 ${pct(g.min_o2.p50)}${g.min_o2.min_at_edge ? ' (at edge of data range)' : ''}` : '');
      } else {
        $('groupInfo').textContent = `${(m.points || []).length} points`;
      }
    };
  } else {
    $('groupPicker').hidden = true;
    const sk = m.groups_skipped || [];
    if (sk.length) {
      const note = document.createElement('p');
      note.className = 'caption';
      note.textContent = `Only PMMA rods have enough tests for a boundary fit. ${sk.length} other material/geometry group(s) `
        + 'lack enough tests with a reported extinction flow; they are shown test by test under "BASS-II flight tests by material".';
      $('envelopeCaption').after(note);
    }
  }
  draw2D(null);
  envelopeReady = true;

  document.querySelectorAll('.toggle button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const v = btn.dataset.view;
      document.querySelectorAll('.toggle button').forEach((bb) => bb.setAttribute('aria-pressed', String(bb === btn)));
      $('plot3d').hidden = v !== '3d';
      $('plot2d').hidden = v !== '2d';
      Plotly.Plots.resize(v === '3d' ? $('plot3d') : $('plot2d'));
    });
  });
}

// ---------- 3. provenance ----------
function renderProvenance() {
  const list = D.bundle?.observations || [];
  if (!D.bundle || !list.length) {
    $('obsStatus').innerHTML = noData('Provenance needs bundle.json with observations.', ERR.bundle);
    return;
  }
  const rows = list.map((o) => {
    const qty = o.outcome?.quantity || '-';
    let outcome;
    if (o.outcome?.state) outcome = esc(o.outcome.state);
    else if (o.outcome?.value) outcome = `${fmt(o.outcome.value.value)} ${esc(o.outcome.value.unit)}`;
    else outcome = '-';
    const o2 = o.conditions?.o2_mole_fraction ? pct(o.conditions.o2_mole_fraction.si_value) : '-';
    const camp = CAMP.get(o.experiment?.campaign_id);
    const mat = MAT.get(o.fuel?.material_id);
    return `<tr class="clickable" tabindex="0" data-id="${esc(o.id)}">
      <td class="mono" title="${esc(o.id)}">${esc(shortId(o.id))}</td>
      <td>${esc(camp ? camp.name : o.experiment?.campaign_id || '-')}</td>
      <td>${esc(o.experiment?.platform || '-')}</td>
      <td>${esc(mat ? mat.name : o.fuel?.material_id || '-')}</td>
      <td>${esc(qty)}<span class="sub">${outcome}</span></td>
      <td>${o2}</td>
      <td>${esc(o.extraction?.method || '-')}</td>
      <td>${esc(o.qa?.status || '-')}</td>
    </tr>`;
  }).join('');
  $('obsTable').innerHTML = `<table>
    <thead><tr><th>ID</th><th>Campaign</th><th>Platform</th><th>Material</th><th>Outcome</th><th>O2</th><th>Method</th><th>QA</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
  $('obsTable').hidden = false;
  // long list: filter + first 12 rows, expandable
  const wrap = $('obsTable');
  wrap.classList.add('collapsed');
  const tools = document.createElement('div');
  tools.className = 'table-tools';
  tools.innerHTML = `<label class="sr-only" for="obsFilter">Filter observations</label>
    <input id="obsFilter" name="obs-filter" type="search" placeholder="Filter by campaign, material, outcome…" autocomplete="off" spellcheck="false">
    <button type="button" class="btn btn-ghost btn-sm" id="obsMore">Show All ${list.length}</button>`;
  wrap.before(tools);
  const trs = [...wrap.querySelectorAll('tbody tr')];
  $('obsFilter').addEventListener('input', (ev) => {
    const q = ev.target.value.trim().toLowerCase();
    trs.forEach((tr) => { tr.hidden = q && !tr.textContent.toLowerCase().includes(q); });
    wrap.classList.toggle('collapsed', !q && $('obsMore').dataset.open !== '1');
  });
  $('obsMore').addEventListener('click', (ev) => {
    const open = ev.currentTarget.dataset.open === '1';
    ev.currentTarget.dataset.open = open ? '0' : '1';
    ev.currentTarget.textContent = open ? `Show All ${list.length}` : 'Show Fewer';
    wrap.classList.toggle('collapsed', open);
  });
  $('obsStatus').innerHTML = '';

  $('obsTable').addEventListener('click', (ev) => {
    const tr = ev.target.closest('tr[data-id]');
    if (tr) openProvenance(tr.dataset.id, tr);
  });
  $('obsTable').addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter') return;
    const tr = ev.target.closest('tr[data-id]');
    if (tr) openProvenance(tr.dataset.id, tr);
  });
  $('provPanel').innerHTML = '<span class="muted">Select an observation.</span>';
  $('provPanel').hidden = true;
}

function openProvenance(id, rowEl) {
  const o = OBS.get(id);
  const panel = $('provPanel');
  document.querySelectorAll('tr.selected').forEach((r) => r.classList.remove('selected'));
  const row = rowEl || document.querySelector(`tr[data-id="${CSS.escape(id)}"]`);
  if (row) row.classList.add('selected');
  if (!o) {
    panel.innerHTML = `<h3>${esc(id)}</h3><p class="muted">No record for this point in bundle.json.</p>`;
  } else {
    panel.innerHTML = provHTML(o);
  }
  panel.hidden = false;
  $('provenance').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function provHTML(o) {
  const loc = o.locator || {};
  const src = SRC.get(loc.source_id);
  const pageTxt = loc.page ? ` · PDF page ${loc.page}` : '';
  const pdfU = src && safeUrl(src.pdf_url);
  const pdf = loc.page && pdfU ? ` · <a href="${pdfU}#page=${loc.page}" target="_blank" rel="noopener">PDF page ${loc.page}</a>` : esc(pageTxt);
  const where = [
    loc.figure && `Figure ${loc.figure}`,
    loc.panel && `panel ${loc.panel}`,
    loc.table && `Table ${loc.table}`,
    loc.row && `row ${loc.row}`,
    loc.column && `column ${loc.column}`,
    loc.series && `series "${loc.series}"`,
    loc.point_index != null && `point #${loc.point_index}`,
    loc.dataset_path && `dataset ${loc.dataset_path}`,
  ].filter(Boolean).join(', ');
  const ex = o.extraction || {};
  const dig = ex.digitization;
  const oc = o.outcome || {};
  const outcome = oc.state ? esc(oc.state) : oc.value ? `${fmt(oc.value.value)} ${esc(oc.value.unit)} (SI ${fmt(oc.value.si_value, 4)} ${esc(oc.value.si_unit)})` : '-';
  const o2 = o.conditions?.o2_mole_fraction;
  const digHTML = dig ? `
    <dt>Digitized pixel</dt><dd class="mono">(${fmt(dig.pixel?.[0], 1)}, ${fmt(dig.pixel?.[1], 1)})${dig.marker ? ` · marker ${esc(dig.marker)}` : ''}</dd>
    <dt>Calibration residual</dt><dd>${fmt(dig.calibration_residual_px, 2)} px</dd>
    <dt>Image SHA-256</dt><dd class="mono" title="${esc(dig.image_sha256)}">${esc(String(dig.image_sha256 || '').slice(0, 12))}…</dd>
    ${dig.x_field ? `<dt>x feeds</dt><dd class="mono">${esc(dig.x_field)}</dd>` : ''}` : '';
  return `<h3>${esc(o.id)}</h3>
    <dl>
      <dt>Source</dt><dd>${srcLink(loc.source_id)}${pdf}</dd>
      <dt>Location</dt><dd>${esc(where || '-')}</dd>
      <dt>Outcome</dt><dd>${esc(oc.quantity || '-')}: ${outcome}</dd>
      <dt>O2</dt><dd>${o2 ? `${pct(o2.si_value)} (reported ${fmt(o2.value)} ${esc(o2.unit)})` : '-'}</dd>
      <dt>Series</dt><dd>${esc(loc.series || '-')}</dd>
      <dt>Extraction</dt><dd>${esc(ex.method || '-')} · ${esc(ex.tool || '-')}${ex.model ? ` · model ${esc(ex.model)}` : ''}</dd>
      <dt>Confidence</dt><dd>${fmt(ex.confidence, 2)}</dd>
      <dt>Flags</dt><dd>${(ex.flags || []).map(esc).join(', ') || 'none'}</dd>
      <dt>QA</dt><dd>${esc(o.qa?.status || '-')}${(o.qa?.reasons || []).length ? ` · ${(o.qa.reasons || []).map(esc).join('; ')}` : ''}</dd>
      ${digHTML}
    </dl>
    ${loc.quote ? `<blockquote>${esc(loc.quote)}</blockquote>` : ''}`;
}

// ---------- 4. validation ----------
function renderValidation() {
  const v = D.validation;
  const el = $('validationBody');
  const folds = (v && v.folds) || [];
  const cv = (v && v.cv) || [];
  if (!v || (!folds.length && !cv.length)) {
    el.innerHTML = noData('No validation results yet.', ERR.validation);
    return;
  }
  const label = {
    rmse_o2_pct: 'Boundary error, held-out extinctions (RMSE, O2 % points)',
    median_abs_rel_error: 'Boundary error, median relative',
    coverage90_ext: 'Held-out extinctions inside 90 % interval',
    acc_stable: 'Held-out stable flames predicted burning',
    brier: 'Brier score, held-out stable flames (lower is better)',
  };
  const isPct = (k) => k === 'coverage90_ext' || k === 'acc_stable';
  const val = (k, x) => (x == null ? '-' : isPct(k) ? pct(x, 0) : fmt(x, 3));
  const block = (title, m, b, n) => {
    const keys = Object.keys(label).filter((k) => m[k] != null || b[k] != null);
    const rows = keys.map((k) => `<tr><td>${esc(label[k])}</td><td><strong>${val(k, m[k])}</strong></td><td>${val(k, b[k])}</td></tr>`).join('');
    return `<h3 class="sub-h">${esc(title)}${n ? ` (n = ${esc(n)})` : ''}</h3>
      <div class="table-wrap"><table><thead><tr><th>Metric</th><th>IGNIS model</th><th>1g rule (burns iff O2 &ge; 15.4 %)</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
  };
  const lims = (v.limitations || []).map((l) => `<li>${esc(l)}</li>`).join('');
  el.innerHTML = `
    <p>${esc(v.summary || '')}</p>
    ${folds.map((f) => block(`Leave-one-campaign-out: held out ${CAMP.get(f.held_out_campaign_id)?.name || f.held_out_campaign_id}`, f.metrics || {}, f.baseline || {}, f.n_test)).join('')}
    ${cv.map((c) => block(c.kind, c.metrics || {}, c.baseline || {}, c.n)).join('')}
    <div class="warn"><strong>Limitations</strong>${lims ? `<ul>${lims}</ul>` : ' none listed'}</div>`;
}

// ---------- 5. next experiments ----------
function renderExperiments() {
  const r = D.recommendations;
  const el = $('experimentsBody');
  if (!r || !(r.items || []).length) {
    el.innerHTML = noData('No recommendations yet.', ERR.recommendations);
    return;
  }
  const cs = r.constraint_set || {};
  const unitMap = {
    gravity_m_s2: { label: 'Gravity (m/s²)', f: (v) => v },
    o2_mole_fraction: { label: 'O2 (%)', f: (v) => v * 100 },
    pressure_pa: { label: 'Pressure (kPa)', f: (v) => v / 1000 },
    flow_velocity_m_s: { label: 'Flow (cm/s)', f: (v) => v * 100 },
    thickness_m: { label: 'Thickness (mm)', f: (v) => v * 1000 },
  };
  const rangeRows = Object.entries(cs.ranges || {}).map(([k, rg]) => {
    const u = unitMap[k] || { label: k, f: (v) => v };
    return `<tr><td>${esc(u.label)}</td><td>${fmt(u.f(rg[0]), 3)} to ${fmt(u.f(rg[1]), 3)}</td></tr>`;
  }).join('');
  const csRefs = (cs.refs || []).map(refHTML).join('');
  const recRows = [...r.items].sort((a, b) => a.rank - b.rank).map((it) => {
    const c = it.conditions || {};
    return `<tr>
      <td>${esc(it.rank)}</td>
      <td>${c.flow_velocity_m_s != null ? fmt(c.flow_velocity_m_s * 100, 2) : '-'}</td>
      <td>${c.o2_mole_fraction != null ? fmt(c.o2_mole_fraction * 100, 1) : '-'}</td>
      <td>${pct(it.p_burns, 0)}</td>
      <td>${fmt(it.expected_information_gain_nats, 3)}</td>
      <td>${esc(it.gap?.description || '-')}${it.n_burns ? `<span class="sub">${esc(it.n_burns)} burn(s)</span>` : ''}</td>
    </tr>`;
  }).join('');
  el.innerHTML = `
    <h3>Constraint Set: ${esc(cs.name || cs.id || '-')}</h3>
    <p class="caption">${esc(cs.platform || '')}${cs.facility ? ` · ${esc(cs.facility)}` : ''}${cs.max_burns ? ` · max ${esc(cs.max_burns)} burns` : ''}</p>
    <div class="table-wrap"><table><thead><tr><th>Parameter</th><th>Range</th></tr></thead><tbody>${rangeRows || '<tr><td colspan="2">No ranges</td></tr>'}</tbody></table></div>
    ${csRefs ? `<div class="refs-title">Range sources</div>${csRefs}` : ''}
    <h3 style="margin-top:16px">Recommended runs</h3>
    <p class="caption">Stars on the envelope above.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Rank</th><th>Flow (cm/s)</th><th>O2 (%)</th><th>P(burns)</th><th>EIG (nats)</th><th>Gap</th></tr></thead>
      <tbody>${recRows}</tbody>
    </table></div>`;
}

// ---------- 6. habitats ----------
function renderHabitats() {
  const h = D.habitats;
  const el = $('habitatsBody');
  const presets = h?.presets || [];
  if (!presets.length) {
    el.innerHTML = noData('No habitat presets yet.', ERR.habitats);
    return;
  }
  el.innerHTML = `<div class="grid-cards">${presets.map(habitatCard).join('')}</div>`;
}

function habitatCard(p) {
  const c = p.conditions || {};
  const pr = p.prediction;
  let pred;
  if (!pr) {
    pred = '<span class="badge">NO PREDICTION</span>';
  } else if (pr.status === 'ok') {
    pred = pr.p_burns != null
      ? `<div class="big">${pct(pr.p_burns, 0)}</div><div class="muted">P(sustained burning)</div>${pr.ood?.reason ? `<p class="caption">${esc(pr.ood.reason)}</p>` : ''}`
      : '<span class="badge">NO VALUE</span>';
  } else {
    const label = pr.status === 'insufficient_data' ? 'INSUFFICIENT DATA' : pr.status === 'extrapolation' ? 'EXTRAPOLATION' : esc(String(pr.status).toUpperCase());
    pred = `<span class="badge">${label}</span><p class="reason">${esc(pr.ood?.reason || 'No reason given.')}</p>`;
  }
  const refs = (p.refs || []).map(refHTML).join('');
  return `<article class="card">
    <h3>${esc(p.name)}</h3>
    <dl>
      <dt>O2</dt><dd>${c.o2_mole_fraction != null ? fmt(c.o2_mole_fraction * 100, 1) + '%' : '-'}</dd>
      <dt>Pressure</dt><dd>${c.pressure_pa != null ? fmt(c.pressure_pa / 1000, 1) + ' kPa' : '-'}</dd>
      <dt>Gravity</dt><dd>${c.gravity_m_s2 != null ? fmt(c.gravity_m_s2, 3) + ' m/s²' : '-'}</dd>
    </dl>
    ${pred}
    ${p.notes ? `<p class="muted" style="font-size:0.88rem">${esc(p.notes)}</p>` : ''}
    <div class="refs-title">References</div>
    ${refs || '<span class="muted">none</span>'}
  </article>`;
}

function refHTML(loc) {
  const page = loc.page ? ` · PDF page ${esc(loc.page)}` : '';
  const where = [loc.figure && `Figure ${loc.figure}`, loc.table && `Table ${loc.table}`].filter(Boolean).join(', ');
  return `<div style="margin-top:6px"><div>${srcLink(loc.source_id)}${page}${where ? ` · ${esc(where)}` : ''}</div>${loc.quote ? `<blockquote>${esc(loc.quote)}</blockquote>` : ''}</div>`;
}

// ---------- data sources + timeline ----------
function renderData() {
  const b = D.bundle;
  const el = $('dataBody');
  if (!b) { el.innerHTML = noData('No bundle.', ERR.bundle); return; }
  const byCamp = new Map();
  (b.observations || []).forEach((o) => {
    const k = o.experiment.campaign_id;
    const e = byCamp.get(k) || { n: 0, outcomes: new Set(), methods: new Set() };
    e.n += 1; e.outcomes.add(o.outcome.quantity); e.methods.add(o.extraction.method);
    byCamp.set(k, e);
  });
  const rows = (b.campaigns || []).map((c) => {
    const e = byCamp.get(c.id) || { n: 0, outcomes: new Set(), methods: new Set() };
    const yrs = (c.years || []).join(', ') || '<span class="muted">not sourced</span>';
    return `<tr><td>${esc(c.name)}</td><td>${esc(c.platform)}</td><td>${yrs}</td><td>${e.n}</td>
      <td>${esc([...e.outcomes].join(', ') || '-')}</td><td>${esc([...e.methods].join(', ') || '-')}</td></tr>`;
  }).join('');
  const srcRows = (b.sources || []).map((s) => `<li>${srcLink(s.id)}${s.year ? ` (${esc(s.year)})` : ''} <span class="muted mono">${esc(s.id)}</span></li>`).join('');
  el.innerHTML = `
    <div class="table-wrap"><table><thead><tr><th>Campaign</th><th>Platform</th><th>Test years</th><th>Observations</th><th>Outcomes</th><th>Extraction</th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    <div id="timelinePlot" class="plot plot-short"></div>
    <p class="caption">Test years come from the campaign's own documents (e.g. BASS-II test matrices); campaigns without a sourced year are not placed on the timeline.</p>
    <h3 class="sub-h">Sources (${(b.sources || []).length})</h3><ul class="src-list">${srcRows}</ul>`;
  const pts = (b.campaigns || []).filter((c) => (c.years || []).length);
  if (window.Plotly && pts.length) {
    const traces = pts.map((c) => ({
      type: 'scatter', mode: 'markers+lines', name: c.name, x: c.years, y: c.years.map(() => c.name),
      marker: { size: 10 + Math.min(20, (byCamp.get(c.id)?.n || 0) / 3) }, hovertemplate: `%{x}<br>${esc(c.name)}<extra></extra>`,
    }));
    Plotly.newPlot('timelinePlot', traces, {
      paper_bgcolor: COL.paper, plot_bgcolor: COL.paper, font: { color: COL.text }, showlegend: false,
      margin: { l: 10, r: 10, t: 10, b: 40 }, xaxis: { gridcolor: COL.grid, dtick: 1 },
      yaxis: { automargin: true, gridcolor: COL.grid }, height: 140 + 30 * pts.length,
    }, PLOT_CFG);
  } else { $('timelinePlot').hidden = true; }
}

// ---------- flight video re-measurement (beta) ----------
function renderVideo() {
  const v = D.video_spread;
  const el = $('videoBody');
  if (!v || !(v.rows || []).length) { el.innerHTML = noData('No video measurements yet.', ERR.video_spread); return; }
  const cc = v.claim_check;
  const cards = v.rows.map((r) => r.ok ? `<article class="card">
      <h3>Test ${esc(r.test_id)} · ${esc(r.thickness_um)} µm PMMA, ${esc(r.sample_width_cm)} cm wide · ${esc(r.view)}</h3>
      <img src="${esc(r.figure)}" alt="Tracked flame front for test ${esc(r.test_id)}" width="800" height="500" loading="lazy" class="fig">
      <dl><dt>Spread rate</dt><dd><strong>${fmt(r.spread_mm_s, 2)} ± ${fmt(r.spread_mm_s_sd, 2)} mm/s</strong>
        <span class="muted">(mask sensitivity ${fmt(r.spread_mm_s_scale_range[0], 2)}-${fmt(r.spread_mm_s_scale_range[1], 2)})</span></dd>
      <dt>Front</dt><dd>${fmt(r.front_px_s, 2)} ± ${fmt(r.front_px_s_se, 2)} px/s over ${esc(r.n_stills)} stills</dd>
      <dt>Scale</dt><dd>flame width ${fmt(r.lateral_extent_px, 1)} px = ${esc(r.sample_width_cm)} cm (assumption) → ${fmt(r.mm_per_px, 3)} mm/px</dd>
      <dt>Flags</dt><dd>${esc((r.flags || []).join(', '))} · confidence ${esc(r.confidence)}</dd>
      <dt>File</dt><dd class="mono">${esc(r.file)} · sha256 ${esc(r.sha256.slice(0, 12))}…</dd></dl>
    </article>` : `<article class="card"><h3>Test ${esc(r.test_id)}</h3><p class="muted">${esc(r.reason)}</p></article>`).join('');
  const side = (v.side_view || []).filter((x) => x.ok).map((x) => `<li>Side-view video ${esc(x.test_id)}: front ${fmt(x.front_px_s, 2)} px/s. ${esc(x.note)}</li>`).join('');
  const st = cc ? cc.status : '';
  const cls = st === 'consistent' ? 'consistent' : st === 'tension' ? 'conflict' : 'tension';
  const claim = cc ? `<div class="card check" style="margin-bottom:12px"><span class="verdict ${cls}">${esc(st.toUpperCase())}</span>
      <h3>Report: highest spread rate for 100-µm PMMA in microgravity “about 2.2 mm/s”</h3>
      <p>Highest re-measured: <strong>${fmt(cc.max_measured_mm_s, 2)} ± ${fmt(cc.max_measured_sd, 2)} mm/s</strong> (test ${esc(cc.max_test)});
      tolerance ±${fmt(cc.tolerance_mm_s, 2)}; scale range ${esc(cc.scale_range_mm_s.join('-'))} mm/s. ${esc(cc.note)}</p>
      <div class="refs-title">Sources</div>${refHTML(cc.claim)}${refHTML(cc.timing_ref)}</div>` : '';
  el.innerHTML = claim + `<div class="grid-cards">${cards}</div>` + (side ? `<ul class="muted">${side}</ul>` : '');
}

// ---------- consistency checks ----------
// Per-sample ground (1g) test vs microgravity burn, from material_screen.json (read only).
const SCREEN_BADGE = {
  'both burned': ['ms-agree', 'agree'],
  'neither burned': ['ms-agree', 'agree'],
  '1g burned, ug did not': ['ms-blue', '1g conservative'],
  'ug burned, 1g did not': ['ms-red', '1g NOT conservative'],
};
function renderScreen() {
  const s = D.material_screen;
  const el = $('screenBody');
  const rows = s?.rows || [];
  if (!rows.length) { el.innerHTML = noData('No material screen yet.', ERR.material_screen); return; }
  const body = rows.map((r) => {
    const [cls, label] = SCREEN_BADGE[r.verdict] || ['ms-grey', r.verdict];
    const mat = r.material_id ? esc(MAT.get(r.material_id)?.name || r.material_id) : '<span class="muted">not stated</span>';
    return `<tr>
      <td>${esc(r.sample)}</td>
      <td>${mat}</td>
      <td>${esc(r.o2_text || '-')}</td>
      <td>${esc(r.flow_cm_s || '-')} · ${esc(r.flow_direction || '-')}</td>
      <td>${esc(r.ug_cell_raw ?? '-')}</td>
      <td>${esc(r.g1_burn_length ?? '-')}</td>
      <td><span class="ms-badge ${cls}" title="${esc(r.verdict)}">${esc(label)}</span></td>
    </tr>`;
  }).join('');
  const src = s.source || {};
  const doi = src.doi ? `<a href="https://doi.org/${esc(encodeURI(src.doi))}" target="_blank" rel="noopener">doi:${esc(src.doi)}</a>` : '';
  const pageUrl = safeUrl(src.url);
  const notes = (s.notes || []).map((n) => `<li>${esc(n)}</li>`).join('');
  el.innerHTML = `
    <p class="caption">Each row is one sample burned in a 1g Earth test and in microgravity on Saffire-II. Burn cells are the raw PSI table text; the verdict only compares whether each one burned.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Sample</th><th>Material</th><th>O2</th><th>Flow cm/s</th><th>Microgravity burn</th><th>1g burn</th><th>Verdict</th></tr></thead>
      <tbody>${body}</tbody>
    </table></div>
    ${notes ? `<h3>Notes (Verbatim from PSI-99)</h3><ul class="muted">${notes}</ul>` : ''}
    <p class="caption">Source: ${pageUrl ? `<a href="${pageUrl}" target="_blank" rel="noopener">${esc(src.title || src.id)}</a>` : esc(src.title || src.id || '-')}${doi ? ` · ${doi}` : ''}</p>`;
}

// ---------- BASS-II per-test outcomes (test_outcomes.json, read only) ----------
const TEST_BADGE = {
  burns_sustained: ['ts-burn', 'burns'],
  blowoff_extinction: ['ts-blow', 'blowoff'],
  quench_extinction: ['ts-quench', 'quench'],
  self_extinguished: ['ts-self', 'self-extinguished'],
  no_ignition: ['ts-none', 'no ignition'],
};
function testBadge(state) {
  const [cls, label] = TEST_BADGE[state] || ['ts-none', state];
  return `<span class="ms-badge ${cls}">${esc(label)}</span>`;
}
function renderTests() {
  const t = D.test_outcomes;
  const el = $('testsBody');
  const groups = t?.groups || [];
  if (!groups.length) { el.innerHTML = noData('No per-test outcomes yet.', ERR.test_outcomes); return; }
  const total = groups.reduce((a, g) => a + g.n, 0);
  $('testsTitle').textContent = `BASS-II Flight Tests by Material (${total} tests)`;
  const o2 = (arr) => (arr && arr.length ? arr.map((v) => `${fmt(v, 2)}%`).join(', ') : 'none');
  el.innerHTML = `<div class="grid-cards">${groups.map((g) => {
    const counts = Object.entries(g.counts_by_state || {})
      .map(([s, c]) => `${testBadge(s)} ${esc(c)}`).join(' &nbsp; ');
    const ext = !g.extinguished_o2_pct ? 'none'
      : g.extinguished_o2_pct[0] === g.extinguished_o2_pct[1] ? `${fmt(g.extinguished_o2_pct[0], 2)}%`
      : `${fmt(g.extinguished_o2_pct[0], 2)}-${fmt(g.extinguished_o2_pct[1], 2)}%`;
    const rows = (g.tests || []).map((x) => `<tr class="${x.qa_status === 'flagged' ? 'muted' : ''}">
      <td>${esc(x.test_id)}</td>
      <td>${testBadge(x.state)}</td>
      <td>${esc(fmt(x.o2_pct, 2))}</td>
      <td>${x.flow_cm_s == null ? '-' : esc(fmt(x.flow_cm_s, 2))}</td>
      <td>${x.qa_status === 'flagged' ? '<span class="ms-badge ts-flag">flagged</span>' : esc(x.qa_status)}</td>
      <td class="ts-quote">${esc(x.quote)}</td>
      <td><button type="button" class="chip" data-obs="${esc(x.obs_id)}">Provenance</button></td>
    </tr>`).join('');
    return `<article class="card">
      <h3>${esc(g.material_name)} · ${esc(g.geometry)}</h3>
      <p>${g.n} test${g.n === 1 ? '' : 's'}${g.n_flagged ? `, ${g.n_flagged} flagged` : ''}</p>
      <p>${counts}</p>
      <p class="muted">Burned to completion at O2: ${esc(o2(g.burned_o2_pct))}<br>Extinguished at O2: ${esc(ext)}</p>
      <details><summary>Tests (${(g.tests || []).length})</summary>
        <div class="table-wrap"><table class="ts-table">
          <thead><tr><th>Test</th><th>State</th><th>O2 %</th><th>Flow cm/s</th><th>QA</th><th>Quote</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </details>
    </article>`;
  }).join('')}</div>`;
  el.querySelectorAll('button[data-obs]').forEach((btn) => btn.addEventListener('click', () => openProvenance(btn.dataset.obs)));
}

function renderChecks() {
  const c = D.contradictions;
  const el = $('checksBody');
  const items = (c && c.items) || [];
  if (!items.length) { el.innerHTML = noData('No consistency checks yet.', ERR.contradictions); return; }
  const order = { conflict: 0, tension: 1, consistent: 2 };
  items.sort((a, b) => order[a.verdict] - order[b.verdict]);
  el.innerHTML = `<div class="grid-cards">${items.map((it) => {
    const obs = (it.observation_ids || []).slice(0, 30).map((id) => `<button type="button" class="chip" data-obs="${esc(id)}">${esc(shortId(id))}</button>`).join(' ');
    const more = (it.observation_ids || []).length > 30 ? ` <span class="muted">+${it.observation_ids.length - 30} more</span>` : '';
    return `<article class="card check ${esc(it.verdict)}">
      <span class="verdict ${esc(it.verdict)}">${esc(it.verdict.toUpperCase())}</span> <span class="muted">${esc(it.kind.replace(/_/g, ' '))}</span>
      <h3>${esc(it.title)}</h3><p>${esc(it.detail)}</p>
      ${(it.refs || []).length ? `<div class="refs-title">Sources</div>${it.refs.map(refHTML).join('')}` : ''}
      ${obs ? `<div class="refs-title">Observations</div><div class="chips">${obs}${more}</div>` : ''}
    </article>`;
  }).join('')}</div>`;
  el.querySelectorAll('button[data-obs]').forEach((btn) => btn.addEventListener('click', () => openProvenance(btn.dataset.obs)));
}

// ---------- footer ----------
// ---------- AI analyst: recorded real runs ----------
function renderAnalyst() {
  const a = D.analyst_runs;
  const el = $('analystBody');
  if (!a || !(a.runs || []).length) { el.innerHTML = noData('No recorded analyst runs yet.', ERR.analyst_runs); return; }
  const runs = a.runs.map((r) => {
    const calls = (r.calls || []).map((c) => `<span class="run-call">${esc(c.tool)}(${esc(c.args && c.args !== '{}' ? c.args : '')})</span>`).join('');
    const body = r.ok
      ? `<div class="run-a">${esc(r.answer)}</div>`
      : `<div class="run-a refused"><span class="verdict conflict">REFUSED BY THE GUARD</span> ${esc(r.reason || '')}${r.answer ? `\n\nRejected draft: ${esc(r.answer)}` : ''}</div>`;
    const raw = (r.calls || []).map((c) => `${c.tool} -> ${c.result}`).join('\n');
    return `<article class="run"><p class="run-q">${esc(r.question)}</p>
      <div class="run-meta">Model: <span class="mono">${esc(r.model)}</span> · ${(r.calls || []).length} tool call${(r.calls || []).length === 1 ? '' : 's'}</div>
      <div class="run-calls">${calls}</div>${body}
      ${r.review ? `<div class="warn"><strong>Team review:</strong> ${esc(r.review)}</div>` : ''}
      ${raw ? `<details><summary>Tool results the answer had to use</summary><pre>${esc(raw)}</pre></details>` : ''}</article>`;
  }).join('');
  el.innerHTML = `<p class="caption">Runtime: ${esc(a.runtime)}. Guard: ${esc(a.guard)} Recorded ${esc(fmtDate(a.recorded_at))}.</p>${runs}`;
}

// ---------- key numbers (all from the exported data files) ----------
function renderStats() {
  const el = $('stats');
  const m = D.model, b = D.bundle, v = D.validation, c = D.contradictions;
  const tiles = [];
  if (m && m.min_o2) {
    const mo = m.min_o2;
    tiles.push(`<div class="stat flame"><div class="stat-label">Lowest oxygen where PMMA keeps burning in orbit</div>
      <div class="stat-value">${(mo.p50 * 100).toFixed(1)}%<span class="unit">O2</span></div>
      <div class="stat-note">90 % band ${(mo.p05 * 100).toFixed(1)}-${(mo.p95 * 100).toFixed(1)}%. Earth screening uses <strong>15.4%</strong>.</div></div>`);
  }
  const g = (c && c.items || []).find((x) => x.id === '1g-limit-vs-flight');
  if (g) {
    tiles.push(`<div class="stat"><div class="stat-label">Flames that burned below the Earth limit</div>
      <div class="stat-value">${esc(g.numbers.n_burning_below)}</div>
      <div class="stat-note">lowest at <strong>${Number(g.numbers.lowest_burning_pct).toFixed(1)}% O2</strong> in ISS and drop-tower tests</div></div>`);
  }
  const f = (v && v.folds || []).find((x) => x.fold_id === 'loco-bass-ii-zgrf');
  if (f && f.metrics && f.baseline) {
    tiles.push(`<div class="stat blue"><div class="stat-label">Trained on the ISS, tested on the drop tower</div>
      <div class="stat-value">${(f.metrics.median_abs_rel_error * 100).toFixed(1)}%</div>
      <div class="stat-note">boundary error vs <strong>${(f.baseline.median_abs_rel_error * 100).toFixed(1)}%</strong> for the Earth rule</div></div>`);
  }
  if (b) {
    const src = (b.sources || []).length;
    tiles.push(`<div class="stat green"><div class="stat-label">Observations, each traced to a source</div>
      <div class="stat-value">${esc((b.observations || []).length)}</div>
      <div class="stat-note"><strong>${src}</strong> NASA documents and datasets, hash-checked</div></div>`);
  }
  el.innerHTML = tiles.join('');
  el.hidden = !tiles.length;
}

function initReveal() {
  const els = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window) || matchMedia('(prefers-reduced-motion: reduce)').matches) {
    els.forEach((e) => e.classList.add('in'));
    return;
  }
  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
  }), { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });
  els.forEach((e) => io.observe(e));
  // anything already on screen, or jumped to via #anchor, shows immediately
  setTimeout(() => els.forEach((e) => { if (e.getBoundingClientRect().top < innerHeight) e.classList.add('in'); }), 50);
  window.addEventListener('hashchange', () => els.forEach((e) => e.classList.add('in')), { once: true });
}

function renderFooter() {
  const m = D.model;
  $('footerModel').textContent = m ? `model ${m.model_id} ${m.model_version}` : 'model: no data yet';
}

// ---------- presentation mode: ?demo=1, number keys glide to each talking point ----------
function initDemoMode() {
  if (new URLSearchParams(location.search).get('demo') !== '1') return;
  const stops = {
    1: { sel: '#top' },                       // intro + challenge: hero with the flight flame
    2: { sel: '#ai' },                        // name + tagline: How the AI Works
    3: { sel: '#stats' },                     // key insight: 13.6 % vs 15.4 %
    4: { sel: '#envelope', view: '2d' },      // the learned boundary, 2D with the 15.4 % line
    5: { sel: '#analyst' },                   // the AI analyst
    6: { sel: '#habitats' },                  // impact: Moon and Mars air, no data yet
    7: { sel: '#experiments' },               // future: next experiments
  };
  document.querySelectorAll('.reveal').forEach((e) => e.classList.add('in'));   // no fade-ins mid-recording
  addEventListener('keydown', (ev) => {
    const stop = stops[ev.key];
    if (!stop || (ev.target instanceof Element && ev.target.closest('input, select, textarea'))) return;
    ev.preventDefault();
    if (stop.view) {
      const b = document.querySelector(`.toggle button[data-view="${stop.view}"]`);
      if (b && b.getAttribute('aria-pressed') !== 'true') b.click();
    }
    const el = document.querySelector(stop.sel);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

boot().then(() => { initReveal(); initDemoMode(); });

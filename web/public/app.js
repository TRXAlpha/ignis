// IGNIS frontend. Plain ES module, no build step.
// Reads only public/data/*.json. ?fixtures=1 switches to ../dev-fixtures/ (fake values).

const FIXTURES = new URLSearchParams(location.search).get('fixtures') === '1';
const BASE = FIXTURES ? '../dev-fixtures/' : 'data/';
const FILES = ['bundle', 'model', 'validation', 'recommendations', 'habitats'];

const $ = (id) => document.getElementById(id);

const COL = {
  bg: '#0b0e14', paper: '#131821', grid: '#283042', text: '#dfe5ee', muted: '#8d98ab',
  accent: '#7aa2f7', ok: '#3ddc84', bad: '#ff5d5d', star: '#ffd166', other: '#9aa3b2',
};
const CS = 'YlOrRd';
const STATE_STYLE = {
  burns_sustained: { color: '#3ddc84', symbol: 'circle', label: 'burns sustained' },
  blowoff_extinction: { color: '#000000', symbol: 'x', label: 'blowoff extinction' },
  quench_extinction: { color: '#ff5d5d', symbol: 'circle', label: 'quench extinction' },
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
    ['footer', renderFooter],
  ];
  for (const [label, fn] of steps) {
    try { fn(); } catch (e) {
      console.error(`[ignis] ${label} failed`, e);
      const target = { envelope: 'envelopeStatus', provenance: 'obsStatus', validation: 'validationBody', experiments: 'experimentsBody', habitats: 'habitatsBody', footer: null }[label];
      if (target) $(target).innerHTML = `<div class="empty"><strong>Render error</strong>${esc(e.message)}</div>`;
    }
  }
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
    ? `<strong>Minimum O2 (p50): ${pct(mo.p50)}</strong> at stretch rate a = ${fmt(mo.at_x, 3)} 1/s.
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

  // 2D boundary
  const traces = [];
  // heatmap
  traces.push({
    type: 'heatmap', x: xs, y: ysPct, z: m.grid.p_burns, zmin: 0, zmax: 1, colorscale: CS,
    colorbar: { title: 'P(burns)', tickformat: '.0%', tickfont: { color: cs.text }, titlefont: { color: cs.text } },
    hovertemplate: 'a=%{x:.3g} 1/s<br>O2=%{y:.1f}%<br>P(burns)=%{z:.2f}<extra></extra>',
    name: 'P(burns) grid', showlegend: false,
  });
  // 90% band: p05 (no fill) then p95 filled back to p05
  const b = m.boundary;
  if (b && b.x) {
    traces.push({ type: 'scatter', mode: 'lines', x: b.x, y: b.o2_p05.map((v) => v * 100), line: { width: 0 }, hoverinfo: 'skip', showlegend: false });
    traces.push({ type: 'scatter', mode: 'lines', x: b.x, y: b.o2_p95.map((v) => v * 100), line: { width: 0 }, fill: 'tonexty', fillcolor: 'rgba(122,162,247,0.22)', name: '90% band (p05 to p95)', hoverinfo: 'skip' });
    traces.push({ type: 'scatter', mode: 'lines', x: b.x, y: b.o2_p50.map((v) => v * 100), line: { color: COL.accent, width: 3 }, name: 'O2 boundary (p50)', hovertemplate: 'a=%{x:.3g} 1/s<br>p50 O2=%{y:.1f}%<extra></extra>' });
  }
  // observation points, grouped by state
  const byState = new Map();
  for (const p of m.points) {
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
      text: list.map((p) => `${p.id}<br>${p.series || ''}`),
      marker: state === 'blowoff_extinction'
        ? { symbol: 'x', size: 13, color: '#000000', line: { color: '#000000', width: 3 } }
        : { symbol: st.symbol, size: 11, color: st.color, line: { color: '#000', width: 1 } },
      hovertemplate: `%{text}<br>${esc(st.label || state)}<br>a=%{x:.3g} 1/s, O2=%{y:.1f}%<br><i>click for provenance</i><extra></extra>`,
    });
  }
  // next-experiment stars
  if (recItems.length) {
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
  for (const bl of m.baselines || []) {
    const y = bl.o2 * 100;
    traces.push({ type: 'scatter', mode: 'lines', x: [xMin, xMax], y: [y, y], line: { color: COL.muted, width: 1.5, dash: 'dash' }, showlegend: false, hoverinfo: 'skip' });
    shapesText.push({ x: xMax, y, xref: 'x', yref: 'y', text: `${bl.label} (${fmt(y, 1)}%)`, showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { color: COL.muted, size: 11 } });
  }
  const allY = ysPct.concat(m.points.map((p) => p.y * 100));
  const yLo = Math.min(...allY) - 0.5, yHi = Math.max(...allY) + 0.5;

  const layout2d = {
    paper_bgcolor: cs.paper, plot_bgcolor: cs.paper, font: { color: cs.text },
    margin: { l: 56, r: 10, t: 10, b: 50 }, height: 500,
    xaxis: {
      type: 'log', title: 'Stretch rate a (1/s)', color: cs.text, gridcolor: cs.grid, zerolinecolor: cs.grid,
      range: [Math.log10(xMin) - 0.05, Math.log10(xMax) + 0.05], autorange: false,
    },
    yaxis: { title: 'O2 (%)', range: [yLo, yHi], color: cs.text, gridcolor: cs.grid },
    legend: { orientation: 'h', x: 0, y: -0.2, font: { color: cs.text, size: 11 } },
    annotations: shapesText,
    hovermode: 'closest',
  };
  Plotly.newPlot('plot2d', traces, layout2d, PLOT_CFG).then((el) => {
    el.on('plotly_click', (ev) => {
      const id = ev.points?.[0]?.customdata;
      if (typeof id === 'string' && !id.startsWith('rec:')) openProvenance(id);
    });
  });
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
  if (!v || !(v.folds || []).length) {
    el.innerHTML = noData('No validation folds yet.', ERR.validation);
    return;
  }
  const metricKeys = ['rmse_log10', 'mae_log10', 'median_abs_rel_error', 'nlpd', 'brier'];
  const head = metricKeys.map((k) => `<th>${esc(k)}</th>`).join('');
  const rows = v.folds.map((f) => {
    const m = f.metrics || {};
    const b = f.baseline || {};
    const cells = metricKeys.map((k) => {
      if (m[k] == null && b[k] == null) return '<td>-</td>';
      return `<td><div>${fmt(m[k], 3)}</div><span class="sub">baseline ${fmt(b[k], 3)}</span></td>`;
    }).join('');
    const cov = (m.coverage || []).map((c) => `${pct(c.nominal, 0)} → ${pct(c.empirical, 0)}`).join(', ') || '-';
    return `<tr>
      <td class="mono">${esc(f.fold_id)}</td>
      <td>${esc(CAMP.get(f.held_out_campaign_id)?.name || f.held_out_campaign_id)}</td>
      <td>${esc(f.n_train)}</td><td>${esc(f.n_test)}</td>
      ${cells}
      <td>${esc(cov)}</td>
    </tr>`;
  }).join('');
  const lims = (v.limitations || []).map((l) => `<li>${esc(l)}</li>`).join('');
  el.innerHTML = `
    <p>${esc(v.summary || '')}</p>
    <div class="warn"><strong>Limitations</strong>${lims ? `<ul>${lims}</ul>` : ' none listed'}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>Fold</th><th>Held-out campaign</th><th>n train</th><th>n test</th>${head}<th>Coverage (nominal → empirical)</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="caption">Each metric shows the GP model value with the scaling-law-only baseline underneath. Leave-one-campaign-out folds.</p>`;
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
    <h3>Constraint set: ${esc(cs.name || cs.id || '-')}</h3>
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
      ? `<div class="big">${pct(pr.p_burns, 0)}</div><div class="muted">P(sustained burning)</div>`
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

// ---------- footer ----------
function renderFooter() {
  const m = D.model;
  $('footerModel').textContent = m ? `model ${m.model_id} ${m.model_version}` : 'model: no data yet';
}

boot();

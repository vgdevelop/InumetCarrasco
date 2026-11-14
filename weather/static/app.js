const state = { stations: [], variables: [], selected: [], station: null };
const $ = (id) => document.getElementById(id);
const formatDate = (value) => value ? new Intl.DateTimeFormat("es-UY", {dateStyle:"short", timeStyle:"short"}).format(new Date(value)) : "Sin datos";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const formatNumber = (value) => new Intl.NumberFormat("es-UY", {maximumFractionDigits: 2}).format(value);

async function api(path) {
  const response = await fetch(path, {headers:{"Accept":"application/json"}});
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

function setStatus(ok, text) {
  $("statusDot").className = `dot ${ok ? "ok" : "bad"}`;
  $("statusText").textContent = text;
}

async function loadStations() {
  const [stations, status] = await Promise.all([api("/api/stations"), api("/api/status")]);
  state.stations = stations;
  $("stationSelect").innerHTML = stations.map(s => `<option value="${escapeHtml(s.station_key)}">${escapeHtml(s.public_name || s.name)}</option>`).join("");
  const latest = status.database.latest_observation;
  setStatus(status.collector?.status === "success", latest ? `Datos al ${formatDate(latest)}` : "Esperando primera captura");
  if (stations.length) await selectStation(stations[0].station_key);
}

async function selectStation(key) {
  state.station = state.stations.find(s => s.station_key === key);
  state.variables = await api(`/api/stations/${encodeURIComponent(key)}/variables`);
  const preferred = [47, 25, 29, 45];
  state.selected = preferred.filter(id => state.variables.some(v => v.variable_id === id)).slice(0, 4);
  if (!state.selected.length) state.selected = state.variables.slice(0, 4).map(v => v.variable_id);
  renderStation(); renderVariablePicker();
  await refreshData();
}

function renderStation() {
  const s = state.station;
  if (!s) return;
  $("stationMeta").innerHTML = [s.code_omm && `OMM ${escapeHtml(s.code_omm)}`, s.code_oaci && `OACI ${escapeHtml(s.code_oaci)}`, s.altitude_m != null && `${escapeHtml(s.altitude_m)} m`, `${s.variable_count} variables`].filter(Boolean).map(v => `<span>${v}</span>`).join("");
}

function renderVariablePicker() {
  $("variablePicker").innerHTML = state.variables.map(v => `<label><input type="checkbox" value="${v.variable_id}" ${state.selected.includes(v.variable_id) ? "checked" : ""}>${escapeHtml(v.name)}</label>`).join("");
  $("variablePicker").querySelectorAll("input").forEach(input => input.addEventListener("change", async (event) => {
    const id = Number(event.target.value);
    if (event.target.checked && state.selected.length >= 4) { event.target.checked = false; return; }
    state.selected = event.target.checked ? [...state.selected, id] : state.selected.filter(v => v !== id);
    await loadSeries();
  }));
}

function renderLatest(rows) {
  $("latestGrid").innerHTML = rows.map(row => {
    const value = row.numeric_value ?? row.text_value ?? "—";
    return `<article class="metric"><div class="metric-name">${escapeHtml(row.name)}</div><div class="metric-value">${escapeHtml(value)} <small>${escapeHtml(row.unit || "")}</small></div><time>${formatDate(row.observed_at)}</time></article>`;
  }).join("") || '<div class="empty">No hay observaciones para esta estación.</div>';
  $("updatedAt").textContent = rows.length ? `Actualizado ${formatDate(rows.reduce((a,b) => a.observed_at > b.observed_at ? a : b).observed_at)}` : "";
}

function chartSvg(series, chartIndex) {
  const points = series.points.filter(p => p.value != null);
  if (points.length < 2) return '<div class="empty">No hay suficientes valores numéricos en este periodo.</div>';
  const values = points.map(point => Number(point.value));
  const min = Math.min(...values), max = Math.max(...values), average = values.reduce((sum, value) => sum + value, 0) / values.length, spread = max-min || 1;
  const width=700, height=280, left=48, right=18, top=22, bottom=42;
  const coordinates = points.map((point,index) => ({x:left+index*(width-left-right)/(points.length-1), y:height-bottom-(Number(point.value)-min)*(height-top-bottom)/spread, point}));
  const line = coordinates.map(item => `${item.x},${item.y}`).join(" ");
  const area = `${left},${height-bottom} ${line} ${width-right},${height-bottom}`;
  const grid = [0, .25, .5, .75, 1].map(ratio => {
    const y = top + ratio*(height-top-bottom), value = max-ratio*spread;
    return `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}"/><text class="chart-label" x="2" y="${y+4}">${escapeHtml(formatNumber(value))}</text>`;
  }).join("");
  const hitPoints = coordinates.map(({x,y,point}) => `<circle class="chart-point" tabindex="0" cx="${x}" cy="${y}" r="9" data-time="${escapeHtml(point.observed_at)}" data-value="${escapeHtml(point.value)}" data-name="${escapeHtml(series.name)}" data-unit="${escapeHtml(series.unit || "")}"/>`).join("");
  return `<div class="chart-summary"><span>Mín. ${escapeHtml(formatNumber(min))} ${escapeHtml(series.unit || "")}</span><span>Máx. ${escapeHtml(formatNumber(max))} ${escapeHtml(series.unit || "")}</span><span>Prom. ${escapeHtml(formatNumber(average))} ${escapeHtml(series.unit || "")}</span></div><svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Serie ${escapeHtml(series.name)}"><defs><linearGradient id="areaGradient-${chartIndex}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#68e0ad"/><stop offset="1" stop-color="#68e0ad" stop-opacity="0"/></linearGradient></defs>${grid}<polygon class="chart-fill" style="fill:url(#areaGradient-${chartIndex})" points="${area}"/><polyline class="chart-line" points="${line}"/>${hitPoints}<text class="chart-label" x="${left}" y="${height-10}">${escapeHtml(formatDate(points[0].observed_at))}</text><text class="chart-label" text-anchor="end" x="${width-right}" y="${height-10}">${escapeHtml(formatDate(points.at(-1).observed_at))}</text></svg>`;
}

function bindChartTooltips() {
  document.querySelectorAll(".chart-card").forEach(card => {
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    tooltip.hidden = true;
    card.appendChild(tooltip);
    card.querySelectorAll(".chart-point").forEach(point => {
      const show = () => {
        tooltip.innerHTML = `<strong>${escapeHtml(point.dataset.name)}</strong><span>${formatDate(point.dataset.time)}</span><span>Valor: ${escapeHtml(formatNumber(Number(point.dataset.value)))} ${escapeHtml(point.dataset.unit)}</span>`;
        const pointBox = point.getBoundingClientRect(), cardBox = card.getBoundingClientRect();
        tooltip.style.left = `${Math.min(cardBox.width - 24, Math.max(24, pointBox.left - cardBox.left + pointBox.width / 2))}px`;
        tooltip.style.top = `${Math.max(100, pointBox.top - cardBox.top)}px`;
        tooltip.hidden = false;
      };
      point.addEventListener("mouseenter", show); point.addEventListener("focus", show);
      point.addEventListener("mouseleave", () => { tooltip.hidden = true; });
      point.addEventListener("blur", () => { tooltip.hidden = true; });
    });
  });
}

async function loadSeries() {
  if (!state.station || !state.selected.length) { $("charts").innerHTML='<div class="empty">Seleccione al menos una variable.</div>'; return; }
  const hours = $("hoursSelect").value;
  const data = await api(`/api/series?station=${encodeURIComponent(state.station.station_key)}&variables=${state.selected.join(",")}&hours=${hours}`);
  $("charts").innerHTML = data.series.map((s, index) => `<article class="chart-card"><div class="chart-title"><strong>${escapeHtml(s.name)}</strong><span>${escapeHtml(s.unit || "sin unidad")} · ${s.points.length} puntos</span></div>${chartSvg(s, index)}</article>`).join("") || '<div class="empty">No hay datos en el periodo seleccionado.</div>';
  bindChartTooltips();
}

function downloadExcel() {
  if (!state.station || !state.selected.length) return;
  const query = new URLSearchParams({station: state.station.station_key, variables: state.selected.join(","), hours: $("hoursSelect").value, generado: Date.now()});
  window.location.assign(`/api/export.xlsx?${query}`);
}

async function refreshData() {
  if (!state.station) return;
  try {
    const latest = await api(`/api/latest?station=${encodeURIComponent(state.station.station_key)}`);
    renderLatest(latest); await loadSeries(); setStatus(true, "Servicio actualizado");
  } catch (error) { setStatus(false, "No se pudo actualizar"); console.error(error); }
}

$("stationSelect").addEventListener("change", e => selectStation(e.target.value));
$("hoursSelect").addEventListener("change", loadSeries);
$("refreshButton").addEventListener("click", refreshData);
$("downloadButton").addEventListener("click", downloadExcel);
loadStations().catch(error => { setStatus(false, "Servicio no disponible"); $("latestGrid").innerHTML=`<div class="empty">${escapeHtml(error.message)}</div>`; });
setInterval(refreshData, 60_000);

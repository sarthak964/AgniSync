const byId = (id) => document.getElementById(id);
const setText = (id, text) => { byId(id).textContent = text; };
const state = {catalog: null, month: null, day: null};
const plots = {responsive: true, displaylogo: false, displayModeBar: false};
const number = (value, places = 0) => value == null ? "—" : value.toLocaleString("en", {
  minimumFractionDigits: places, maximumFractionDigits: places,
});
const dateLabel = (day) => new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
}).format(new Date(day));
const monthLabel = (month) => new Intl.DateTimeFormat("en-GB", {
  month: "long", year: "numeric", timeZone: "UTC",
}).format(new Date(month + "-01"));

let requestVersion = 0;

async function getData(endpoint, params) {
  const response = await fetch("/api/" + endpoint + "?" + new URLSearchParams(params));
  if (!response.ok) throw new Error("Could not load the selected data. Try another date or refresh the page.");
  return response.json();
}

function draw(id, figure, overrides = {}, data = figure.data) {
  return Plotly.react(byId(id), data, {
    ...figure.layout, ...overrides, template: {},
    paper_bgcolor: "transparent", plot_bgcolor: "#fffdf8",
    font: {family: "Instrument Sans, Segoe UI, sans-serif", color: "#495247", size: 12},
  }, plots);
}

function table(id, rows) {
  byId(id).replaceChildren(...rows.map((values) => {
    const row = document.createElement("tr");
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    return row;
  }));
}

function renderCalendar(catalog) {
  const calendar = byId("month-calendar");
  calendar.replaceChildren();
  const header = calendar.createTHead().insertRow();
  for (const month of ["Year", ...catalog.month_names]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = month;
    header.append(cell);
  }
  const entries = new Map(catalog.calendar.map((entry) => [entry.month, entry]));
  const peak = Math.max(1, ...catalog.calendar.map((entry) => entry.activity ?? 0));
  const body = calendar.createTBody();
  for (const year of new Set(catalog.months.map((month) => month.slice(0, 4)))) {
    const row = body.insertRow();
    const label = document.createElement("th");
    label.scope = "row";
    label.textContent = year;
    row.append(label);
    for (let index = 0; index < 12; index++) {
      const month = year + "-" + String(index + 1).padStart(2, "0");
      const entry = entries.get(month);
      const cell = row.insertCell();
      if (!entry) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.month = month;
      button.textContent = entry.activity == null ? "—" :
        number(entry.activity) + (entry.delivery === "Complete delivery" ? "" : "*");
      const activity = entry.activity == null ? "activity unavailable" : number(entry.activity, 1) + " active cell-days";
      button.title = [monthLabel(month), activity, entry.source, entry.delivery].join(" · ");
      button.setAttribute("aria-label", button.title);
      if (entry.activity == null) button.classList.add("missing");
      else button.style.setProperty("--heat", 12 + 78 * Math.sqrt(entry.activity / peak) + "%");
      if (entry.activity > peak * 0.6) button.classList.add("hot");
      button.addEventListener("click", () => {
        byId("month").value = month;
        update((version) => renderMonth(month, version, false));
      });
      cell.append(button);
    }
  }
}

function drawMap() {
  if (!state.day) return;
  const figure = state.day.map;
  const enabled = new Set([...document.querySelectorAll("#map-filters input:checked")].map((item) => item.value));
  const traces = figure.data.filter((trace) => trace.mode === "lines" || enabled.has(trace.name));
  draw("cell-map", figure, {
    showlegend: false, height: 383, dragmode: "pan",
    margin: {l: 44, r: 12, t: 10, b: 43},
  }, traces);
  if (state.day.unverified.length) {
    setText("map-note", "File delivery evidence is unavailable for " + state.day.unverified.join(" and ") + " on this day.");
  } else if (traces.every((trace) => trace.mode === "lines")) {
    setText("map-note", "There are no retained hotspot cells for the selected groups on this day.");
  } else {
    setText("map-note", "Markers show 1 km cell centers. Purple diamonds mark detections from both sensors on the same day.");
  }
}

async function renderDay(day, ticket) {
  const response = await getData("day", {mode: byId("mode").value, month: state.month.month, day});
  if (ticket !== requestVersion) return;
  state.day = response;
  setText("map-date", dateLabel(day));
  setText("shared", number(response.counts["Both sensors"]));
  setText("shared-note", dateLabel(day) + " · UTC");
  for (const count of document.querySelectorAll("[data-count]")) {
    count.textContent = number(response.counts[count.dataset.count]);
  }
  await Plotly.relayout(byId("daily-chart"), {shapes: [{
    type: "line", x0: day, x1: day, y0: 0, y1: 1, yref: "paper",
    line: {color: "#30372d", width: 1.5, dash: "dot"},
  }]});
  drawMap();
}

async function renderMonth(month, ticket, preserveDay) {
  const mode = byId("mode").value;
  const percentile = byId("percentile").value;
  const response = await getData("month", {mode, month, percentile});
  if (ticket !== requestVersion) return;
  state.month = response;
  for (const button of byId("month-calendar").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.month === month));
  }
  const priorDay = byId("day").value;
  const day = preserveDay && response.days.includes(priorDay) ? priorDay : response.default_day;
  byId("day").replaceChildren(...response.days.map((date) => new Option(dateLabel(date), date)));
  byId("day").value = day;
  byId("export").href = "/download?" + new URLSearchParams({mode, month, percentile});
  const anomaly = response.anomaly;
  setText("activity", number(anomaly.activity, 1));
  setText("activity-note", anomaly.source + " · " + anomaly.delivery);
  for (const [index, sensor] of response.sensors.entries()) {
    const id = index === 0 ? "modis" : "viirs";
    setText(id, number(sensor.raw_hotspots));
    setText(id + "-note", sensor.delivery);
  }
  setText("insight-title", monthLabel(month) + (anomaly.unusually_high ? " was unusually active" : ""));
  setText("insight-text", response.summary[1]);
  const readings = Object.values(anomaly.sensor_agreement);
  const flagged = readings.filter((reading) => reading.unusually_high).map((reading) => reading.source);
  setText("agreement", readings[0].unusually_high == null ? readings[0].status :
    flagged.length === 2 ? "Both sensors crossed their historical cutoffs." :
      flagged.length === 1 ? "Only " + flagged[0] + " crossed its historical cutoff." :
        "Activity stayed at or below each sensor’s cutoff.");
  table("sensor-rows", readings.map((reading) => [reading.source, number(reading.activity), number(reading.threshold, 1)]));
  setText("baseline-label", anomaly.baseline_count + " earlier years of the same calendar month · active cell-days");
  setText("weather-summary", response.summary[2]);
  byId("weather-table").hidden = response.weather.length === 0;
  table("weather-rows", response.weather.map((row) => [
    row.metric, number(row.selected, 1) + (row.selected == null ? "" : " " + row.unit),
    number(row.historical_median, 1) + (row.historical_median == null ? "" : " " + row.unit),
  ]));
  await Promise.all([
    draw("daily-chart", response.timeline, {height: 270, clickmode: "event", margin: {l: 48, r: 15, t: 14, b: 36}}),
    draw("anomaly-chart", response.anomaly_chart, {height: 300, margin: {l: 56, r: 14, t: 10, b: 48}}),
  ]);
  if (ticket !== requestVersion) return;
  const chart = byId("daily-chart");
  chart.removeAllListeners("plotly_click");
  chart.on("plotly_click", ({points}) => {
    const selected = points[0]?.customdata;
    if (response.days.includes(selected)) {
      byId("day").value = selected;
      update((version) => renderDay(selected, version));
    }
  });
  await renderDay(day, ticket);
}

async function renderCatalog(ticket) {
  const mode = byId("mode").value;
  const catalog = await getData("catalog", {mode});
  if (ticket !== requestVersion) return;
  state.catalog = catalog;
  const min = catalog.months[0];
  const max = catalog.months.at(-1);
  setText("archive-name", byId("mode").selectedOptions[0].textContent);
  setText("archive-years", min.slice(0, 4) + "–" + max.slice(0, 4));
  setText("archive-total", number(catalog.detections) + " retained detections");
  byId("month").min = min;
  byId("month").max = max;
  if (!catalog.months.includes(byId("month").value)) byId("month").value = "2024-04";
  for (const [id, url] of Object.entries({
    "firms-source": catalog.firms, "power-source": catalog.power, "boundary-source": catalog.boundary_source,
  })) byId(id).href = url;
  setText("comparison-note", catalog.model.held_out_all ?
    catalog.model.held_out_all.months + " months held out from model fitting." : catalog.model.status);
  byId("gap-chart").hidden = !catalog.harmonization;
  renderCalendar(catalog);
  const chartTasks = [draw("sensor-chart", catalog.comparison, {height: 300, margin: {l: 49, r: 12, t: 18, b: 48}})];
  if (catalog.harmonization) chartTasks.push(draw("gap-chart", catalog.harmonization, {
    height: 235, margin: {l: 100, r: 21, t: 14, b: 50},
  }));
  await Promise.all(chartTasks);
  if (ticket !== requestVersion) return;
  await renderMonth(byId("month").value, ticket, false);
}

async function update(action) {
  const ticket = ++requestVersion;
  setText("status", "");
  try {
    await action(ticket);
  } catch (error) {
    if (ticket === requestVersion) setText("status", error.message);
  }
}

byId("mode").addEventListener("change", () => update(renderCatalog));
byId("month").addEventListener("change", () => {
  const month = byId("month").value;
  if (!state.catalog?.months.includes(month)) {
    setText("status", "Choose a month within the available archive.");
    byId("month").value = state.month?.month || "2024-04";
    return;
  }
  update((version) => renderMonth(month, version, false));
});
byId("day").addEventListener("change", () => update((version) => renderDay(byId("day").value, version)));
byId("percentile").addEventListener("change", () => update((version) => renderMonth(byId("month").value, version, true)));
byId("map-filters").addEventListener("change", drawMap);
for (const link of document.querySelectorAll(".header nav a")) {
  link.addEventListener("click", () => {
    document.querySelector(".header nav a.current")?.classList.remove("current");
    link.classList.add("current");
  });
}
update(renderCatalog);

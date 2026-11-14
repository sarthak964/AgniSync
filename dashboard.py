from calendar import month_abbr
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from zipfile import BadZipFile

from flask import Flask, abort, jsonify, render_template, request, send_file
import pandas as pd
from plotly.offline import get_plotlyjs

from src.analysis import (
    calibrate, daily_hotspot_cells, monthly_activity, seasonal_comparison, sensor_anomaly_agreement, unified_activity,
)
from src.config import DAILY_CELL_COLORS, DATA, FIRMS_ARCHIVE, GRID_CRS, GRID_METRES, POWER_URL, QUALITY, REGION, STREAMS
from src.datasets import load_cache, synthetic
from src.evidence import explain, weather_evidence
from src.exports import export_bundle
from src.observations import district
from src.sources import local_weather
from src.visuals import anomaly_chart, daily_activity_chart, daily_cell_map, harmonization_gap_chart, sensor_chart

app = Flask(__name__, template_folder="web/templates", static_folder="web/static", static_url_path="/assets")
MODES = {"archive": "NASA FIRMS archive", "synthetic": "Synthetic demonstration"}


@lru_cache(maxsize=2)
def dataset(mode):
    boundary, geometry = district()
    metadata = json.loads((DATA / "boundary-source.json").read_bytes())
    points, manifest = synthetic(geometry) if mode == "synthetic" else load_cache("firms-demo")
    weather, raw_weather = local_weather() if mode == "archive" else (None, None)
    weather_metadata = None
    if raw_weather:
        weather_metadata = {
            **raw_weather["header"],
            "parameters": raw_weather["parameters"],
            "response_geometry": raw_weather["geometry"],
            "sha256": sha256((DATA / "power-almora.json").read_bytes()).hexdigest(),
        }
    monthly = monthly_activity(points, manifest["intervals"])
    report = {
        **calibrate(monthly), "region": REGION, "grid_crs": GRID_CRS, "grid_metres": GRID_METRES,
        "stream_pair": list(STREAMS), "quality_filters": QUALITY, "mode": manifest["mode"],
        "boundary_sha256": metadata["sha256"],
    }
    return points, monthly, unified_activity(monthly, report), report, manifest, boundary, geometry.bounds, metadata, weather, weather_metadata


def data_mode():
    mode = request.args.get("mode", "archive")
    if mode not in MODES:
        abort(400, "Choose a supported data source.")
    return mode


def selected_month(history):
    default = "2024-04" if history.month.eq("2024-04").any() else history.month.iloc[-1]
    month = request.args.get("month", default)
    if not history.month.eq(month).any():
        abort(400, "Choose a month in the archive.")
    return month


def percentile_value():
    percentile = request.args.get("percentile", "90")
    if percentile not in ("75", "80", "85", "90", "95"):
        abort(400, "Choose one of the historical cutoffs.")
    return int(percentile)


def figure_json(figure):
    return json.loads(figure.to_json())


@lru_cache(maxsize=64)
def month_cells(mode, month):
    points = dataset(mode)[0]
    cells = daily_hotspot_cells(points[points.month.eq(month)])
    period = pd.Period(month, freq="M")
    days = pd.date_range(period.start_time, period.end_time.normalize()).strftime("%Y-%m-%d")
    counts = cells.groupby(["day_utc", "detected_by"]).size().unstack(fill_value=0).reindex(
        index=days, columns=list(DAILY_CELL_COLORS), fill_value=0,
    )
    return cells, counts


@app.get("/")
def index():
    return render_template("dashboard.html", modes=MODES, colors=DAILY_CELL_COLORS)


@app.get("/assets/plotly.js")
def plotly_javascript():
    return app.response_class(get_plotlyjs(), mimetype="application/javascript",
                              headers={"Cache-Control": "public, max-age=86400"})


@app.get("/healthz")
def health():
    return "ok"


@app.get("/api/catalog")
def catalog():
    mode = data_mode()
    points, _, history, report, _, _, _, metadata, _, _ = dataset(mode)
    evaluation = report.get("held_out_all")
    calendar = history[["month", "activity", "source", "delivery"]]
    return jsonify(
        months=history.month.tolist(), month_names=list(month_abbr)[1:], detections=len(points),
        calendar=json.loads(calendar.to_json(orient="records")), comparison=figure_json(sensor_chart(history)),
        harmonization=figure_json(harmonization_gap_chart(evaluation)) if evaluation else None,
        model=report, boundary_source=metadata["metadata_url"], boundary_license=metadata["license"],
        firms=FIRMS_ARCHIVE, power=POWER_URL,
    )


def month_evidence(monthly, history, weather, month, percentile):
    anomaly, earlier = seasonal_comparison(history, month, percentile)
    anomaly["sensor_agreement"] = sensor_anomaly_agreement(monthly, month, percentile)
    conditions = weather_evidence(weather, month, anomaly["baseline_years"])
    return anomaly, earlier, conditions, explain(anomaly, conditions)


@app.get("/api/month")
def month_details():
    mode = data_mode()
    _, monthly, history, _, _, _, _, _, weather, _ = dataset(mode)
    month = selected_month(history)
    anomaly, earlier, conditions, summary = month_evidence(monthly, history, weather, month, percentile_value())
    _, counts = month_cells(mode, month)
    sensors = monthly.loc[monthly.month.eq(month), ["stream", "raw_hotspots", "delivery"]]
    return jsonify(
        month=month, default_day=counts.sum(axis=1).idxmax(), days=counts.index.tolist(),
        timeline=figure_json(daily_activity_chart(counts)), anomaly_chart=figure_json(anomaly_chart(anomaly, earlier)),
        anomaly=anomaly, weather=conditions, summary=summary, sensors=json.loads(sensors.to_json(orient="records")),
    )


@app.get("/api/day")
def day_details():
    mode = data_mode()
    _, _, history, _, manifest, boundary, bounds, _, _, _ = dataset(mode)
    month = selected_month(history)
    cells, counts = month_cells(mode, month)
    day = request.args.get("day", counts.sum(axis=1).idxmax())
    if day not in counts.index:
        abort(400, "Choose a UTC day in the selected month.")
    delivered = {entry["stream"] for entry in manifest["intervals"] if entry["start"] <= day <= entry["end"]}
    return jsonify(
        counts={group: int(counts.at[day, group]) for group in DAILY_CELL_COLORS},
        unverified=[stream for stream in STREAMS if stream not in delivered],
        map=figure_json(daily_cell_map(cells[cells.day_utc.eq(day)], boundary, bounds)),
    )


@app.get("/download")
def download():
    points, monthly, history, report, manifest, _, _, metadata, weather, weather_metadata = dataset(data_mode())
    month = selected_month(history)
    anomaly, _, conditions, summary = month_evidence(monthly, history, weather, month, percentile_value())
    payload = export_bundle(month, points, monthly, history, anomaly, conditions, summary, manifest, report, metadata, weather_metadata)
    return send_file(BytesIO(payload), mimetype="application/zip", as_attachment=True,
                     download_name=f"almora-{month}-{manifest['mode']}.zip")


@app.errorhandler(OSError)
@app.errorhandler(ValueError)
@app.errorhandler(BadZipFile)
def unavailable(error):
    app.logger.error("Dashboard data unavailable: %s", error)
    return jsonify(error="The dashboard data could not be loaded. Please try again."), 503

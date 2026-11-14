import calendar as months
import hashlib
import json

import pandas as pd
import shapely
import streamlit as st

from src.analysis import (
    calibrate, daily_hotspot_cells, monthly_activity, seasonal_comparison, sensor_anomaly_agreement, unified_activity,
)
from src.config import (
    BASELINE_MIN, CUTOVER, DAILY_CELL_COLORS, DATA, FIRMS_ARCHIVE, GRID_CRS, GRID_METRES, MODIS, POWER_URL, QUALITY, REGION,
    STREAMS, VIIRS, WEATHER_COORDINATES,
)
from src.datasets import import_files, load_cache, synthetic
from src.evidence import explain, weather_evidence
from src.exports import export_bundle
from src.observations import district
from src.sources import local_weather
from src.visuals import (
    activity_calendar, anomaly_chart, coordinate_map, daily_activity_chart, daily_cell_map, harmonization_gap_chart,
    map_view, seasonal_profile, sensor_chart,
)

st.set_page_config(page_title="AgniSync | Almora fire activity", page_icon="🌐", layout="wide")


@st.cache_data(show_spinner="Loading observations…")
def get_local_data(stem, file_version):
    return load_cache(stem)


@st.cache_data(show_spinner="Cleaning and clipping FIRMS observations…")
def get_uploaded(files, geometry_wkb):
    return import_files(files, shapely.from_wkb(geometry_wkb))


@st.cache_data(show_spinner="Preparing the synthetic demo…")
def get_synthetic(geometry_wkb):
    return synthetic(shapely.from_wkb(geometry_wkb))


@st.cache_data(show_spinner=False)
def get_metrics(points, intervals):
    monthly = monthly_activity(points, intervals)
    model = calibrate(monthly)
    return monthly, model, unified_activity(monthly, model)


def show_sensor_agreement(results):
    st.subheader("Do both sensors flag this month as unusual?")
    baseline = results[MODIS]
    years = ", ".join(baseline["baseline_years"]) or "none"
    st.caption(
        f"Both sensors use the same {baseline['baseline_count']} earlier years for this calendar month ({years}). "
        f"The comparison requires complete standard deliveries from both sensors and at least {BASELINE_MIN} earlier pairs."
    )
    flagged = [stream for stream, reading in results.items() if reading["unusually_high"]]
    if baseline["unusually_high"] is None:
        st.info(baseline["status"])
    elif len(flagged) == len(STREAMS):
        st.info("Both sensors flag unusually high activity.")
    elif flagged:
        st.info(f"Only {flagged[0]} flags unusually high activity.")
    else:
        st.info("Neither sensor crosses its historical cutoff.")

    cutoff_label = f"{baseline['percentile']}th-percentile cutoff"
    rows = [
        {
            "Sensor": stream,
            "Active cell-days": reading["activity"],
            cutoff_label: reading["threshold"],
            "Delivery": reading["delivery"],
        }
        for stream, reading in results.items()
    ]
    st.dataframe(
        rows, hide_index=True, width="stretch",
        column_config={cutoff_label: st.column_config.NumberColumn(format="%.2f")},
    )
    st.caption("Each cutoff uses that sensor’s own observed active cell-days. Agreement describes satellite observations only.")


def show_daily_comparison(selected, observations, intervals, boundary, bounds):
    st.subheader("Daily hotspot comparison")
    cells = daily_hotspot_cells(observations)
    month = pd.Period(selected, freq="M")
    dates = pd.date_range(month.start_time, month.end_time.normalize()).strftime("%Y-%m-%d")
    counts = cells.groupby(["day_utc", "detected_by"]).size().unstack(fill_value=0).reindex(
        index=dates, columns=list(DAILY_CELL_COLORS), fill_value=0,
    )
    busiest = counts.sum(axis=1).idxmax()
    day_key = f"hotspot_day_{selected}"
    chart_key = f"hotspot_timeline_{selected}"

    def select_day_from_chart():
        points = st.session_state[chart_key].selection.points
        if points and points[-1]["customdata"] in dates:
            st.session_state[day_key] = points[-1]["customdata"]

    st.plotly_chart(
        daily_activity_chart(counts), width="stretch", key=chart_key, selection_mode="points",
        on_select=select_day_from_chart,
        alt="Daily counts of grid cells with hotspots from MODIS, VIIRS, or both. Choose a bar to update the map.",
    )
    day = st.selectbox(
        "Day (UTC)", dates.tolist(), index=dates.get_loc(busiest), key=day_key,
        format_func=lambda date: pd.Timestamp(date).strftime("%d %b %Y"),
        help="Choose a date here or click a bar in the chart.",
    )
    for column, label in zip(st.columns(3), DAILY_CELL_COLORS, strict=True):
        column.metric(label, f"{counts.at[day, label]:,}")
    delivered = {entry["stream"] for entry in intervals if entry["start"] <= day <= entry["end"]}
    unverified = [stream for stream in STREAMS if stream not in delivered]
    if unverified:
        st.info(f"File delivery evidence is unavailable for {', '.join(unverified)} on this date.")
    daily = cells[cells.day_utc.eq(day)]
    if daily.empty:
        st.caption("The loaded records contain no retained hotspots for this day.")
        return

    visible_groups = st.pills(
        "Detections to show on the map", list(DAILY_CELL_COLORS), default=list(DAILY_CELL_COLORS),
        selection_mode="multi",
    )
    visible = daily[daily.detected_by.isin(visible_groups)]
    if visible.empty:
        st.info("Choose a detection group with cells on this day to show it on the map.")
    else:
        st.plotly_chart(
            daily_cell_map(visible, boundary, bounds), width="stretch", key="daily_hotspot_map",
            alt="Map of Almora showing the centers of grid cells with recorded hotspots on the selected day.",
        )
    st.caption(
        "Each marker is the center of a 1 km grid cell. Purple diamonds mark cells with detections from both sensors "
        "on the same UTC day."
    )


def main():
    st.title("AgniSync")
    st.caption("Satellite fire activity in Almora district, Uttarakhand")
    try:
        boundary, geometry = district()
        boundary_metadata = json.loads((DATA / "boundary-source.json").read_text(encoding="utf-8-sig"))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        st.error(f"Almora boundary unavailable. {exc}")
        return

    with st.sidebar:
        st.header("Explore Almora")
        st.caption("Uttarakhand, India · district boundary")
        local = {
            "NASA FIRMS archive": "firms-demo",
            "Local expanded archive": "processed/firms-archives",
            "Local FIRMS API cache": "processed/firms-api",
        }
        available = {
            label: stem for label, stem in local.items()
            if all((DATA / f"{stem}.{ext}").is_file() for ext in ("parquet", "json"))
        }
        mode = st.radio("Data source", [*available, "Import FIRMS CSVs", "Synthetic demonstration"])
    weather = weather_header = None
    if mode == "Synthetic demonstration":
        st.warning("Synthetic demonstration data · Generated records for testing. Every chart and export uses synthetic hotspots.")
        points, manifest = get_synthetic(geometry.wkb)
    elif mode == "Import FIRMS CSVs":
        files = st.file_uploader("Choose Aqua MODIS and/or Suomi NPP VIIRS FIRMS CSVs", type=["csv"],
                                 accept_multiple_files=True)
        st.markdown(f"[Open the NASA FIRMS archive]({FIRMS_ARCHIVE})")
        if not files:
            st.info("Upload one or more FIRMS files. The map is available once an import succeeds.")
            return
        points, manifest, errors = get_uploaded(tuple((f.name, f.getvalue()) for f in files), geometry.wkb)
        for error in errors:
            st.error(error)
        if points is not None:
            st.info("Uploaded point files show observed activity. Delivery dates are unknown, so these files are excluded from calibration and anomaly thresholds.")
    else:
        stem = available[mode]
        try:
            stamps = tuple((DATA / f"{stem}.{extension}").stat().st_mtime_ns for extension in ("parquet", "json"))
            points, manifest = get_local_data(stem, stamps)
        except (OSError, KeyError, ValueError) as exc:
            st.error(f"Unable to load the local FIRMS cache. {exc}")
            return
    if points is None or (points.empty and not manifest["intervals"]):
        st.warning("No eligible Aqua MODIS or Suomi NPP VIIRS detections in Almora.")
        if manifest["files"]:
            st.dataframe(pd.json_normalize(manifest["files"]), hide_index=True, width="stretch")
        return

    if manifest["mode"] == "real":
        try:
            weather, weather_payload = local_weather()
            if weather_payload is not None:
                weather_path = DATA / "power-almora.json"
                weather_header = {
                    **weather_payload["header"], "parameters": weather_payload["parameters"],
                    "response_geometry": weather_payload["geometry"],
                    "sha256": hashlib.sha256(weather_path.read_bytes()).hexdigest(),
                    "cache_file_modified_utc": pd.Timestamp(weather_path.stat().st_mtime, unit="s", tz="UTC").isoformat(),
                }
        except (OSError, KeyError, TypeError, ValueError) as exc:
            st.warning(f"NASA POWER cache unavailable. {exc}")

    grouped, model, full_history = get_metrics(points, manifest["intervals"])
    years = sorted(full_history.month.str[:4].unique(), reverse=True)
    with st.sidebar:
        picked_year = st.selectbox("Year", years, index=years.index("2024") if "2024" in years else 0)
        month_options = full_history.loc[full_history.month.str.startswith(picked_year), "month"].tolist()
        april = f"{picked_year}-04"
        selected = st.selectbox(
            "Month", month_options, index=month_options.index(april) if april in month_options else 0,
            format_func=lambda month: months.month_name[int(month[5:])],
            key=f"month_{picked_year}",
        )
        year_options = sorted(years)
        displayed_years = (st.select_slider("Years on charts", options=year_options, value=(years[-1], years[0]))
                           if len(years) > 1 else (years[0], years[0]))
        st.caption("All dates and days use UTC.")

    model = {
        **model, "region": REGION, "grid_crs": GRID_CRS, "grid_metres": GRID_METRES,
        "stream_pair": list(STREAMS), "quality_filters": QUALITY, "mode": manifest["mode"],
        "boundary_sha256": boundary_metadata["sha256"],
    }
    history = full_history[full_history.month.str[:4].between(*displayed_years)]
    selected_points = points[points.month.eq(selected)]
    selected_monthly = grouped[grouped.month.eq(selected)].set_index("stream")
    selected_calendar = full_history.set_index("month").loc[selected]
    period_label = f"{months.month_name[int(selected[5:])]} {picked_year}"
    st.subheader(period_label)
    current, aqua, npp = st.columns(3)
    activity = selected_calendar.activity
    current.metric("Reference-scale active cell-days", "—" if pd.isna(activity) else f"{activity:,.1f}")
    current.caption(f"{selected_calendar.source} · {selected_calendar.delivery}")
    for column, stream in zip((aqua, npp), STREAMS, strict=True):
        count = selected_monthly.at[stream, "raw_hotspots"]
        column.metric(f"{stream} hotspots", "—" if pd.isna(count) else f"{count:,.0f}")
        column.caption(selected_monthly.at[stream, "delivery"])

    overview, timeline, investigation, sensors, sources = st.tabs([
        "Overview", "Burning calendar", "Investigate month", "Sensor comparison", "Results & sources",
    ])
    with overview:
        st.subheader("Hotspot locations")
        if len(points):
            last = points.timestamp_utc.max().strftime("%d %b %Y %H:%M UTC")
            st.caption(f"Last retained detection in this dataset · {last}")
        st.caption("Map legend · Rust = Aqua MODIS · Teal = Suomi NPP VIIRS")
        map_format = st.radio("Map display", ["Interactive map", "Coordinate view"], horizontal=True)
        if map_format == "Interactive map":
            st.pydeck_chart(map_view(selected_points, boundary, geometry.bounds), width="stretch", height=420)
        else:
            st.plotly_chart(coordinate_map(selected_points, boundary, geometry.bounds), width="stretch")
        if selected_points.empty:
            st.info("No retained points are available for this month. Check each stream’s delivery status above.")
        st.caption("A hotspot is a thermal detection. Several detections can come from the same fire, and clouds or satellite timing can hide activity.")

    with timeline:
        st.subheader("Monthly activity")
        st.caption("A 1 km grid cell with a retained hotspot on three UTC days contributes three active cell-days to its sensor’s monthly total.")
        if history.activity.notna().any():
            st.plotly_chart(activity_calendar(history), width="stretch")
            st.caption("— means missing reference-scale activity. An asterisk marks incomplete or unknown delivery. Hover over a cell for its source.")
        else:
            st.info("The displayed range has no reference-scale activity. Check Sensor comparison for available VIIRS observations.")
        st.subheader("Typical seasonal pattern")
        st.caption("Median by calendar month across comparable years in the displayed range.")
        st.plotly_chart(seasonal_profile(history), width="stretch")
        st.dataframe(history[["month", "activity", "source", "delivery"]], hide_index=True, width="stretch",
                     height=220)

    with investigation:
        st.subheader(f"How unusual was {period_label}?")
        st.caption("Retrospective comparison using the reconstructed calendar.")
        threshold = st.slider("Historical percentile threshold", min_value=75, max_value=95, value=90, step=5)
        result, earlier = seasonal_comparison(full_history, selected, threshold)
        st.plotly_chart(anomaly_chart(result, earlier), width="stretch")
        baseline_years = ", ".join(result["baseline_years"]) or "none"
        st.caption(f"Baseline · {result['baseline_count']} earlier years of this calendar month ({baseline_years}). At least {BASELINE_MIN} comparable years are required.")
        evidence = weather_evidence(weather, selected, result["baseline_years"])
        summary = explain(result, evidence)
        for sentence in summary:
            st.write(sentence)
        sensor_results = sensor_anomaly_agreement(grouped, selected, threshold)
        show_sensor_agreement(sensor_results)
        show_daily_comparison(selected, selected_points, manifest["intervals"], boundary, geometry.bounds)
        if evidence:
            st.subheader("Weather evidence")
            weather_table = pd.DataFrame(evidence)[["metric", "unit", "selected", "historical_median", "historical_count"]]
            st.dataframe(weather_table.rename(columns={
                "metric": "Daily weather summary", "unit": "Unit", "selected": "Selected period",
                "historical_median": "Historical median", "historical_count": "Historical windows",
            }), hide_index=True, width="stretch")
            lon, lat = WEATHER_COORDINATES
            st.caption(f"NASA POWER / MERRA‑2 near {lat:.2f}°N, {lon:.2f}°E · approximately 0.5° × 0.625° grid · daily UTC.")

    with sensors:
        st.subheader("Aqua MODIS and Suomi NPP VIIRS")
        st.plotly_chart(sensor_chart(history), width="stretch")
        st.write(model["status"])
        st.caption(f"Fit · {model['fit_period']} ({model['fit_months']} complete pairs). Held-out evaluation · {model['evaluation_period']} ({model['evaluation_months']} complete pairs).")
        if model["coefficient"] is not None:
            evaluation = model["held_out_all"]
            st.subheader("Monthly gap before and after adjustment")
            st.plotly_chart(
                harmonization_gap_chart(evaluation), width="stretch", key="harmonization_gap",
                alt=f"The average monthly gap from Aqua MODIS was {evaluation['raw_mae']:.1f} active cell-days "
                    f"before adjustment and {evaluation['adjusted_mae']:.1f} after adjustment.",
            )
            st.caption(
                f"The chart compares VIIRS with Aqua MODIS across the same {evaluation['months']} months "
                "held out from fitting. Smaller gaps indicate closer agreement with MODIS."
            )
            low, high = model["viirs_training_range"]
            scale = model["coefficient"]
            st.write(f"Candidate estimate = VIIRS active cell-days × **{scale:.3f}** on the Aqua MODIS reference scale.")
            outside = model["test_months_outside_training_range"]
            st.caption(f"Training range · {low}–{high} VIIRS active cell-days. Held-out metrics include {outside} out-of-range months. The unified calendar excludes out-of-range estimates.")
            if selected_calendar.outside_training_range:
                st.warning("The selected month’s VIIRS value is outside the calibration training range.")
            rows = {"All held-out months": model["held_out_all"], "Active held-out months": model["held_out_active"],
                    **model["held_out_seasonal"]}
            st.dataframe(pd.DataFrame.from_dict(rows, orient="index"), width="stretch")
            st.caption("MAE is mean absolute difference from MODIS. Bias is mean VIIRS minus MODIS. Both use active cell-days.")
        with st.expander("How the reference series is assembled"):
            st.write(model["criteria"])
            st.write(f"Before {CUTOVER}, the calendar uses Aqua MODIS. From {CUTOVER}, it uses eligible adjusted VIIRS months and falls back to MODIS where available. Each month has one reference value.")

    with sources:
        st.subheader("Selected observations")
        query = st.text_input("Search by date, sensor, or confidence").strip().casefold()
        columns = ["timestamp_utc", "latitude", "longitude", "stream", "confidence_category", "processing", "source_file"]
        display = selected_points[columns]
        if query:
            matches = display.astype(str).apply(lambda column: column.str.casefold().str.contains(query, regex=False)).any(axis=1)
            display = display[matches]
        st.dataframe(display, hide_index=True, width="stretch", height=280)
        bundle = export_bundle(
            selected, points, grouped, full_history, {**result, "sensor_agreement": sensor_results},
            evidence, summary, manifest, model,
            boundary_metadata, weather_header,
        )
        st.download_button("Download selected month (.zip)", bundle,
                           f"almora-{selected}-{manifest['mode']}.zip", mime="application/zip", on_click="ignore")
        with st.expander("Data provenance and limitations"):
            st.markdown(f"[NASA FIRMS archive]({FIRMS_ARCHIVE}) · [NASA POWER daily API]({POWER_URL})")
            st.markdown(f"[Almora district boundary]({boundary_metadata['metadata_url']}) · {boundary_metadata['license']}")
            st.write(f"Filters · {QUALITY}. Grid · {GRID_METRES} m in {GRID_CRS}.")
            st.write("Complete delivery describes the input files. Clear-sky coverage is unknown, and hotspot points do not quantify area burned.")
            st.json({"fire_inputs": manifest, "boundary": boundary_metadata, "weather": weather_header}, expanded=False)


if __name__ == "__main__":
    main()

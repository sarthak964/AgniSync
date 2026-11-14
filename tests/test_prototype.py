from io import BytesIO
import json
from zipfile import ZipFile

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.analysis import FULL, MISSING, PARTIAL, UNKNOWN, calibrate, monthly_activity, seasonal_comparison, unified_activity
from src.config import MODIS, ROOT, VIIRS
from src.datasets import import_files, synthetic
from src.evidence import weather_window
from src.exports import export_bundle
from src.observations import district


def test_import_confidence_clipping_and_cell_days():
    geometry = district()[1]
    point = geometry.representative_point()
    header = "latitude,longitude,acq_date,acq_time,satellite,confidence,version"
    csv = "\n".join([
        header,
        f"{point.y},{point.x},2024-04-01,15,A,80,6.1NRT",
        f"{point.y},{point.x},2024-04-01,0015,A,88,6.1",
        f"{point.y},{point.x},2024-04-01,16,A,30,6.1",
        f"{point.y},{point.x},2024-04-02,0015,A,88,6.1",
        f"{point.y},{point.x},2024-04-02,0020,N,n,2",
        f"{point.y},{point.x},2024-04-02,0021,N,l,2",
        f"{point.y},{point.x},2024-04-02,2400,N,h,2",
        "21,79,2024-04-02,2401,N,h,2",
        "21,79,2024-04-02,0201,N,h,2",
    ]).encode()
    points, manifest, errors = import_files([("firms.csv", csv), ("bad.csv", b"a,b\n1,2")], geometry)
    assert len(errors) == 1
    assert len(points) == 4
    assert manifest["duplicates_removed"] == 1
    assert points.iloc[0].acq_time == "0015"
    assert points.iloc[0].processing == "standard"
    assert manifest["files"][0]["rejected_rows"]["outside_district"] == 1
    assert manifest["files"][0]["rejected_rows"]["invalid_time"] == 2
    monthly = monthly_activity(points, [
        {"stream": MODIS, "start": "2024-02-01", "end": "2024-02-29", "processing": "standard"},
        {"stream": MODIS, "start": "2024-03-01", "end": "2024-03-02", "processing": "standard"},
    ]).set_index(["month", "stream"])
    assert monthly.loc[("2024-02", MODIS), "active_cell_days"] == 0
    assert monthly.loc[("2024-02", MODIS), "delivery"] == FULL
    assert pd.isna(monthly.loc[("2024-02", VIIRS), "active_cell_days"])
    assert monthly.loc[("2024-02", VIIRS), "delivery"] == MISSING
    assert monthly.loc[("2024-03", MODIS), "delivery"] == PARTIAL
    assert pd.isna(monthly.loc[("2024-03", MODIS), "raw_hotspots"])
    assert pd.isna(monthly.loc[("2024-03", MODIS), "active_cell_days"])
    assert monthly.loc[("2024-04", MODIS), "delivery"] == UNKNOWN
    assert monthly.loc[("2024-04", MODIS), "active_cell_days"] == 2
    assert monthly.loc[("2024-04", VIIRS), "active_cell_days"] == 1


def test_calibration_split_and_reference_selection():
    points, manifest = synthetic(district()[1])
    monthly = monthly_activity(points, manifest["intervals"])
    report = calibrate(monthly)
    assert report["fit_months"] == 108
    assert report["evaluation_months"] == 48
    assert report["use_adjustment"]
    assert 0.45 < report["coefficient"] < 0.8
    assert report["held_out_all"]["adjusted_mae"] < report["held_out_all"]["raw_mae"]
    calendar = unified_activity(monthly, report).set_index("month")
    assert calendar.loc["2021-04", "activity"] == calendar.loc["2021-04", "modis"]
    assert calendar.loc["2022-04", "activity"] == calendar.loc["2022-04", "viirs_adjusted"]
    assert calendar.loc["2024-04", "source"] == "MODIS fallback"
    assert calibrate(monthly.assign(active_cell_days=0))["coefficient"] is None
    assert calibrate(monthly.assign(standard_delivery=False))["coefficient"] is None


def test_zero_baseline_and_missing_weather():
    frame = pd.DataFrame({
        "month": [f"{year}-04" for year in range(2018, 2026)],
        "activity": [0, 0, 0, 0, 0, 0, 4, 100],
        "comparable": [True, True, False, True, True, True, True, True],
        "source": ["Observed MODIS"] * 8,
        "delivery": [FULL] * 8,
    })
    result, _ = seasonal_comparison(frame, "2024-04")
    assert result["baseline_count"] == 5
    assert result["median"] == 0
    assert result["unusually_high"]
    partial, _ = seasonal_comparison(frame, "2020-04")
    assert partial["unusually_high"] is None
    insufficient, _ = seasonal_comparison(frame, "2021-04")
    assert insufficient["status"] == "Insufficient same-month history."
    dates = pd.date_range("2024-03-02", "2024-03-31")
    weather = pd.DataFrame({"PRECTOTCORR": 0.0}, index=dates)
    assert weather_window(weather, "2024-04", "PRECTOTCORR") == 0
    weather.iloc[0, 0] = float("nan")
    assert weather_window(weather, "2024-04", "PRECTOTCORR") is None


def test_export_month_and_synthetic_labels():
    points, manifest = synthetic(district()[1])
    monthly = monthly_activity(points, manifest["intervals"])
    report = calibrate(monthly)
    calendar = unified_activity(monthly, report)
    selected = "2024-04"
    anomaly, _ = seasonal_comparison(calendar, selected)
    data = export_bundle(selected, points, monthly, calendar, anomaly, [], ["Test"], manifest, report, {})
    with ZipFile(BytesIO(data)) as bundle:
        points = pd.read_csv(bundle.open("observations.csv"))
        assert points.month.eq(selected).all()
        assert points["mode"].eq("synthetic").all()
        assert len(pd.read_csv(bundle.open("activity_by_sensor.csv"))) == 2
        assert len(pd.read_csv(bundle.open("calendar_month.csv"))) == 1
        assert json.load(bundle.open("anomaly.json"))["month"] == selected


def test_streamlit_modes_and_month_selection():
    app = AppTest.from_file(ROOT / "app.py", default_timeout=40).run()
    assert not app.exception
    data_source = next(item for item in app.radio if item.label == "Data source")
    data_source.set_value("Import FIRMS CSVs").run()
    assert any("Upload one or more" in item.value for item in app.info)
    next(item for item in app.radio if item.label == "Data source").set_value("Synthetic demonstration").run()
    assert not app.exception
    assert any("Synthetic demonstration data" in item.value for item in app.warning)
    next(item for item in app.selectbox if item.label == "Month").set_value("2024-05").run()
    assert not app.exception
    assert any(item.value == "May 2024" for item in app.subheader)
    next(item for item in app.radio if item.label == "Map display").set_value("Coordinate view").run()
    assert not app.exception

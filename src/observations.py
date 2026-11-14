from collections import Counter
from io import BytesIO
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer
from shapely.geometry import shape

from src.config import DATA, GRID_CRS, GRID_METRES, MODIS, VIIRS

REQUIRED = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "version"}
SATELLITES = {
    "a": MODIS, "aqua": MODIS,
    "n": VIIRS, "npp": VIIRS, "snpp": VIIRS, "suominpp": VIIRS,
}
EXPECTED_INSTRUMENT = {MODIS: "modis", VIIRS: "viirs"}
KEY = ["stream", "timestamp_utc", "latitude", "longitude"]


def district():
    document = json.loads((DATA / "almora.geojson").read_text(encoding="utf-8-sig"))
    features = document["features"]
    if len(features) != 1 or features[0]["properties"]["shapeName"] != "Almora":
        raise ValueError("Expected one Almora district feature.")
    geometry = shape(features[0]["geometry"])
    west, south, east, north = geometry.bounds
    if (geometry.geom_type not in {"Polygon", "MultiPolygon"} or not geometry.is_valid
            or not (78 < west < east < 81 and 28 < south < north < 31)):
        raise ValueError("Almora geometry is invalid or outside its expected WGS 84 extent.")
    return document, geometry


def checksum(data):
    return hashlib.sha256(data).hexdigest()


def read_fire_csv(data):
    try:
        rows = pd.read_csv(BytesIO(data), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError("Unable to read this FIRMS CSV.") from exc
    rows.columns = rows.columns.str.strip().str.lower()
    missing = REQUIRED - set(rows.columns)
    if missing:
        raise ValueError(f"FIRMS columns missing: {', '.join(sorted(missing))}.")
    if not rows.columns.is_unique:
        raise ValueError("The CSV has duplicate column names.")
    return rows


def normalize(rows, filename, district_geometry, *, mode="real", expected_stream=None):
    satellite = rows.satellite.str.strip()
    stream = satellite.str.lower().str.replace(r"[^a-z0-9]", "", regex=True).map(SATELLITES)
    instrument = stream.map(EXPECTED_INSTRUMENT)
    if "instrument" in rows:
        labeled = rows.instrument.str.strip().str.lower()
        instrument_ok = labeled.eq("") | labeled.eq(instrument)
    else:
        instrument_ok = pd.Series(True, index=rows.index)

    acquisition = rows.acq_time.str.strip()
    hhmm = acquisition.where(acquisition.str.fullmatch(r"\d{1,4}")).str.zfill(4)
    date_text = rows.acq_date.str.strip()
    iso_date = date_text.where(date_text.str.fullmatch(r"\d{4}-\d{2}-\d{2}"))
    timestamps = pd.to_datetime(iso_date + " " + hhmm, format="%Y-%m-%d %H%M", errors="coerce", utc=True)
    # Require a strict four-digit UTC time, including a valid hour and minute.
    time_ok = hhmm.str.fullmatch(r"(?:[01]\d|2[0-3])[0-5]\d", na=False)
    lat = pd.to_numeric(rows.latitude, errors="coerce")
    lon = pd.to_numeric(rows.longitude, errors="coerce")
    confidence = rows.confidence.str.strip()
    modis_value = pd.to_numeric(confidence, errors="coerce")
    modis_range = modis_value.between(0, 100) & modis_value.mod(1).eq(0)
    modis_quality = pd.cut(modis_value, [-1, 29, 79, 100], labels=["low", "nominal", "high"]).astype("string")
    viirs_quality = confidence.str.lower().map({
        "l": "low", "low": "low", "n": "nominal", "nominal": "nominal", "h": "high", "high": "high",
    })
    quality = modis_quality.where(stream.eq(MODIS) & modis_range, viirs_quality.where(stream.eq(VIIRS)))
    version = rows.version.str.strip()
    tier = version.str.upper().str.replace(r"^[0-9.]+\s*", "", regex=True).map({
        "": "standard", "NRT": "near-real-time", "RT": "real-time", "URT": "ultra-real-time",
    }).where(version.str.fullmatch(r"\d+(?:\.\d+)?\s*(?:NRT|RT|URT)?", case=False))
    rejects = Counter()
    keep = pd.Series(True, index=rows.index)
    checks = {
        "unsupported_satellite": stream.notna() if expected_stream is None else stream.eq(expected_stream),
        "wrong_instrument": instrument_ok,
        "invalid_time": timestamps.notna() & time_ok,
        "invalid_coordinates": lat.between(-90, 90) & lon.between(-180, 180),
        "invalid_confidence": quality.notna(),
        "low_confidence": quality.isin(["nominal", "high"]),
        "invalid_version": tier.notna(),
    }
    for reason, valid in checks.items():
        valid = valid.fillna(False)
        rejects[reason] = int((keep & ~valid).sum())
        keep &= valid

    positions = shapely.points(lon[keep], lat[keep])
    in_district = shapely.intersects(district_geometry, positions)
    rejects["outside_district"] = int((~in_district).sum())
    indices = rows.index[keep][in_district]
    out = pd.DataFrame({
        "timestamp_utc": timestamps,
        "acq_time": hhmm,
        "latitude": lat,
        "longitude": lon,
        "satellite": satellite,
        "instrument": instrument.str.upper(),
        "stream": stream,
        "confidence_original": confidence,
        "confidence_category": quality,
        "version": version,
        "processing": tier,
        "source_file": Path(filename).name,
        "mode": mode,
    }).loc[indices].reset_index(drop=True)
    for column in ("frp", "daynight", "scan", "track", "type"):
        if column in rows:
            values = rows.loc[indices, column].reset_index(drop=True)
            if column == "frp":
                values = pd.to_numeric(values, errors="coerce")
                values = values.where(np.isfinite(values) & values.ge(0))
            out["frp_mw" if column == "frp" else column] = values
    return out, dict(rejects)


def deduplicate(observations):
    processing_order = {"standard": 0, "near-real-time": 1, "real-time": 2, "ultra-real-time": 3}
    ordered = observations.assign(_rank=observations.processing.map(processing_order)).sort_values(
        ["_rank", "source_file"], kind="stable"
    )
    unique = ordered.drop_duplicates(KEY).drop(columns="_rank").sort_values("timestamp_utc")
    return unique.reset_index(drop=True)


def tag_grid(observations):
    project = Transformer.from_crs("EPSG:4326", GRID_CRS, always_xy=True)
    x, y = project.transform(observations.longitude.to_numpy(), observations.latitude.to_numpy())
    return observations.assign(
        day_utc=observations.timestamp_utc.dt.strftime("%Y-%m-%d"),
        month=observations.timestamp_utc.dt.strftime("%Y-%m"),
        grid_x=np.floor(x / GRID_METRES).astype("int64"),
        grid_y=np.floor(y / GRID_METRES).astype("int64"),
    )


def add_file_info(data, filename, observations, rejects, source_url, **metadata):
    available = observations.timestamp_utc
    return {
        "file": filename, "source_url": source_url, "sha256": checksum(data),
        "retained_district_rows": len(observations), "rejected_rows": rejects,
        "first_observation_utc": available.min().isoformat() if len(available) else None,
        "last_observation_utc": available.max().isoformat() if len(available) else None,
        "versions_in_retained_rows": sorted(observations.version.unique()),
        **metadata,
    }

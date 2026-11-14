from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from src.config import CUTOVER, GRID_CRS, GRID_METRES, QUALITY, REGION
from src.sources import POWER_QUERY, POWER_URL


def export_bundle(selected, observations, monthly, calendar_row, anomaly, weather, explanation,
                  manifest, calibration, boundary, weather_header=None):
    mode = manifest["mode"]
    points = observations.loc[observations.month.eq(selected)].copy()
    # An uploaded filename or optional text column can be interpreted as a formula in Excel.
    for column in points.select_dtypes(include=["object", "string"]).columns:
        values = points[column].astype("string")
        points[column] = values.mask(values.str.match(r"^\s*[=+@-]", na=False), "'" + values)
    monthly = monthly.loc[monthly.month.eq(selected)].assign(mode=mode, region=REGION)
    canonical = calendar_row.loc[calendar_row.month.eq(selected)].assign(mode=mode, region=REGION)
    metadata = {
        "mode": mode, "region": REGION, "selection_utc": selected, "boundary": boundary,
        "fire_inputs": manifest, "calibration": calibration, "cutover": CUTOVER,
        "quality_filters": QUALITY, "grid_crs": GRID_CRS, "grid_metres": GRID_METRES,
        "weather_source": {"url": POWER_URL, "query": POWER_QUERY, **weather_header} if weather_header else None,
        "metric": "At most one retained detection per satellite, projected cell and UTC day.",
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("observations.csv", points.to_csv(index=False))
        archive.writestr("activity_by_sensor.csv", monthly.to_csv(index=False))
        archive.writestr("calendar_month.csv", canonical.to_csv(index=False))
        archive.writestr("anomaly.json", json.dumps({"mode": mode, "region": REGION, **anomaly}, indent=2))
        archive.writestr("weather.json", json.dumps({"mode": mode, "evidence": weather}, indent=2))
        archive.writestr("explanation.txt", f"{REGION} | {selected} UTC | {mode.upper()}\n\n" + "\n\n".join(explanation))
        archive.writestr("provenance.json", json.dumps(metadata, indent=2, ensure_ascii=False))
    return buffer.getvalue()

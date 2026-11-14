from calendar import monthrange
from io import BytesIO
import json

import numpy as np
import pandas as pd
import shapely

from src.config import DATA, FIRMS_ARCHIVE, MODIS, STREAMS, VIIRS
from src.observations import add_file_info, checksum, deduplicate, normalize, read_fire_csv, tag_grid


def load_cache(stem):
    payload = (DATA / f"{stem}.parquet").read_bytes()
    manifest = json.loads((DATA / f"{stem}.json").read_bytes())
    if manifest["parquet_sha256"] != checksum(payload):
        raise ValueError("The FIRMS cache does not match its manifest. Rebuild the cache.")
    if manifest["boundary_sha256"] != checksum((DATA / "almora.geojson").read_bytes()):
        raise ValueError("The boundary changed. Rebuild the FIRMS cache using the current boundary.")
    return pd.read_parquet(BytesIO(payload)), manifest


def import_files(files, geometry):
    accepted, errors, points = [], [], []
    for filename, content in files:
        try:
            observations, rejects = normalize(read_fire_csv(content), filename, geometry)
        except ValueError as exc:
            errors.append(f"{filename} — {exc}")
            continue
        points.append(observations)
        accepted.append(add_file_info(content, filename, observations, rejects, FIRMS_ARCHIVE))
    manifest = {"mode": "real", "files": accepted, "intervals": []}
    if not points:
        return None, manifest, errors
    rows = pd.concat(points, ignore_index=True)
    clean = tag_grid(deduplicate(rows))
    manifest["duplicates_removed"] = len(rows) - len(clean)
    return clean, manifest, errors


def synthetic(geometry):
    rng = np.random.default_rng(42)
    west, south, east, north = geometry.bounds
    locations = []
    while len(locations) < 300:
        candidates = rng.uniform([west, south], [east, north], size=(400, 2))
        inside = shapely.contains_xy(geometry, candidates[:, 0], candidates[:, 1])
        locations.extend(candidates[inside])
    records = []
    for year in range(2013, 2026):
        for month in range(1, 13):
            seasonal = (3, 7, 15, 40, 62, 38, 3, 1, 2, 15, 10, 4)[month - 1]
            episode = 85 if (year, month) == (2024, 4) else 0
            modis_n = max(0, int(seasonal * rng.uniform(0.65, 1.4) + episode))
            viirs_n = max(0, int(modis_n * rng.uniform(1.45, 1.85)))
            for stream, count in ((MODIS, modis_n), (VIIRS, viirs_n)):
                for idx in rng.integers(0, len(locations), size=count):
                    lon, lat = locations[idx]
                    day = int(rng.integers(1, monthrange(year, month)[1] + 1))
                    records.append({
                        "latitude": str(round(lat, 5)), "longitude": str(round(lon, 5)),
                        "acq_date": f"{year}-{month:02d}-{day:02d}", "acq_time": "0745",
                        "satellite": "A" if stream == MODIS else "N",
                        "confidence": "78" if stream == MODIS else "n",
                        "version": "6.1" if stream == MODIS else "2.0",
                    })
    points, rejected = normalize(pd.DataFrame(records), "synthetic_seed_42", geometry, mode="synthetic")
    clean = tag_grid(deduplicate(points))
    intervals = [{"stream": stream, "start": "2013-01-01", "end": "2025-12-31", "processing": "standard"}
                 for stream in STREAMS]
    return clean, {"mode": "synthetic", "seed": 42, "intervals": intervals,
                   "files": [], "filter_rejections": rejected, "duplicates_removed": len(points) - len(clean)}

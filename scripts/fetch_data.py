"""Build regional data caches. Run as python -m scripts.fetch_data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import json
import os

import pandas as pd

from src.config import DATA, MODIS, REGION, STREAMS, VIIRS
from src.observations import add_file_info, checksum, deduplicate, district, normalize, read_fire_csv, tag_grid
from src.sources import ARCHIVE_CATALOG, COUNTRY_ROOT, POWER_QUERY, POWER_URL, area_requests, fetch, utc_now, write_atomic

COUNTRY_PREFIX = {MODIS: "modis", VIIRS: "viirs-snpp"}


def country_file(stream, year, catalog, boundary, bounds):
    filename = f"{COUNTRY_PREFIX[stream]}_{year}_India.csv"
    if filename not in catalog:
        raise ValueError(f"FIRMS has no published file named {filename}.")
    path = DATA / "raw" / filename
    url = f"{COUNTRY_ROOT}/{filename}"
    expected_size = catalog[filename]
    retrieved = None
    if path.is_file() and path.stat().st_size == expected_size:
        data = path.read_bytes()
    else:
        data = fetch(url, label=filename)
        if len(data) != expected_size:
            raise ValueError(f"{filename} does not match the published byte size.")
        write_atomic(path, data)
        retrieved = utc_now()
    if retrieved is None:
        retrieved = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").isoformat()

    rows = read_fire_csv(data)
    start, end = f"{year}-01-01", f"{year}-12-31"
    aliases = ["a", "aqua"] if stream == MODIS else ["n", "npp", "snpp", "suominpp"]
    satellite = rows.satellite.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    in_year = rows.acq_date.between(start, end)
    stream_rows = satellite.isin(aliases) & in_year
    if not stream_rows.any():
        raise ValueError(f"{filename} contains no matching {stream} records for {year}.")
    observed_days = set(pd.to_datetime(rows.loc[stream_rows, "acq_date"], format="%Y-%m-%d", errors="coerce").dropna())
    sp_rows = stream_rows & rows.version.str.strip().str.fullmatch(r"\d+(?:\.\d+)?")
    nonstandard_days = set(pd.to_datetime(
        rows.loc[stream_rows & ~sp_rows, "acq_date"], format="%Y-%m-%d", errors="coerce"
    ).dropna())
    west, south, east, north = bounds
    regional = pd.to_numeric(rows.longitude, errors="coerce").between(west, east) & pd.to_numeric(
        rows.latitude, errors="coerce"
    ).between(south, north)
    points, rejected = normalize(rows[regional & in_year], filename, boundary, expected_stream=stream)
    rejected["outside_bbox_or_invalid_coordinates"] = int((~regional).sum())
    rejected["outside_requested_year_within_bbox"] = int((regional & ~in_year).sum())
    info = add_file_info(
        data, filename, points, rejected, url, stream=stream, retrieved_utc=retrieved,
        extent="India archive clipped to Almora", requested_start=start, requested_end=end,
        district_bounds=list(bounds),
    )
    # A day with no records for this stream across India has unknown delivery.
    days = sorted(observed_days)
    intervals = []
    for day in days:
        label = day.date().isoformat()
        processing = "mixed or near-real-time" if day in nonstandard_days else "standard"
        if intervals and intervals[-1]["end"] == (day.date() - timedelta(days=1)).isoformat() and intervals[-1]["processing"] == processing:
            intervals[-1]["end"] = label
        else:
            intervals.append({"stream": stream, "start": label, "end": label, "processing": processing})
    print(f"{year} {stream}: {len(points)} district detections, {len(days)} delivery days", flush=True)
    return points, intervals, info


def api_file_stream(stream, start, end, geometry, key):
    west, south, east, north = geometry.bounds
    bounds = (round(west - 0.0001, 5), round(south - 0.0001, 5), round(east + 0.0001, 5), round(north + 0.0001, 5))
    for data, first, last, url in area_requests(key, stream, start, end, bounds):
        filename = f"{COUNTRY_PREFIX[stream]}_almora_{first}_{last}.csv"
        rows = read_fire_csv(data)
        points, rejects = normalize(rows, filename, geometry, expected_stream=stream)
        if len(points) and (
            points.processing.ne("standard").any()
            or not points.timestamp_utc.dt.date.between(first, last).all()
        ):
            raise ValueError("Unexpected processing tier or dates in FIRMS response.")
        write_atomic(DATA / "raw" / filename, data)
        interval = {"stream": stream, "start": first.isoformat(), "end": last.isoformat(), "processing": "standard"}
        yield points, [interval], add_file_info(
            data, filename, points, rejects, url, retrieved_utc=utc_now(), bounds=list(bounds), **interval
        )


def save_cache(results, stem):
    observations, intervals, files = zip(*results, strict=True)
    combined = pd.concat(observations, ignore_index=True)
    points = tag_grid(deduplicate(combined))
    parquet = points.to_parquet(index=False, compression="zstd")
    manifest = {
        "mode": "real", "region": REGION, "prepared_utc": utc_now(), "parquet_sha256": checksum(parquet),
        "boundary_sha256": checksum((DATA / "almora.geojson").read_bytes()),
        "files": list(files), "intervals": [entry for batch in intervals for entry in batch],
        "duplicates_removed": len(combined) - len(points),
    }
    write_atomic(DATA / f"{stem}.parquet", parquet)
    write_atomic(DATA / f"{stem}.json", json.dumps(manifest, indent=2).encode())
    print(f"Saved {len(points)} retained observations to data/{stem}.parquet.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    country = commands.add_parser("archive", help="Public India annual archives, clipped to Almora")
    country.add_argument("--modis-from", type=int, default=2003)
    country.add_argument("--viirs-from", type=int, default=2013)
    country.add_argument("--end-year", type=int, default=2025)
    country.add_argument("--bundled", action="store_true", help="Write distributable regional sample instead of local cache")
    api = commands.add_parser("firms", help="Regional standard-processing FIRMS API with a MAP_KEY")
    api.add_argument("--start", type=date.fromisoformat, required=True)
    api.add_argument("--end", type=date.fromisoformat, required=True)
    commands.add_parser("weather", help="Refresh representative NASA POWER daily weather")
    args = parser.parse_args()
    try:
        if args.command == "weather":
            payload = fetch(POWER_URL, label="NASA POWER", params=POWER_QUERY)
            from src.sources import weather_from_payload
            weather_from_payload(json.loads(payload))
            write_atomic(DATA / "power-almora.json", payload)
            return
        _, geometry = district()
        if args.command == "firms":
            key = os.environ.get("FIRMS_MAP_KEY", "").strip()
            results = [result for stream in STREAMS
                       for result in api_file_stream(stream, args.start, args.end, geometry, key)]
            save_cache(results, "processed/firms-api")
            return

        text = fetch(ARCHIVE_CATALOG, label="FIRMS public archive catalog").decode()
        catalog = {parts[0]: int(parts[1]) for line in text.splitlines()
                   if len(parts := line.split(",")) >= 2 and parts[1].isdigit()}
        tasks = [(stream, year) for stream, first in ((MODIS, args.modis_from), (VIIRS, args.viirs_from))
                 for year in range(first, args.end_year + 1)]
        if not tasks:
            raise ValueError("Select an archive year range containing at least one year.")
        with ThreadPoolExecutor(max_workers=4) as executor:
            jobs = [executor.submit(country_file, stream, year, catalog, geometry, geometry.bounds)
                    for stream, year in tasks]
            results = [job.result() for job in jobs]
        save_cache(results, "firms-demo" if args.bundled else "processed/firms-archives")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()

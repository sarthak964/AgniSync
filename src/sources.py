from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import json
import re

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from src.config import DATA, FIRMS_BASE, POWER_URL, SOURCES, WEATHER_COORDINATES, WEATHER_PARAMS

COUNTRY_ROOT = f"{FIRMS_BASE}/data/country"
ARCHIVE_CATALOG = f"{COUNTRY_ROOT}/yearly_summary_files.txt"
POWER_QUERY = {
    "parameters": ",".join(WEATHER_PARAMS), "community": "AG",
    "longitude": WEATHER_COORDINATES[0], "latitude": WEATHER_COORDINATES[1],
    "start": "20021201", "end": "20251231", "time-standard": "UTC", "format": "JSON",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fetch(url, *, label, params=None):
    retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    try:
        with requests.Session() as session:
            session.mount("https://", HTTPAdapter(max_retries=retries))
            response = session.get(url, params=params, timeout=(10, 45))
            response.raise_for_status()
            return response.content
    except requests.RequestException:
        # HTTP exceptions can contain the full URL, including a FIRMS credential.
        raise ValueError(f"{label} request failed. Check network access and product availability.") from None


def availability(key, product):
    content = fetch(f"{FIRMS_BASE}/api/data_availability/csv/{key}/{product}", label="FIRMS availability")
    try:
        rows = pd.read_csv(BytesIO(content), dtype=str)
        rows.columns = rows.columns.str.strip().str.lower()
        item = rows.loc[rows.data_id.eq(product)].iloc[0]
        return date.fromisoformat(item.min_date), date.fromisoformat(item.max_date)
    except (AttributeError, IndexError, ValueError, UnicodeError):
        raise ValueError("FIRMS could not confirm availability. Check the key and source.") from None


def area_requests(key, stream, start, end, bounds):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise ValueError("Set FIRMS_MAP_KEY in your local environment.")
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    product = SOURCES[stream]
    lower, upper = availability(key, product)
    if start < lower or end > upper:
        raise ValueError(f"{product} reports availability from {lower} through {upper}.")
    west, south, east, north = bounds
    area = ",".join(str(value) for value in (west, south, east, north))
    while start <= end:
        count = min(5, (end - start).days + 1)
        last_day = start + timedelta(days=count - 1)
        relative = f"{product}/{area}/{count}/{start.isoformat()}"
        data = fetch(f"{FIRMS_BASE}/api/area/csv/{key}/{relative}", label="FIRMS area")
        yield data, start, last_day, f"{FIRMS_BASE}/api/area/csv/[MAP_KEY]/{relative}"
        start = last_day + timedelta(days=1)


def write_atomic(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    temporary.replace(path)


def weather_from_payload(payload):
    header = payload["header"]
    if header["time_standard"] != "UTC":
        raise ValueError("NASA POWER daily weather must use UTC.")
    rows = pd.DataFrame(payload["properties"]["parameter"]).reindex(columns=WEATHER_PARAMS)
    rows.index = pd.to_datetime(rows.index, format="%Y%m%d")
    rows = rows.astype(float).replace(float(header["fill_value"]), float("nan"))
    return rows.sort_index()


def local_weather():
    path = DATA / "power-almora.json"
    if not path.is_file():
        return None, None
    payload = json.loads(path.read_bytes())
    return weather_from_payload(payload), payload

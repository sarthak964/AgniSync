from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REGION = "Almora district, Uttarakhand"
MODIS = "Aqua MODIS"
VIIRS = "Suomi NPP VIIRS"
STREAMS = (MODIS, VIIRS)
SOURCES = {MODIS: "MODIS_SP", VIIRS: "VIIRS_SNPP_SP"}
GRID_CRS = "EPSG:32644"
GRID_METRES = 1000
TRAIN_END = "2021-12"
CUTOVER = "2022-01"
TEST_END = "2025-12"
BASELINE_MIN = 5
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov"
FIRMS_ARCHIVE = f"{FIRMS_BASE}/download/"
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
WEATHER_COORDINATES = (79.60, 29.65)
WEATHER_PARAMS = ("PRECTOTCORR", "T2M", "RH2M", "WS10M")
QUALITY = "MODIS integer confidence ≥ 30 and VIIRS nominal/high"
SENSOR_COLORS = {MODIS: "#a34627", VIIRS: "#196964"}


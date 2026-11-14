# AgniSync — A Satellite Fire Calendar for Almora

A Streamlit dashboard by Team Antariksh Guru for the NASA Space Apps Challenge on harmonizing MODIS and VIIRS hotspots. It compares Aqua MODIS and Suomi NPP VIIRS hotspot activity on a common grid, reconstructs a monthly activity calendar for Almora district, Uttarakhand, and puts unusual months beside NASA POWER weather evidence.

## Run on Windows

Open PowerShell in the project folder. If you already have the project environment, use the final command.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

## Run on Linux or macOS

From the project folder, with Python 3.12 installed:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Open [the local dashboard](http://127.0.0.1:8501). The dependency file contains versions installed and exercised on Windows. Shapely and pyproj handle geometry and projection directly because Windows Application Control blocked the GeoPandas I/O dependency on this machine. PyArrow 22.0.0 passed the same environment's import and Parquet checks.

## Three-minute demo

1. Start on **NASA FIRMS archive**, with **April 2024** selected. Point out the district boundary and the different raw counts from the two satellite streams.
2. Open **Burning calendar**. One grid cell active on three UTC days contributes three active cell-days. Use the month selector to show that the map and details follow the selection.
3. Open **Investigate month**. April 2024 had **63.2** adjusted active cell-days against an April median of **8.0** and a 90th-percentile threshold of **48.2** from 20 earlier comparable Aprils. Preceding rainfall was higher than the historical median for those windows, while mean relative humidity was lower. The conditions provide context, and the ignition cause remains unconfirmed.
4. Open **Sensor comparison**. On 30 held-out monthly pairs the mean absolute difference from Aqua MODIS fell from **71.2** to **2.5** active cell-days. The coefficient is local to this region, period, filter and grid.
5. Open **Results & sources** and download the selected month's ZIP. It includes the retained point records, monthly activity by stream, the reference-scale value, weather and anomaly results, the explanation and provenance.

If WebGL or a basemap is unavailable, choose **Coordinate view**. The district outline and points in that view use local data. **Synthetic demonstration** is a separate, fixed-seed mode for showing software behaviour.

## Data and refresh

The files needed for the key-free demo are included. Keep these files in `data/`:

| File | Contents |
| --- | --- |
| `almora.geojson` and `boundary-source.json` | Almora ADM2 geometry, attribution, license and checksum |
| `firms-demo.parquet` and `firms-demo.json` | Retained district observations, input checksums, rejection counts and delivery history |
| `power-almora.json` | UTC daily weather and response metadata from NASA POWER |

**Import FIRMS CSVs** accepts multiple NASA FIRMS point files. Download the Aqua MODIS and Suomi NPP 375 m VIIRS products as CSV, preferably using standard processing. To try a small import, use April 2024 and the Almora bounding rectangle (west **79.0387**, south **29.4218**, east **80.0805**, north **29.9760**). The app clips points to the district polygon. CSV uploads have no independent date-delivery record. Their observed counts are displayed with unknown delivery and are excluded from calibration and anomaly thresholds. [NASA FIRMS Archive Download](https://firms.modaps.eosdis.nasa.gov/download/)

To recreate the district cache, the archive command retrieves India-only annual files and clips them locally. A full rebuild downloads about 700 MB before clipping. Use `archive --modis-from 2024 --viirs-from 2024 --end-year 2024` for a smaller slice. The archive and API commands write separate local caches under `data/processed/`. Raw downloads go to `data/raw/`. The `--bundled` option writes the demo cache. The `weather` command refreshes the weather JSON.

```powershell
.\.venv\Scripts\python.exe -m scripts.fetch_data archive
.\.venv\Scripts\python.exe -m scripts.fetch_data weather
```

The optional regional area API needs a [FIRMS MAP_KEY](https://firms.modaps.eosdis.nasa.gov/api/area/). Set the environment variable locally with the value from NASA. The script checks available dates, requests at most five days per call and redacts the key from messages and provenance.

```powershell
$env:FIRMS_MAP_KEY = '<your key>'
.\.venv\Scripts\python.exe -m scripts.fetch_data firms --start 2024-04-01 --end 2024-04-30
Remove-Item Env:FIRMS_MAP_KEY
```

```bash
./.venv/bin/python -m scripts.fetch_data archive
./.venv/bin/python -m scripts.fetch_data weather
FIRMS_MAP_KEY='<your key>' ./.venv/bin/python -m scripts.fetch_data firms --start 2024-04-01 --end 2024-04-30
```

## Verification and scope

Run `.\.venv\Scripts\python.exe -m pytest -q` on Windows or `./.venv/bin/python -m pytest -q` on Linux/macOS. See [verification](docs/VERIFICATION.md), [methodology](docs/METHODOLOGY.md), and the [learning guide](docs/LEARNING_GUIDE.md).

- The prototype ships with 19,228 real detections, including Aqua MODIS from 2003–2025 and Suomi NPP VIIRS from 2013–2025. Individual months can be partial or missing.
- The live key-authenticated FIRMS route needs an end-to-end check with a user-supplied key. The public archive path and the CSV importer use the same normalization and grid.
- The analysis reports district hotspot activity. Detection opportunity, clear-sky coverage, ignition and burned area require other evidence. The weather series represents one broad grid cell.
- For deployment, package the app, source, pinned dependencies and bundled caches for a Python 3.12 Streamlit host. Retain the boundary attribution and license and configure any credentials through host secrets. The current prototype runs locally.

# AgniSync — A Satellite Fire Calendar for Almora

A Flask dashboard by Team Antariksh Guru for the NASA Space Apps Challenge on harmonizing MODIS and VIIRS hotspots. It compares Aqua MODIS and Suomi NPP VIIRS hotspot activity on a common grid, reconstructs a monthly activity calendar for Almora district, Uttarakhand, and puts unusual months beside NASA POWER weather evidence.

## Run on Windows

Open PowerShell in the project folder. If you already have the project environment, use the final command.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m waitress --listen=127.0.0.1:8504 dashboard:app
```

## Run on Linux or macOS

From the project folder, with Python 3.12 installed:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m waitress --listen=127.0.0.1:8504 dashboard:app
```

Open [the Flask dashboard](http://127.0.0.1:8504). The Streamlit dashboard remains available for local FIRMS CSV imports and local cache exploration. Run it with `python -m streamlit run app.py --server.address 127.0.0.1` using the project environment.

## Three-minute demo

1. Start on **NASA FIRMS archive**, with **April 2024** selected. Point out the district boundary and the different raw counts from the two satellite streams.
2. Click the **April 25** bar beside the map. The map shows **6** cells with MODIS detections only, **92** with VIIRS detections only and **2** with both. Use the filter chips to isolate a group.
3. In **Investigate**, April 2024 shows **63.2** adjusted active cell-days against a historical cutoff of **48.2**. Only **VIIRS** crosses its own cutoff when both sensors are compared against the same ten earlier Aprils. Click **April 2021** in the **Calendar** to see a month both satellites flag at the 90th percentile.
4. In **Compare**, the mean absolute difference from Aqua MODIS fell from **71.2** to **2.5** active cell-days across 30 held-out months. The coefficient is local to this region, period, filter and grid.
5. Use **Download evidence** to export the selected month's observations, monthly activity, anomaly results, weather, explanation and provenance.

The district outline and grid markers use local data. **Synthetic demonstration** is a separately labeled, fixed-seed mode.

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

## Deploy to Google Cloud Run

From the project directory, use a Google Cloud project with billing enabled and sign in to the Google Cloud CLI. Substitute your project ID below. Cloud Run uses the included Dockerfile to build and serve the dashboard. The bundled Almora demo works without a FIRMS API key.

```sh
gcloud run deploy agnisync --source . --project YOUR_PROJECT_ID --region us-central1 --allow-unauthenticated --min-instances 0 --max-instances 1 --memory 1Gi
```

Open the resulting service URL in a private browser window to check public access. Try clicking a daily activity bar and choosing a detection group on the map. Use **Download evidence** to check that the deployment includes the data files. Cloud Run compute, build, image storage and data transfer each have their own pricing. [Google Cloud Run deployment](https://docs.cloud.google.com/run/docs/deploying-source-code) · [Cloud Run pricing](https://cloud.google.com/run/pricing)

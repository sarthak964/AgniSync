# Prototype verification

Verified on Windows with Python 3.12. The code can be started in the project directory using the README commands.

| Command | Result |
| --- | --- |
| `py -3.12 -m venv .venv` | Created the project virtual environment. |
| `.\.venv\Scripts\python.exe -m pip check` | No broken requirements. PyArrow 22.0.0 passed Windows import and Parquet checks. |
| `.\.venv\Scripts\python.exe -m scripts.fetch_data archive --modis-from 2024 --viirs-from 2024 --end-year 2024 --bundled` | Imported 2,732 real Almora detections from 2024. |
| `.\.venv\Scripts\python.exe -m scripts.fetch_data archive --bundled` | Verified file sizes against the public NASA catalog and cached 19,228 retained detections from 36 India annual archives. |
| `.\.venv\Scripts\python.exe -m pytest -q` | 7 tests passed. Streamlit emitted a pandas deprecation warning about timezone access. |
| `.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true` | Started the local dashboard. Browser checks covered the map, calendar, April investigation, sensor comparison and results. |
| `.\.venv\Scripts\python.exe -m scripts.fetch_data firms --start 2024-04-01 --end 2024-04-30` | With no key configured, the command exited with the expected missing-key message. The authenticated call still needs a valid MAP_KEY to verify. |

The browser downloaded `almora-2024-04-real.zip`. ZIP integrity passed, the observations file contained 1,048 records from April 2024 only, and the month summary identified adjusted VIIRS. The archive also contained the anomaly, four weather summaries, explanation and provenance. Streamlit's automated test changed the selected month in synthetic mode and exercised the coordinate map. Individual browser tooltips and macOS/Linux startup were not independently checked.

In Chrome, clicking April 8 on the daily timeline changed the selected date from April 25 and updated the counts. Turning off **VIIRS only** removed that group from the map.

## Real archive and scientific scope

- Aqua MODIS retained 1,828 detections between January 2003 and December 2025. Suomi NPP VIIRS retained 17,400 between January 2013 and December 2025.
- The conservative country-archive proxy found 187 complete and 89 partial Aqua months. For VIIRS it found 147 complete and nine partial months in 2013–2025. VIIRS is unavailable in this cache before 2013.
- Calibration used 73 fit months and 30 held-out months. Overall MAE was 71.233 before adjustment and 2.483 after, while mean bias changed from +71.100 to −1.076 active cell-days. Among the 28 active held-out months, MAE fell from 76.321 to 2.660. June–August had one held-out pair and carries little evidence on its own.
- April 2024 held 63.2 adjusted cell-days, compared with a median of 8.0 and a 90th-percentile threshold of 48.2. NASA POWER showed 50.8 mm of preceding rainfall compared with a median of 16.17 mm over the same baseline years.
- These checks evaluate agreement with one satellite stream and verify software behaviour. Confirming actual fires, burned area or clear-sky coverage would require additional data.

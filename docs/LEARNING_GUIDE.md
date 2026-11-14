# Explain the prototype in an interview

The same district can show very different raw counts across sensors because pixel size, sensitivity and observation times differ. Our map preserves those counts. The calendar uses one activity definition and, when supported by overlap, a local adjustment to a common reference scale.

| Stage | Code to read | What goes in and comes out |
| --- | --- | --- |
| Data sources | `scripts/fetch_data.py`, `src/sources.py`, `src/datasets.py` | NASA FIRMS CSVs and a district polygon become a compact Parquet file and a provenance manifest. NASA POWER daily JSON is cached separately. |
| Cleaning and grid | `src/observations.py` | A CSV time of `15` becomes `00:15 UTC`. After clipping to Almora and projecting, points on the same cell and day count once per sensor. |
| Monthly analysis | `src/analysis.py` | A sensor with five occupied cells on Monday and three on Tuesday contributes eight active cell-days. Missing and incomplete deliveries carry explicit states. |
| Sensor adjustment | `src/analysis.py` | Paired full months fit a scaling coefficient. Later months test agreement. The calendar selects one source per month using a fixed cutover. |
| Investigation | `src/evidence.py`, `src/analysis.py` | A selected April is compared to earlier Aprils. The explanation cites the calculated threshold and weather evidence. |
| Interface and export | `app.py`, `src/visuals.py`, `src/exports.py` | One sidebar selection controls the map, cards, explanation and downloaded ZIP. The date range slider narrows charts. |

**Why use a projected grid?** A degree of longitude covers a different distance depending on latitude. A projection converts coordinates to local metres so a 1,000 m cell can be defined consistently.

**What does harmonization mean here?** We fit a factor that expresses VIIRS cell-days on Aqua MODIS's scale. Agreement with MODIS is the evaluation target for this experiment. Validating against actual fire occurrence would require independent ground or higher-resolution evidence.

**Why split by time?** Training on earlier months and evaluating on later months checks whether the relationship holds later in the record. It also keeps the 2024 case outside model fitting.

**What does an anomaly mean?** April 2024 exceeded a threshold built from earlier comparable Aprils. Comparing April with other Aprils accounts for the usual seasonal pattern. A percentile threshold describes historical activity.

**Can you say rain caused the April result?** The evidence shows 50.8 mm in the prior 30 days versus a 16.17 mm historical median, and lower mean relative humidity during the month. Those results describe conditions at a representative weather grid cell. Ignition remains unconfirmed.

# Method and sources

## Observations

The release uses standard-processing country archive downloads from NASA FIRMS where delivery can be established. The source list in `data/firms-demo.json` records filenames, URLs, available dates of retained rows, checksums, geographic extent and rejection counts. The public MODIS India files contain multiple satellites, so the importer selects Aqua. The VIIRS input is the 375 m Suomi NPP product. [FIRMS country archive](https://firms.modaps.eosdis.nasa.gov/country/)

The parser validates coordinates, UTC date/time and version; retains MODIS confidence 30–100 and VIIRS nominal/high; and preserves the original confidence and processing information. Optional fire radiative power is in megawatts. The district clip includes points on the polygon edge. Identical UTC timestamp, position and stream count once, with standard processing preferred over a near-real-time duplicate. Subtle geolocation shifts between products can prevent exact matching, so months with mixed processing are excluded from calibration. [MODIS attributes](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_MODIS_Firehotspots.html), [VIIRS attributes](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html)

The boundary is the simplified 2021 Almora ADM2 feature from geoBoundaries India, pinned to release commit `9469f09`. It is sourced from Pathways Data Pvt. Ltd. and lgdirectory.gov.in as recorded by geoBoundaries. The source record specifies ODbL 1.0, and the extracted geometry retains that attribution and license. [Boundary metadata](https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/), [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)

## Activity and completeness

Coordinates start in WGS 84 longitude/latitude and are projected to UTM 44N (EPSG:32644), which expresses local distances in metres. Divide easting and northing by 1,000 and round down to give stable cell IDs. Each UTC day, count each occupied cell once per satellite. Sum over the month to obtain active cell-days. Their units are cell-days. The grid groups reported hotspots and provides no measurement of burned area.

For the India archive, a day with any rows for a stream anywhere in India is evidence that the country's file contains that stream's records for the day. This is a conservative delivery proxy. Days without country records lack delivery evidence. For API visits, a valid CSV response establishes retrieval for the requested dates. A complete month with no retained points has zero reported activity. An incomplete or unknown month can show a partial count when a retained district point exists. With no evidence to support a count, the value is missing. Complete file delivery does not establish pass-level or cloud-free coverage. Uploaded CSVs preserve unknown delivery.

## Calibration and calendar

Fit `MODIS = coefficient × VIIRS` with a non-negative coefficient and a zero intercept. Train on complete standard-processing pairs from January 2013 through December 2021. Evaluate on the same kind of pairs from January 2022 through December 2025. Require 24 fit months, eight fit months with positive activity in both streams, 12 test months, and six test months active in either stream. Use the adjustment if overall held-out MAE drops at least 5% and active-month MAE does not increase. Report MAE and mean signed bias across all, active and seasonal groups. Interpret small groups cautiously. The observed coefficient was approximately 0.08561, with 73 fit pairs and 30 held-out pairs. The fit range was 0–1,022 VIIRS active cell-days.

Use observed Aqua MODIS through December 2021. From January 2022, use adjusted VIIRS when the candidate meets the decision rule, the VIIRS month is complete standard processing, and its activity is in the fit range. Otherwise use the available MODIS value and label it as fallback. If neither supplies a usable reference-scale value, leave it missing. Partial or nonstandard observations cannot enter the anomaly baseline. This retrospective study uses the held-out period to decide whether to show adjusted results, so the calendar cannot serve as an as-of-date warning evaluation.

## Investigation and weather

For a selected month, use earlier comparable years of the same calendar month. With at least five prior values, report their median and a configurable upper percentile (90th by default). Flag activity strictly above that threshold. This is a descriptive historical comparison. Avoid relative percentage changes when the historical baseline is zero.

NASA POWER daily MERRA‑2 data are requested at 29.65°N, 79.60°E in UTC for December 2002 through December 2025. Weather represents one broad grid cell, approximately 0.5° latitude by 0.625° longitude. The prototype sums corrected rainfall in the 30 days before the month and averages 2 m temperature, 2 m relative humidity and 10 m wind across the calendar month. It excludes any parameter/window with an absent or fill-valued day. Baselines reuse the historical activity years where each weather window is available. The explanation is generated from those values with deterministic text. [NASA POWER daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/), [MERRA‑2 meteorology](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/)

ISRO's Indian Institute of Remote Sensing supplies independent context about Uttarakhand's 2024 fire season, including Almora. The case did not set the project's anomaly result. [IIRS 2024 observations](https://www.iirs.gov.in/iirs_slide_page?s=121)

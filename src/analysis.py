import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from src.config import BASELINE_MIN, BOTH_SENSORS, CUTOVER, MODIS, STREAMS, TEST_END, TRAIN_END, VIIRS

FULL = "Complete delivery"
PARTIAL = "Partial delivery"
UNKNOWN = "Delivery unknown"
MISSING = "Missing"


def monthly_activity(observations, intervals):
    dates = list(observations.day_utc)
    for interval in intervals:
        dates.extend((interval["start"], interval["end"]))
    if not dates:
        return pd.DataFrame(columns=["month", "stream", "active_cell_days", "raw_hotspots", "delivery", "standard_delivery"])
    months = pd.period_range(min(dates), max(dates), freq="M")
    unique = observations.drop_duplicates(["stream", "day_utc", "grid_x", "grid_y"])
    cells = unique.groupby(["stream", "month"]).size().to_dict()
    counts = observations.groupby(["stream", "month"]).size().to_dict()
    any_nonstandard = observations.loc[
        observations.processing.ne("standard"), ["stream", "month"]
    ].value_counts().to_dict()
    delivered = {stream: set() for stream in STREAMS}
    standard = {stream: set() for stream in STREAMS}
    for interval in intervals:
        days = set(pd.date_range(interval["start"], interval["end"], freq="D"))
        delivered[interval["stream"]].update(days)
        if interval["processing"] == "standard":
            standard[interval["stream"]].update(days)

    records = []
    for month in months:
        days = set(pd.date_range(month.start_time, month.end_time.normalize(), freq="D"))
        for stream in STREAMS:
            key = (stream, str(month))
            n_raw = counts.get(key, 0)
            if days <= delivered[stream]:
                status = FULL
            elif days & delivered[stream]:
                status = PARTIAL
            else:
                status = UNKNOWN if n_raw else MISSING
            records.append({
                "month": str(month), "stream": stream, "delivery": status,
                "raw_hotspots": n_raw if n_raw or status == FULL else None,
                "active_cell_days": cells.get(key, 0) if n_raw or status == FULL else None,
                "standard_delivery": days <= standard[stream] and key not in any_nonstandard,
            })
    return pd.DataFrame.from_records(records)


def daily_hotspot_cells(observations):
    cell_day = ["day_utc", "grid_x", "grid_y"]
    detections = observations.groupby([*cell_day, "stream"]).size().unstack(fill_value=0)
    present = detections.reindex(columns=list(STREAMS), fill_value=0).gt(0)
    detected_by = np.select(
        [present.all(axis=1), present[MODIS]], [BOTH_SENSORS, "MODIS only"], default="VIIRS only",
    )
    return detections.index.to_frame(index=False).assign(detected_by=detected_by)


def _metrics(data, coefficient):
    raw = data[VIIRS] - data[MODIS]
    adjusted = data[VIIRS] * coefficient - data[MODIS]
    return {
        "months": len(data), "raw_mae": round(float(raw.abs().mean()), 3),
        "adjusted_mae": round(float(adjusted.abs().mean()), 3),
        "raw_bias": round(float(raw.mean()), 3), "adjusted_bias": round(float(adjusted.mean()), 3),
    }


def calibrate(monthly):
    paired = monthly[monthly.standard_delivery.astype(bool)].pivot(
        index="month", columns="stream", values="active_cell_days"
    ).reindex(columns=list(STREAMS)).dropna()
    train = paired.loc[(paired.index >= "2013-01") & (paired.index <= TRAIN_END)]
    test = paired.loc[(paired.index >= CUTOVER) & (paired.index <= TEST_END)]
    active = test[(test[MODIS] > 0) | (test[VIIRS] > 0)]
    report = {
        "method": "non-negative origin fit v1",
        "status": "Insufficient data for calibration", "use_adjustment": False,
        "coefficient": None, "fit_months": len(train), "evaluation_months": len(test),
        "fit_period": f"2013-01 to {TRAIN_END}", "evaluation_period": f"{CUTOVER} to {TEST_END}",
        "criteria": "≥24 fit months; ≥8 fit months active in both streams; ≥12 test months; ≥6 active test months. Use adjustment if held-out MAE improves by ≥5% overall and does not increase in active months.",
    }
    if (len(train) < 24 or (train.gt(0).all(axis=1)).sum() < 8
            or len(test) < 12 or len(active) < 6):
        return report

    model = LinearRegression(fit_intercept=False, positive=True).fit(train[[VIIRS]], train[MODIS])
    coefficient = float(model.coef_[0])
    all_metrics = _metrics(test, coefficient)
    active_metrics = _metrics(active, coefficient)
    raw_error = (test[VIIRS] - test[MODIS]).abs().mean()
    adjusted_error = (test[VIIRS] * coefficient - test[MODIS]).abs().mean()
    active_raw = (active[VIIRS] - active[MODIS]).abs().mean()
    active_adjusted = (active[VIIRS] * coefficient - active[MODIS]).abs().mean()
    useful = bool(coefficient > 0 and raw_error > 0 and adjusted_error <= raw_error * 0.95
                  and active_adjusted <= active_raw)
    seasons = test.groupby(pd.Index(test.index.str[5:].astype(int) % 12 // 3, name="season"))
    seasonal = {("Dec–Feb", "Mar–May", "Jun–Aug", "Sep–Nov")[key]: _metrics(group, coefficient)
                for key, group in seasons}
    lower, upper = int(train[VIIRS].min()), int(train[VIIRS].max())
    return {
        **report, "status": "Eligible for prototype use" if useful else "Experimental adjustment did not meet the acceptance criteria",
        "use_adjustment": useful, "coefficient": coefficient, "held_out_all": all_metrics,
        "held_out_active": active_metrics, "held_out_seasonal": seasonal,
        "viirs_training_range": [lower, upper],
        "test_months_outside_training_range": int((~test[VIIRS].between(lower, upper)).sum()),
        "reference_scale": MODIS,
    }


def unified_activity(monthly, report):
    modis = monthly[monthly.stream.eq(MODIS)].set_index("month")
    viirs = monthly[monthly.stream.eq(VIIRS)].set_index("month")
    calendar = pd.DataFrame(index=modis.index)
    calendar["modis"] = modis.active_cell_days
    calendar["viirs"] = viirs.active_cell_days
    calendar["modis_delivery"] = modis.delivery
    calendar["viirs_delivery"] = viirs.delivery
    calendar["viirs_adjusted"] = np.nan
    calendar["outside_training_range"] = False
    coefficient = report["coefficient"]
    if coefficient is not None:
        lower, upper = report["viirs_training_range"]
        calendar["viirs_adjusted"] = calendar.viirs * coefficient
        calendar["outside_training_range"] = calendar.viirs.notna() & ~calendar.viirs.between(lower, upper)
    after = calendar.index >= CUTOVER
    use_viirs = (
        after & report["use_adjustment"] & viirs.standard_delivery.astype(bool)
        & ~calendar.outside_training_range & calendar.viirs.notna()
    )
    calendar["activity"] = calendar.modis.where(~use_viirs, calendar.viirs_adjusted)
    calendar["source"] = np.select(
        [use_viirs, calendar.modis.notna() & after, calendar.modis.notna()],
        ["Adjusted VIIRS", "MODIS fallback", "Observed MODIS"], default="Missing",
    )
    calendar["comparable"] = use_viirs | (modis.standard_delivery.astype(bool) & modis.active_cell_days.notna())
    calendar["delivery"] = modis.delivery.where(~use_viirs, viirs.delivery)
    calendar.loc[calendar.activity.isna(), "delivery"] = MISSING
    return calendar.reset_index()


def seasonal_comparison(calendar, selected, percentile=90):
    target = calendar.set_index("month").loc[selected]
    earlier = calendar[
        calendar.month.lt(selected) & calendar.month.str[5:].eq(selected[5:]) & calendar.comparable
    ].dropna(subset=["activity"])
    result = {
        "month": selected, "source": target.source, "activity": None if pd.isna(target.activity) else float(target.activity),
        "delivery": target.delivery, "baseline_years": earlier.month.str[:4].tolist(),
        "baseline_count": len(earlier), "median": None, "threshold": None, "percentile": percentile,
        "status": "Comparable", "unusually_high": None,
    }
    if not target.comparable:
        result["status"] = "Selected month lacks complete, standard-processing evidence."
    elif len(earlier) < BASELINE_MIN:
        result["status"] = "Insufficient same-month history."
    else:
        result["median"] = float(earlier.activity.median())
        result["threshold"] = float(earlier.activity.quantile(percentile / 100))
        result["unusually_high"] = bool(target.activity > result["threshold"])
    return result, earlier


def sensor_anomaly_agreement(monthly, selected, percentile=90):
    eligible = monthly.standard_delivery & monthly.active_cell_days.notna()
    delivered_streams = monthly.loc[eligible].groupby("month").stream.nunique()
    paired_months = delivered_streams[delivered_streams.eq(len(STREAMS))].index
    observed = monthly.assign(
        activity=monthly.active_cell_days, source=monthly.stream,
        comparable=monthly.month.isin(paired_months),
    )
    return {
        stream: seasonal_comparison(observed[observed.stream.eq(stream)], selected, percentile)[0]
        for stream in STREAMS
    }

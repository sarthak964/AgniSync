from calendar import monthrange

import numpy as np
import pandas as pd

WEATHER_METRICS = {
    "PRECTOTCORR": ("Rainfall in the 30 days before the month", "mm"),
    "T2M": ("Mean temperature in the month", "°C"),
    "RH2M": ("Mean relative humidity in the month", "%"),
    "WS10M": ("Mean 10 m wind speed in the month", "m/s"),
}


def weather_window(weather, month, parameter):
    year, number = (int(part) for part in month.split("-"))
    start = pd.Timestamp(year, number, 1)
    rainfall = parameter == "PRECTOTCORR"
    if rainfall:
        days = pd.date_range(start - pd.Timedelta(days=30), periods=30)
    else:
        days = pd.date_range(start, periods=monthrange(year, number)[1])
    values = weather[parameter].reindex(days)
    if not np.isfinite(values).all():
        return None
    if rainfall and values.lt(0).any():
        return None
    return float(values.sum() if rainfall else values.mean())


def weather_evidence(weather, selected, years):
    if weather is None:
        return []
    evidence = []
    for parameter, (label, unit) in WEATHER_METRICS.items():
        value = weather_window(weather, selected, parameter)
        historical = {year: weather_window(weather, f"{year}-{selected[5:]}", parameter) for year in years}
        available = {year: item for year, item in historical.items() if item is not None}
        evidence.append({
            "parameter": parameter, "metric": label, "unit": unit,
            "selected": round(value, 2) if value is not None else None,
            "historical_median": round(float(np.median(list(available.values()))), 2) if available else None,
            "historical_years": list(available), "historical_count": len(available),
        })
    return evidence


def explain(anomaly, weather):
    activity = anomaly["activity"]
    if activity is None:
        observations = f"{anomaly['month']} has no reference-scale activity value in this dataset."
    else:
        source = anomaly["source"]
        delivery = anomaly["delivery"]
        observations = f"{anomaly['month']} had {activity:,.1f} active cell-days on the MODIS reference scale ({source}, {delivery.lower()})."
    if anomaly["threshold"] is None:
        history = anomaly["status"]
    else:
        relation = "above" if anomaly["unusually_high"] else "at or below"
        history = (f"Activity was {relation} the {anomaly['percentile']}th-percentile threshold "
                   f"of {anomaly['threshold']:,.1f} across {anomaly['baseline_count']} earlier years of the same month. "
                   f"The historical median was {anomaly['median']:,.1f}.")
    rainfall = next((item for item in weather if item["parameter"] == "PRECTOTCORR"), None)
    if rainfall and rainfall["selected"] is not None and rainfall["historical_count"] >= 5:
        if rainfall["selected"] < rainfall["historical_median"]:
            context = "Lower preceding rainfall may have contributed to drier conditions."
        else:
            context = "Preceding rainfall was at or above the historical median for the available comparison windows."
    elif weather:
        context = "Weather is shown where available. A rainfall comparison requires five complete historical windows."
    else:
        context = "Weather evidence is unavailable for this data mode."
    humidity = next((item for item in weather if item["parameter"] == "RH2M"), None)
    if (humidity and humidity["selected"] is not None and humidity["historical_count"] >= 5
            and humidity["selected"] < humidity["historical_median"]):
        context += " Mean relative humidity was below its historical median, consistent with drier air."
    return [observations, history, context,
            "Satellite passes and clouds affect detections. The ignition cause is unconfirmed."]

import calendar

import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
from pyproj import Transformer

from src.analysis import FULL
from src.config import BOTH_SENSORS, DAILY_CELL_COLORS, GRID_CRS, GRID_METRES, MODIS, SENSOR_COLORS, STREAMS, VIIRS

SOURCE_COLORS = {"Observed MODIS": "#a34627", "MODIS fallback": "#a34627", "Adjusted VIIRS": "#196964"}
CHART_FONT = "Source Sans 3, Arial, sans-serif"


def chart_layout(fig, **options):
    fig.update_layout(
        template="plotly_white", font=dict(family=CHART_FONT, color="#302c25", size=13),
        margin=dict(l=16, r=16, t=18, b=16), paper_bgcolor="rgba(0,0,0,0)", **options,
    )
    return fig


def map_view(observations, boundary, bounds):
    positions = observations[["longitude", "latitude", "stream", "confidence_category", "timestamp_utc"]].copy()
    positions["acquired"] = positions.pop("timestamp_utc").dt.strftime("%Y-%m-%d %H:%M UTC")
    positions["color"] = positions.stream.map({MODIS: "169,70,39", VIIRS: "25,105,100"}).map(
        lambda value: [int(channel) for channel in value.split(",")]
    )
    layers = [pdk.Layer(
        "GeoJsonLayer", boundary, stroked=True, filled=True, pickable=False, line_width_min_pixels=2,
        get_line_color=[94, 86, 66], get_fill_color=[232, 224, 204, 155],
    )]
    if not positions.empty:
        layers.append(pdk.Layer(
            "ScatterplotLayer", positions, get_position=["longitude", "latitude"], get_fill_color="color",
            get_radius=230, radius_min_pixels=3, radius_max_pixels=7, pickable=True, opacity=0.75,
        ))
    west, south, east, north = bounds
    return pdk.Deck(
        layers=layers, map_provider=None, map_style=None,
        initial_view_state=pdk.ViewState(longitude=(west + east) / 2, latitude=(south + north) / 2, zoom=8.15),
        tooltip={"text": "{stream}\n{acquired}\n{confidence_category} confidence"},
    )


def _district_outline(boundary, bounds):
    fig = go.Figure()
    geom = boundary["features"][0]["geometry"]
    polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for polygon in polygons:
        for ring in polygon:
            fig.add_trace(go.Scatter(
                x=[point[0] for point in ring], y=[point[1] for point in ring], mode="lines",
                line=dict(color="#70644b", width=2), hoverinfo="skip", showlegend=False,
            ))
    west, south, east, north = bounds
    fig.update_xaxes(title="Longitude", range=[west - 0.03, east + 0.03])
    fig.update_yaxes(title="Latitude", range=[south - 0.03, north + 0.03], scaleanchor="x", scaleratio=1.14)
    return fig


def coordinate_map(observations, boundary, bounds):
    fig = _district_outline(boundary, bounds)
    for stream in STREAMS:
        points = observations[observations.stream.eq(stream)]
        fig.add_trace(go.Scatter(
            x=points.longitude, y=points.latitude, mode="markers", name=stream,
            marker=dict(color=SENSOR_COLORS[stream], size=6, opacity=0.72),
            text=points.timestamp_utc.dt.strftime("%Y-%m-%d %H:%M UTC"), hovertemplate="%{text}<extra>%{fullData.name}</extra>",
        ))
    return chart_layout(fig, height=420, legend=dict(orientation="h"))


def daily_activity_chart(counts):
    fig = go.Figure()
    for label, color in DAILY_CELL_COLORS.items():
        fig.add_bar(
            x=counts.index, y=counts[label], name=label, marker_color=color,
            customdata=counts.index.tolist(),
            selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
            hovertemplate="%{x|%d %b} UTC<br>%{y} cells<extra>%{fullData.name}</extra>",
        )
    fig.update_xaxes(type="date", tickformat="%d %b")
    fig.update_yaxes(rangemode="tozero")
    return chart_layout(fig, height=235, barmode="stack", showlegend=False, yaxis_title="Grid cells",
                        clickmode="event+select")


def daily_cell_map(cells, boundary, bounds):
    fig = _district_outline(boundary, bounds)
    inverse = Transformer.from_crs(GRID_CRS, "EPSG:4326", always_xy=True)
    for label, color in DAILY_CELL_COLORS.items():
        group = cells[cells.detected_by.eq(label)]
        if group.empty:
            continue
        x = (group.grid_x + 0.5) * GRID_METRES
        y = (group.grid_y + 0.5) * GRID_METRES
        lon, lat = inverse.transform(x.tolist(), y.tolist())
        fig.add_scatter(
            x=lon, y=lat, mode="markers", name=label,
            marker=dict(
                color=color, size=10 if label == BOTH_SENSORS else 7,
                symbol="diamond" if label == BOTH_SENSORS else "square",
                line=dict(color="white", width=0.8),
            ),
            customdata=group[["grid_x", "grid_y"]],
            hovertemplate="Grid cell %{customdata[0]}, %{customdata[1]}<extra>%{fullData.name}</extra>",
        )
    return chart_layout(fig, height=405, legend=dict(orientation="h", y=-0.22))


def activity_calendar(history):
    data = history.assign(year=history.month.str[:4], month_number=history.month.str[5:].astype(int))
    values = data.pivot(index="year", columns="month_number", values="activity").reindex(columns=range(1, 13))
    source = data.pivot(index="year", columns="month_number", values="source").reindex_like(values)
    delivery = data.pivot(index="year", columns="month_number", values="delivery").reindex_like(values)
    labels = [["—" if pd.isna(value) else f"{value:.0f}{'' if state == FULL else '*'}"
               for value, state in zip(row, states)] for row, states in zip(values.to_numpy(), delivery.to_numpy())]
    details = [[f"{origin} · {state}" if pd.notna(origin) else "Outside the selected years"
                for origin, state in zip(row, states)] for row, states in zip(source.to_numpy(), delivery.to_numpy())]
    fig = go.Figure(go.Heatmap(
        x=list(calendar.month_abbr)[1:], y=values.index, z=values.to_numpy(),
        zmin=0, colorscale=[[0, "#fcf2df"], [0.45, "#e8af71"], [1, "#8e321e"]],
        text=labels, texttemplate="%{text}", customdata=details, hoverongaps=False,
        hovertemplate="%{x} %{y}<br>%{z:.1f} active cell-days<br>%{customdata}<extra></extra>",
        colorbar=dict(title="Cell-days", thickness=12),
    ))
    fig.update_yaxes(type="category", autorange="reversed", dtick=1)
    return chart_layout(fig, height=max(300, 24 * len(values) + 68), plot_bgcolor="#e8e5dd")


def seasonal_profile(history):
    source = history[history.comparable].assign(month_number=lambda df: df.month.str[5:].astype(int))
    median = source.groupby("month_number").activity.median().reindex(range(1, 13))
    fig = go.Figure(go.Bar(x=list(calendar.month_abbr)[1:], y=median, marker_color="#a34627"))
    return chart_layout(fig, height=260, yaxis_title="Median active cell-days")


def sensor_chart(history):
    fig = go.Figure()
    for column, label, color, dash in (
        ("modis", MODIS, SENSOR_COLORS[MODIS], "solid"),
        ("viirs", VIIRS, SENSOR_COLORS[VIIRS], "solid"),
        ("viirs_adjusted", "Candidate adjusted VIIRS", "#77639b", "dot"),
    ):
        if history[column].notna().any():
            fig.add_trace(go.Scatter(x=history.month, y=history[column], name=label, mode="lines+markers",
                                     line=dict(color=color, dash=dash), marker=dict(size=4), connectgaps=False))
    return chart_layout(fig, height=370, yaxis_title="Active cell-days", legend=dict(orientation="h"))


def harmonization_gap_chart(evaluation):
    gaps = [evaluation["raw_mae"], evaluation["adjusted_mae"]]
    fig = go.Figure(go.Bar(
        x=gaps, y=["Before adjustment", "After adjustment"], orientation="h",
        marker_color=[SENSOR_COLORS[MODIS], SENSOR_COLORS[VIIRS]],
        texttemplate="%{x:.1f}", textposition="outside",
        hovertemplate="%{y}<br>%{x:.3f} active cell-days<extra></extra>",
    ))
    fig.update_xaxes(range=[0, max(1, max(gaps) * 1.2)], title="Mean absolute gap from Aqua MODIS (active cell-days)")
    fig.update_yaxes(autorange="reversed", automargin=True)
    return chart_layout(fig, height=210)


def anomaly_chart(result, earlier):
    years = earlier.month.str[:4].tolist() + [result["month"][:4]]
    values = earlier.activity.tolist() + [result["activity"]]
    fig = go.Figure(go.Bar(x=years, y=values, marker_color=["#a89b81"] * len(earlier) + ["#a34627"]))
    if result["threshold"] is not None:
        fig.add_hline(y=result["threshold"], line_dash="dot", line_color="#196964",
                      annotation_text=f"{result['percentile']}th percentile")
    fig.update_xaxes(type="category")
    return chart_layout(fig, height=300, yaxis_title="Active cell-days")

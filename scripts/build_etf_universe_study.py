#!/usr/bin/env python3
"""Build the standalone Qinvia ETF Universe 1A notebook and HTML report."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from html import escape
import io
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import nbformat
import numpy as np
import pandas as pd


REPORT_BASENAME = "QINVIA_ETF_UNIVERSE_STUDY_1A"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT_LANGUAGE = "es"
BLUE = "#0868d7"
NAVY = "#08296b"
CYAN = "#0bb9df"
RED = "#d84b5b"
AMBER = "#d89014"
GREEN = "#0a9b71"


LABELS = {
    "active_identified": "Activa identificada",
    "index_passive_identified": "Índice/pasiva identificada",
    "systematic_or_rules_based": "Sistemática / reglas",
    "not_determined": "No determinada",
    "equity": "Renta variable",
    "fixed_income": "Renta fija",
    "commodity": "Materias primas",
    "currency": "Divisas",
    "real_estate": "Inmobiliario",
    "alternatives": "Alternativas",
    "multi_asset": "Multiactivo",
    "crypto": "Cripto",
    "unknown": "No resuelta",
    "other_equity": "Renta variable · otra",
    "factor_or_style": "Factores / estilo",
    "sector_or_industry": "Sector / industria",
    "dividend_or_income": "Dividendos / rentas",
    "thematic_equity": "Temática",
    "broad_equity": "Mercado amplio",
    "long_short_market_neutral": "Long/short y market neutral",
    "managed_futures": "Managed futures",
    "merger_arbitrage": "Arbitraje de fusiones",
    "absolute_return": "Retorno absoluto",
    "precious_metals": "Metales preciosos",
    "technology": "Tecnología",
    "semiconductors": "Semiconductores",
    "industrials_transport": "Industriales / transporte",
    "healthcare_biotech": "Salud / biotech",
    "consumer_discretionary": "Consumo discrecional",
    "not_sector_specific": "Sin sector específico",
    "intentional_management": "Gestión intencional",
    "systematic_static_beta": "Beta sistemática / reglas",
    "broad_market_beta": "Mercado amplio",
    "concentrated_equity_beta": "Beta sectorial / temática",
    "other_asset_beta": "Beta de otros activos",
    "fixed_income_beta": "Renta fija",
    "other_or_unresolved": "No resuelta / otros",
}

LABELS_EN = {
    "active_identified": "Identified active",
    "index_passive_identified": "Identified index/passive",
    "systematic_or_rules_based": "Systematic / rules-based",
    "not_determined": "Not determined",
    "equity": "Equity",
    "fixed_income": "Fixed income",
    "commodity": "Commodities",
    "currency": "Currencies",
    "real_estate": "Real estate",
    "alternatives": "Alternatives",
    "multi_asset": "Multi-asset",
    "crypto": "Crypto",
    "unknown": "Unresolved",
    "other_equity": "Equity · other",
    "factor_or_style": "Factor / style",
    "sector_or_industry": "Sector / industry",
    "dividend_or_income": "Dividend / income",
    "thematic_equity": "Thematic equity",
    "broad_equity": "Broad market",
    "long_short_market_neutral": "Long/short and market neutral",
    "managed_futures": "Managed futures",
    "merger_arbitrage": "Merger arbitrage",
    "absolute_return": "Absolute return",
    "precious_metals": "Precious metals",
    "technology": "Technology",
    "semiconductors": "Semiconductors",
    "industrials_transport": "Industrials / transport",
    "healthcare_biotech": "Healthcare / biotech",
    "consumer_discretionary": "Consumer discretionary",
    "not_sector_specific": "No specific sector",
    "intentional_management": "Intentional management",
    "systematic_static_beta": "Systematic / rules beta",
    "broad_market_beta": "Broad-market beta",
    "concentrated_equity_beta": "Sector / thematic beta",
    "other_asset_beta": "Other-asset beta",
    "fixed_income_beta": "Fixed-income beta",
    "other_or_unresolved": "Unresolved / other",
}


def set_language(language: str) -> None:
    global CURRENT_LANGUAGE
    if language not in {"es", "en"}:
        raise ValueError(f"Unsupported language: {language}")
    CURRENT_LANGUAGE = language


def tr(spanish: str, english: str) -> str:
    return english if CURRENT_LANGUAGE == "en" else spanish


def label(value: object) -> str:
    labels = LABELS_EN if CURRENT_LANGUAGE == "en" else LABELS
    return labels.get(str(value), str(value).replace("_", " ").capitalize())


def fmt(value: object, digits: int = 2) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "—"
    if not np.isfinite(numeric):
        return "—"
    rendered = f"{numeric:.{digits}f}".replace("-", "−")
    return rendered if CURRENT_LANGUAGE == "en" else rendered.replace(".", ",")


def pct(value: object, digits: int = 1) -> str:
    try:
        rendered = f"{100 * float(value):.{digits}f}%".replace("-", "−")
        return rendered if CURRENT_LANGUAGE == "en" else rendered.replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def nfmt(value: object) -> str:
    try:
        rendered = f"{int(value):,}"
        return rendered if CURRENT_LANGUAGE == "en" else rendered.replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def data_uri(path: Path) -> str:
    mime = {".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def figure_uri(figure: plt.Figure) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def style_axis(axis: plt.Axes, grid: str = "y") -> None:
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#b9cce0")
    axis.tick_params(colors="#52667d", labelsize=8)
    axis.grid(axis=grid, color="#e7eef6", linewidth=0.8)
    axis.set_axisbelow(True)


def html_table(frame: pd.DataFrame, formats: dict[str, Callable[[Any], str]] | None = None, limit: int | None = None) -> str:
    formats = formats or {}
    shown = frame.head(limit) if limit else frame
    headers = "".join(f"<th>{escape(str(column))}</th>" for column in shown.columns)
    body: list[str] = []
    for _, row in shown.iterrows():
        cells: list[str] = []
        for column, value in row.items():
            formatter = formats.get(column)
            rendered = formatter(value) if formatter else ("—" if pd.isna(value) else str(value))
            cells.append(f"<td>{escape(str(rendered))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="table-wrap"><table><thead><tr>{headers}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def markdown_table(frame: pd.DataFrame, limit: int | None = None) -> str:
    shown = (frame.head(limit) if limit else frame).copy()
    columns = [str(column) for column in shown.columns]
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in shown.itertuples(index=False, name=None):
        values = []
        for value in row:
            if pd.isna(value):
                rendered = "—"
            elif isinstance(value, float):
                rendered = f"{value:.4f}"
            else:
                rendered = str(value)
            values.append(rendered.replace("|", "\\|"))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def lookup_group(groups: pd.DataFrame, dimension: str, group: str) -> pd.Series:
    row = groups[(groups.dimension == dimension) & (groups.group == group)]
    if row.empty:
        raise KeyError((dimension, group))
    return row.iloc[0]


def headline_table(selected: pd.DataFrame, groups: pd.DataFrame) -> pd.DataFrame:
    del groups
    rows: list[dict[str, Any]] = []
    definitions = [
        ("CAGR", "beat_spy_cagr"),
        ("Sortino", "beat_spy_sortino"),
        ("Calmar", "beat_spy_calmar"),
        ("Martin", "beat_spy_martin"),
        ("RWM", "beat_spy_rwm_score"),
        ("CAGR + RWM", "beat_spy_cagr_and_rwm"),
        (tr("Las cuatro a la vez", "All four at once"), "beat_spy_all_four"),
    ]
    for name, column in definitions:
        beaten = int(selected[column].sum())
        rows.append(
            {
                tr("Criterio", "Criterion"): name,
                tr("Baten a SPY", "Beat SPY"): beaten,
                tr("No baten", "Do not beat SPY"): len(selected) - beaten,
                tr("% del universo", "% of universe"): beaten / len(selected),
            }
        )
    return pd.DataFrame(rows)


def funnel_figure(funnel: pd.DataFrame) -> str:
    plot = funnel.copy()
    labels = [
        tr("Catálogo bruto", "Raw catalogue"),
        tr("Elegibles económicos", "Economically eligible"),
        tr("Símbolos únicos", "Unique symbols"),
        tr("Parquet válidos", "Valid Parquet files"),
        tr("Comparables con SPY", "Comparable with SPY"),
        tr("Pasan el corte", "Pass maturity cutoff"),
        tr("Productos sin alias", "Products after alias merge"),
    ]
    plot["label"] = labels[: len(plot)]
    figure, axis = plt.subplots(figsize=(11.4, 5.3), constrained_layout=True)
    colors = ["#bddcf6", "#9dcef1", "#7abde9", "#55ace2", "#2a93d5", BLUE, NAVY]
    axis.barh(plot.label[::-1], plot["count"][::-1], color=colors[::-1])
    maximum = plot["count"].max()
    for position, value in enumerate(plot["count"][::-1]):
        axis.text(value + maximum * 0.012, position, nfmt(value), va="center", fontsize=9, color=NAVY, weight="bold")
    axis.set_xlim(0, maximum * 1.16)
    axis.set_title(tr("Del catálogo al universo de investigación", "From catalogue to research universe"), loc="left", color=NAVY, weight="bold")
    axis.set_xlabel(tr("Identidades, símbolos o productos según la etapa", "Identities, symbols or products at each stage"))
    style_axis(axis, "x")
    return figure_uri(figure)


def pass_rate_figure(selected: pd.DataFrame) -> str:
    labels = ["CAGR", "Sortino", "Calmar", "Martin", "RWM", "CAGR + RWM"]
    values = [
        selected.beat_spy_cagr.mean(),
        selected.beat_spy_sortino.mean(),
        selected.beat_spy_calmar.mean(),
        selected.beat_spy_martin.mean(),
        selected.beat_spy_rwm_score.mean(),
        selected.beat_spy_cagr_and_rwm.mean(),
    ]
    counts = [
        selected.beat_spy_cagr.sum(),
        selected.beat_spy_sortino.sum(),
        selected.beat_spy_calmar.sum(),
        selected.beat_spy_martin.sum(),
        selected.beat_spy_rwm_score.sum(),
        selected.beat_spy_cagr_and_rwm.sum(),
    ]
    figure, axis = plt.subplots(figsize=(11.4, 5.0), constrained_layout=True)
    colors = ["#8aa7c2", "#9cb4ca", "#acc0d3", "#7ea9c9", BLUE, RED]
    bars = axis.bar(labels, np.array(values) * 100, color=colors)
    for bar, value, count in zip(bars, values, counts):
        axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.35, f"{int(count)} · {100*value:.1f}%", ha="center", fontsize=9, color=NAVY, weight="bold")
    axis.set_ylim(0, max(values) * 130)
    axis.set_ylabel(tr("Porcentaje del universo", "Share of the universe"))
    axis.set_title(tr("Radiografía completa; RWM será el criterio de decisión", "The full scorecard; RWM will make the decision"), loc="left", color=NAVY, weight="bold")
    style_axis(axis)
    return figure_uri(figure)


def common_curve_figure(curves: pd.DataFrame, cohort: int) -> str:
    frame = curves.copy()
    frame.session_date = pd.to_datetime(frame.session_date)
    figure, axes = plt.subplots(2, 1, figsize=(12.0, 7.0), gridspec_kw={"height_ratios": [4, 1]}, constrained_layout=True, sharex=True)
    axis = axes[0]
    axis.plot(frame.session_date, frame.spy, color=NAVY, linewidth=2.4, label="SPY")
    axis.plot(frame.session_date, frame.etf_mean_all_available, color=BLUE, linewidth=2.0, label=tr("Media transversal ETF", "Cross-sectional ETF mean"))
    axis.plot(frame.session_date, frame.etf_median_all_available, color=CYAN, linewidth=1.5, label=tr("Mediana transversal ETF", "Cross-sectional ETF median"))
    axis.plot(frame.session_date, frame.etf_mean_fixed_complete, color=AMBER, linewidth=1.2, linestyle="--", label=tr("Media · cobertura completa", "Mean · complete coverage"))
    axis.set_ylabel(tr("Capital normalizado", "Normalised wealth"))
    axis.set_title(tr("Una inversión media en el universo queda por detrás de SPY desde el corte", "The average ETF investment has trailed SPY since the cutoff"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False, ncol=2)
    style_axis(axis)
    coverage = axes[1]
    coverage.fill_between(frame.session_date, frame.available_members, color="#b7d9f3", alpha=0.9)
    coverage.axhline(cohort, color=BLUE, linewidth=1, linestyle="--")
    coverage.set_ylabel("ETF")
    coverage.set_ylim(max(0, frame.available_members.min() - 80), cohort + 25)
    coverage.set_title(tr("Constituyentes con precio observable", "Constituents with observable prices"), loc="left", fontsize=10, color=NAVY)
    style_axis(coverage)
    return figure_uri(figure)


def universe_fan_figure(curves: pd.DataFrame) -> str:
    frame = curves.copy()
    frame.session_date = pd.to_datetime(frame.session_date)
    figure, axis = plt.subplots(figsize=(12.0, 5.8), constrained_layout=True)
    axis.fill_between(
        frame.session_date,
        frame.etf_p10_fixed_complete,
        frame.etf_p90_fixed_complete,
        color="#dceeff",
        alpha=0.85,
        label=tr("Percentiles 10–90", "10th–90th percentiles"),
    )
    axis.fill_between(
        frame.session_date,
        frame.etf_p25_fixed_complete,
        frame.etf_p75_fixed_complete,
        color="#8fc7ed",
        alpha=0.72,
        label=tr("Percentiles 25–75", "25th–75th percentiles"),
    )
    axis.plot(frame.session_date, frame.etf_p50_fixed_complete, color=BLUE, linewidth=2.0, label=tr("Mediana ETF", "ETF median"))
    axis.plot(frame.session_date, frame.spy, color=NAVY, linewidth=2.8, label="SPY")
    axis.scatter(frame.session_date.iloc[-1], frame.spy.iloc[-1], color=NAVY, s=28, zorder=5)
    axis.text(
        frame.session_date.iloc[-1],
        frame.spy.iloc[-1],
        f"  SPY {frame.spy.iloc[-1]:.0f}",
        color=NAVY,
        fontsize=8,
        va="center",
        weight="bold",
    )
    axis.set_ylabel(tr("Capital normalizado a 100", "Wealth rebased to 100"))
    axis.set_title(tr("SPY frente a toda la distribución: no solo supera la media", "SPY against the full distribution: it beats more than the mean"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False, ncol=4, loc="upper left")
    style_axis(axis)
    return figure_uri(figure)


def scatter_figure(selected: pd.DataFrame) -> str:
    plot = selected[
        np.isfinite(selected.excess_cagr) & np.isfinite(selected.excess_rwm_score)
    ].copy()
    rwm_only = plot[plot.beat_spy_rwm_score & ~plot.beat_spy_cagr]
    both = plot[plot.beat_spy_rwm_score & plot.beat_spy_cagr]
    figure, axis = plt.subplots(figsize=(11.8, 5.8), constrained_layout=True)
    axis.scatter(plot.excess_cagr * 100, plot.excess_rwm_score, s=11, alpha=0.20, color="#8aa7c2", label=tr("No supera RWM", "Does not beat RWM"))
    axis.scatter(rwm_only.excess_cagr * 100, rwm_only.excess_rwm_score, s=22, alpha=0.72, color=CYAN, label=tr("Supera RWM", "Beats RWM"))
    axis.scatter(both.excess_cagr * 100, both.excess_rwm_score, s=25, alpha=0.82, color=BLUE, label=tr("Supera RWM + CAGR", "Beats RWM + CAGR"))
    x_low, x_high = plot.excess_cagr.quantile([0.01, 0.995]) * 100
    y_low, y_high = plot.excess_rwm_score.quantile([0.01, 0.995])
    visible = plot[
        plot.beat_spy_rwm_score
        & plot.excess_cagr.mul(100).between(x_low, x_high)
        & plot.excess_rwm_score.between(y_low, y_high)
    ]
    for position, row in enumerate(visible.nlargest(10, "excess_rwm_score").itertuples()):
        axis.annotate(
            row.request_symbol,
            (row.excess_cagr * 100, row.excess_rwm_score),
            xytext=(4, 3 + (position % 3) * 6),
            textcoords="offset points",
            fontsize=6.5,
            color=NAVY,
        )
    axis.axvline(0, color="#52667d", linewidth=0.9)
    axis.axhline(0, color="#52667d", linewidth=0.9)
    axis.set_xlim(x_low - (x_high - x_low) * 0.03, x_high + (x_high - x_low) * 0.03)
    axis.set_ylim(y_low - (y_high - y_low) * 0.04, y_high + (y_high - y_low) * 0.04)
    axis.set_xlabel(tr("Exceso CAGR vs SPY · puntos porcentuales", "CAGR excess vs SPY · percentage points"))
    axis.set_ylabel(tr("Exceso RWM vs SPY", "RWM excess vs SPY"))
    axis.set_title(tr("RWM decide; CAGR conserva el contexto económico", "RWM decides; CAGR keeps the economic context visible"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False, ncol=3, loc="upper left")
    style_axis(axis)
    return figure_uri(figure)


def management_figure(groups: pd.DataFrame) -> str:
    plot = groups[groups.dimension == "management_style"].copy()
    order = ["active_identified", "index_passive_identified", "systematic_or_rules_based", "not_determined"]
    plot = plot.set_index("group").reindex(order).dropna().reset_index()
    y = np.arange(len(plot))
    figure, axis = plt.subplots(figsize=(11.2, 4.8), constrained_layout=True)
    axis.barh(y, plot.rate_beat_spy_rwm_score * 100, height=0.48, color=RED)
    axis.set_yticks(y, [f"{label(value)} · N={int(n)}" for value, n in zip(plot.group, plot.n)])
    axis.invert_yaxis()
    axis.set_xlabel(tr("Porcentaje que bate a SPY", "Share that beats SPY"))
    axis.set_title(tr("La etiqueta de gestión no rebaja el listón de RWM", "A management label does not lower the RWM bar"), loc="left", color=NAVY, weight="bold")
    style_axis(axis, "x")
    return figure_uri(figure)


def management_base_rate_figure(groups: pd.DataFrame) -> str:
    plot = groups[groups.dimension.eq("management_style")].copy()
    order = ["active_identified", "index_passive_identified", "systematic_or_rules_based", "not_determined"]
    plot = plot.set_index("group").reindex(order).dropna().reset_index()
    successes = plot.beat_spy_rwm_score.to_numpy(dtype=float)
    totals = plot.n.to_numpy(dtype=float)
    z = 1.96
    denominator = 1.0 + z**2 / totals
    centers = (successes / totals + z**2 / (2.0 * totals)) / denominator
    half_widths = (
        z
        * np.sqrt((successes / totals) * (1.0 - successes / totals) / totals + z**2 / (4.0 * totals**2))
        / denominator
    )
    rates = successes / totals
    y = np.arange(len(plot))
    figure, axis = plt.subplots(figsize=(11.4, 4.8), constrained_layout=True)
    axis.errorbar(
        rates * 100,
        y,
        xerr=np.vstack(((rates - (centers - half_widths)) * 100, ((centers + half_widths) - rates) * 100)),
        fmt="o",
        markersize=8,
        color=BLUE,
        ecolor="#83a8c8",
        elinewidth=2.4,
        capsize=4,
    )
    axis.set_yticks(y, [f"{label(value)} · {int(s)}/{int(n)}" for value, s, n in zip(plot.group, successes, totals)])
    axis.invert_yaxis()
    for position, rate in enumerate(rates):
        axis.text(rate * 100 + 0.18, position - 0.16, pct(rate), fontsize=8, color=NAVY, weight="bold")
    axis.set_xlabel(tr("Superan el RWM de SPY · intervalo Wilson del 95%", "Beat SPY's RWM · 95% Wilson interval"))
    axis.set_title(tr("La etiqueta de gestión apenas cambia la tasa base observada", "The management label barely shifts the observed base rate"), loc="left", color=NAVY, weight="bold")
    style_axis(axis, "x")
    return figure_uri(figure)


def asset_heatmap_figure(groups: pd.DataFrame) -> str:
    plot = groups[(groups.dimension == "asset_class_refined") & (groups.n >= 7)].copy().sort_values("n", ascending=False)
    plot = plot.sort_values("n")
    figure, axes = plt.subplots(1, 2, figsize=(11.8, 5.8), constrained_layout=True)
    labels = [label(value) for value in plot.group]
    axes[0].barh(labels, plot.n, color="#9dcef1")
    axes[0].set_title(tr("Tamaño de cada clase", "Size of each asset class"), loc="left", color=NAVY, weight="bold")
    axes[0].set_xlabel(tr("Productos", "Products"))
    style_axis(axes[0], "x")
    axes[1].barh(labels, plot.rate_beat_spy_rwm_score * 100, color=RED)
    for position, row in enumerate(plot.itertuples()):
        axes[1].text(row.rate_beat_spy_rwm_score * 100 + 0.2, position, f"{int(row.beat_spy_rwm_score)}", va="center", fontsize=8, color=NAVY)
    axes[1].set_title(tr("Superan el RWM de SPY", "Beat SPY's RWM"), loc="left", color=NAVY, weight="bold")
    axes[1].set_xlabel(tr("Porcentaje · cifra = productos", "Percentage · number = products"))
    style_axis(axes[1], "x")
    return figure_uri(figure)


def inception_figure(selected: pd.DataFrame) -> str:
    plot = selected.copy()
    plot["year"] = pd.to_datetime(plot.start_date).dt.year
    all_counts = plot.groupby("year").size()
    winner_counts = plot[plot.beat_spy_rwm_score].groupby("year").size().reindex(all_counts.index, fill_value=0)
    figure, axis = plt.subplots(figsize=(11.5, 4.8), constrained_layout=True)
    axis.bar(all_counts.index, all_counts.values, color="#b8d9f2", label=tr("Universo", "Universe"))
    axis.bar(winner_counts.index, winner_counts.values, color=RED, label=tr("Superan RWM de SPY", "Beat SPY's RWM"))
    axis.axvline(2022, color=AMBER, linestyle="--", linewidth=1.5, label=tr("Corte 01/03/2022", "Cutoff 1 Mar 2022"))
    axis.set_xlim(all_counts.index.min() - 1, 2023)
    axis.set_xlabel(tr("Año de primera sesión utilizable", "Year of first usable session"))
    axis.set_ylabel(tr("Productos", "Products"))
    axis.set_title(tr("El corte evita declarar ganadores con unos pocos meses de historia", "The cutoff prevents a few months of history from creating winners"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False, ncol=3)
    style_axis(axis)
    return figure_uri(figure)


def strategy_figure(groups: pd.DataFrame) -> str:
    plot = groups[(groups.dimension == "primary_strategy") & (groups.n >= 10)].copy()
    plot = plot.sort_values("rate_beat_spy_rwm_score").tail(16)
    y = np.arange(len(plot))
    figure, axis = plt.subplots(figsize=(11.5, 7.0), constrained_layout=True)
    colors = [RED if value == "long_short_market_neutral" else BLUE for value in plot.group]
    axis.barh(y, plot.rate_beat_spy_rwm_score * 100, color=colors)
    axis.set_yticks(y, [f"{label(value)} · N={int(n)}" for value, n in zip(plot.group, plot.n)])
    for position, row in enumerate(plot.itertuples()):
        axis.text(row.rate_beat_spy_rwm_score * 100 + 0.25, position, f"{int(row.beat_spy_rwm_score)}", va="center", fontsize=8, color=NAVY)
    axis.set_xlabel(tr("Superan RWM de SPY (%) · cifra al final = productos", "Beat SPY's RWM (%) · end label = products"))
    axis.set_title(tr("Los ganadores no se reparten por igual entre estrategias", "Winners are not evenly distributed across strategies"), loc="left", color=NAVY, weight="bold")
    style_axis(axis, "x")
    return figure_uri(figure)


def winner_provenance_figure(evidence: pd.DataFrame) -> str:
    order = [
        "broad_market_beta",
        "concentrated_equity_beta",
        "systematic_static_beta",
        "other_asset_beta",
        "intentional_management",
        "other_or_unresolved",
        "fixed_income_beta",
    ]
    plot = evidence.set_index("evidence_bucket").reindex(order).dropna().reset_index()
    y = np.arange(len(plot))
    figure, axis = plt.subplots(figsize=(11.7, 5.7), constrained_layout=True)
    axis.barh(y + 0.17, plot.beat_spy_rwm_score, height=0.32, color=BLUE, label="RWM")
    axis.barh(y - 0.17, plot.beat_spy_cagr_and_rwm, height=0.32, color=RED, label="CAGR + RWM")
    axis.set_yticks(y, [f"{label(value)} · N={int(n)}" for value, n in zip(plot.evidence_bucket, plot.n)])
    axis.invert_yaxis()
    axis.set_xlabel(tr("Productos que baten a SPY", "Products that beat SPY"))
    axis.set_title(tr("Procedencia de los ganadores: exposición no equivale a habilidad", "Where winners come from: exposure is not skill"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False)
    style_axis(axis, "x")
    return figure_uri(figure)


def managed_scorecard_figure(managed: pd.DataFrame) -> str:
    labels = ["CAGR", "RWM", "CAGR + RWM"]
    columns = ["beat_spy_cagr", "beat_spy_rwm_score", "beat_spy_cagr_and_rwm"]
    counts = [int(managed[column].sum()) for column in columns]
    values = np.array(counts) / len(managed) * 100
    figure, axis = plt.subplots(figsize=(10.9, 4.6), constrained_layout=True)
    bars = axis.bar(labels, values, color=["#8aa7c2", BLUE, RED])
    for bar, count, value in zip(bars, counts, values):
        axis.text(bar.get_x() + bar.get_width() / 2, value + 0.25, f"{count} · {value:.1f}%", ha="center", color=NAVY, fontsize=9, weight="bold")
    axis.set_ylim(0, max(values) * 1.35)
    axis.set_ylabel(tr("Porcentaje de gestión intencional", "Share of intentional-management products"))
    axis.set_title(tr("El listón sigue alto cuando aislamos productos que toman decisiones", "The bar stays high when we isolate products that make decisions"), loc="left", color=NAVY, weight="bold")
    style_axis(axis)
    return figure_uri(figure)


def leverage_grid_figure(grid: pd.DataFrame) -> str:
    figure, axis = plt.subplots(figsize=(11.4, 5.2), constrained_layout=True)
    series = [
        ("beat_rwm_score", "RWM", BLUE),
        ("beat_cagr", "CAGR", CYAN),
        ("beat_cagr_and_rwm", "CAGR + RWM", RED),
    ]
    for column, name, color in series:
        axis.plot(grid.initial_leverage, grid[column], marker="o", linewidth=2.1, color=color, label=name)
        for x, y in zip(grid.initial_leverage, grid[column]):
            axis.text(x, y + 0.25, str(int(y)), ha="center", fontsize=8, color=color)
    axis.set_xticks(grid.initial_leverage, [f"{fmt(value)}×" for value in grid.initial_leverage])
    axis.set_ylabel(tr("Candidatos de riesgo que baten a SPY", "Risk-efficient candidates that beat SPY"))
    axis.set_xlabel(tr("Apalancamiento inicial · deuda fija, sin rebalanceo", "Initial leverage · fixed debt, no rebalancing"))
    axis.set_title(tr("Más exposición eleva el CAGR, pero puede erosionar RWM", "More exposure raises CAGR—but may erode RWM"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False, ncol=3)
    style_axis(axis)
    return figure_uri(figure)


def return_match_figure(matched: pd.DataFrame, sensitivity: pd.DataFrame) -> str:
    finite = matched[np.isfinite(matched.required_initial_leverage)].copy()
    finite["rwm_excess_matched"] = finite.matched_rwm_score - finite.spy_rwm_score
    figure, axes = plt.subplots(1, 2, figsize=(12.0, 5.5), constrained_layout=True)
    axis = axes[0]
    colors = np.where(finite.feasible_at_or_below_2x, BLUE, "#a9b8c8")
    axis.scatter(finite.required_initial_leverage, finite.rwm_excess_matched, s=55, color=colors, alpha=0.82)
    for row in finite.itertuples():
        axis.annotate(row.request_symbol, (row.required_initial_leverage, row.rwm_excess_matched), xytext=(4, 4), textcoords="offset points", fontsize=7, color=NAVY)
    axis.axvline(2.0, color=RED, linestyle="--", linewidth=1.2, label=tr("Límite 2×", "2× limit"))
    axis.axhline(0.0, color="#52667d", linewidth=1)
    axis.set_xlabel(tr("Apalancamiento inicial para igualar riqueza final", "Initial leverage required to match terminal wealth"))
    axis.set_ylabel(tr("RWM apalancado − RWM SPY", "Levered RWM − SPY RWM"))
    axis.set_title(tr("Igualar retorno no garantiza conservar RWM", "Matching return does not guarantee preserving RWM"), loc="left", color=NAVY, weight="bold")
    axis.legend(frameon=False)
    style_axis(axis)

    second = axes[1]
    x = np.arange(len(sensitivity))
    second.plot(x, sensitivity.feasible_at_or_below_2x, marker="o", color=BLUE, label=tr("Igualan retorno ≤2×", "Match return at ≤2×"))
    second.plot(x, sensitivity.matched_rwm_better, marker="o", color=RED, label=tr("Y conservan RWM", "And preserve RWM"))
    second.set_xticks(x, [f"+{pct(value)}" for value in sensitivity.financing_spread])
    second.set_xlabel(tr("Diferencial sobre Fed Funds", "Spread over Fed Funds"))
    second.set_ylabel(tr("Productos", "Products"))
    second.set_title(tr("La conclusión resiste al coste de financiación", "The conclusion survives financing costs"), loc="left", color=NAVY, weight="bold")
    second.legend(frameon=False, fontsize=8)
    style_axis(second)
    return figure_uri(figure)


def return_matched_equity_figure(curves: pd.DataFrame) -> str:
    symbols = (
        curves[["request_symbol", "required_initial_leverage"]]
        .drop_duplicates()
        .sort_values("required_initial_leverage")
    )
    figure, axes = plt.subplots(2, 3, figsize=(12.2, 7.8), constrained_layout=True)
    for axis, row in zip(axes.flat, symbols.itertuples(index=False)):
        frame = curves[curves.request_symbol.eq(row.request_symbol)].copy()
        frame.session_date = pd.to_datetime(frame.session_date)
        highlight = False
        matched_color = BLUE
        axis.plot(frame.session_date, frame.spy, color=NAVY, linewidth=2.1, label="SPY")
        axis.plot(
            frame.session_date,
            frame.etf_unlevered,
            color="#96a8bb",
            linewidth=1.4,
            linestyle="--",
            label=tr("ETF sin apalancar", "Unlevered ETF"),
        )
        axis.plot(
            frame.session_date,
            frame.etf_return_matched,
            color=matched_color,
            linewidth=2.0,
            label=tr("ETF · retorno igualado", "ETF · return matched"),
        )
        axis.set_title(
            f"{row.request_symbol} · {fmt(row.required_initial_leverage)}×",
            loc="left",
            color=matched_color if highlight else NAVY,
            weight="bold",
        )
        axis.set_ylabel(tr("Capital · base 100", "Wealth · base 100"))
        locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
        axis.xaxis.set_major_locator(locator)
        axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        style_axis(axis)
        if axis is axes.flat[0]:
            axis.legend(frameon=False, fontsize=7.2, loc="upper left")
    for axis in axes.flat[len(symbols) :]:
        axis.set_visible(False)
    figure.suptitle(
        tr("Mismo capital final, caminos muy distintos", "Same terminal wealth, very different paths"),
        color=NAVY,
        weight="bold",
        fontsize=15,
    )
    return figure_uri(figure)


def rolling_robustness_figure(rolling: pd.DataFrame) -> str:
    plot = rolling.sort_values("rate_beat_rwm_score")
    y = np.arange(len(plot))
    figure, axis = plt.subplots(figsize=(11.2, 5.4), constrained_layout=True)
    colors = [GREEN if value >= 0.5 else RED for value in plot.rate_beat_rwm_score]
    axis.barh(y, plot.rate_beat_rwm_score * 100, color=colors)
    axis.set_yticks(y, [f"{symbol} · {int(windows)} {tr('ventanas', 'windows')}" for symbol, windows in zip(plot.request_symbol, plot.rolling_windows)])
    for position, value in enumerate(plot.rate_beat_rwm_score):
        axis.text(value * 100 + 1, position, f"{100*value:.0f}%", va="center", fontsize=8, color=NAVY)
    axis.axvline(50, color="#52667d", linestyle="--", linewidth=1)
    axis.set_xlim(0, 108)
    axis.set_xlabel(tr("Meses de entrada cuya ventana de 756 sesiones supera el RWM de SPY", "Entry months whose 756-session window beats SPY's RWM"))
    axis.set_title(tr("Estabilidad al punto de entrada, no pruebas independientes", "Entry-point stability—not independent tests"), loc="left", color=NAVY, weight="bold")
    style_axis(axis, "x")
    return figure_uri(figure)


def prepare_table(frame: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    return frame[list(columns)].rename(columns=columns).copy()


TABLE_COLUMNS_EN = {
    "Criterio": "Criterion",
    "Baten a SPY": "Beat SPY",
    "No baten": "Do not beat SPY",
    "% del universo": "% of universe",
    "Gestión": "Management",
    "Estrategia": "Strategy",
    "Superan RWM": "Beat RWM",
    "% del grupo": "% of group",
    "Producto": "Product",
    "Inicio Yahoo": "Yahoo start",
    "Clase": "Asset class",
    "Proceso": "Process",
    "Proceso identificado": "Identified process",
    "Supera CAGR": "Beats CAGR",
    "Apalancamiento inicial": "Initial leverage",
    "Candidatos": "Candidates",
    "Baten CAGR": "Beat CAGR",
    "Conservan RWM": "Preserve RWM",
    "Baten ambos": "Beat both",
    "Margen sobre Fed Funds": "Spread over Fed Funds",
    "Alcanzables ≤ 2×": "Feasible at ≤ 2×",
    "Apalancamiento requerido": "Required leverage",
    "RWM igualado": "Matched RWM",
    "Resultado": "Outcome",
    "Supera RWM": "Beats RWM",
    "Peor Δ CAGR": "Worst Δ CAGR",
    "Peor Δ RWM": "Worst Δ RWM",
    "Ticker anterior": "Previous ticker",
    "Ticker actual": "Current ticker",
    "Evidencia": "Evidence",
    "Motivo resumido": "Summary reason",
    "Productos": "Products",
}


def english_frame(frame: pd.DataFrame) -> pd.DataFrame:
    value_map = {LABELS[key]: LABELS_EN[key] for key in LABELS.keys() & LABELS_EN.keys()}
    value_map.update(
        {
            "Sí": "Yes",
            "No": "No",
            "Las cuatro a la vez": "All four at once",
            "Iguala y conserva RWM": "Matches and preserves RWM",
            "Iguala; pierde RWM": "Matches; loses RWM",
            "Exige más de 2×": "Requires more than 2×",
            "La financiación supera el retorno": "Financing exceeds return",
            "Apalancados o inversos": "Leveraged or inverse",
            "Payoff estructurado o protección de cola": "Structured payoff or tail protection",
            "Símbolo o vehículo no negociable": "Non-tradable symbol or vehicle",
            "No lanzados o sin negociación comprobable": "Never launched or no verified trading",
            "Productos de volatilidad": "Volatility products",
        }
    )
    return frame.rename(columns=TABLE_COLUMNS_EN).replace(value_map)


def build(results_root: Path, output_root: Path, logo_path: Path, icon_path: Path, catalogue_path: Path) -> tuple[Path, Path, Path, Path]:
    set_language("es")
    summary = json.loads((results_root / "study_summary.json").read_text(encoding="utf-8"))
    selected = pd.read_parquet(results_root / "selected_etfs.parquet")
    selected["joint_excess_score"] = (
        selected["excess_cagr"].rank(pct=True) + selected["excess_rwm_score"].rank(pct=True)
    ) / 2.0
    qualifying = pd.read_parquet(results_root / "qualifying_series_with_aliases.parquet")
    groups = pd.read_parquet(results_root / "group_summaries.parquet")
    curves = pd.read_parquet(results_root / "common_period_curves.parquet")
    funnel = pd.read_csv(results_root / "selection_funnel.csv")
    winners = pd.read_csv(results_root / "winners_all_four.csv")
    dbf_leaders = pd.read_csv(results_root / "dbf_leaders.csv")
    rwm_leaders = pd.read_csv(results_root / "rwm_leaders.csv")
    active = pd.read_csv(results_root / "active_identified.csv")
    alternatives = pd.read_csv(results_root / "alternative_strategies.csv")
    evidence = pd.read_csv(results_root / "evidence_bucket_summary.csv")
    managed = pd.read_csv(results_root / "intentional_management_products.csv")
    risk_candidates = pd.read_csv(results_root / "risk_efficient_candidates.csv")
    leverage_grid = pd.read_csv(results_root / "leverage_grid.csv")
    leverage_summary = pd.read_csv(results_root / "leverage_grid_summary.csv")
    return_matched = pd.read_csv(results_root / "return_matched_leverage.csv")
    return_matched_curves = pd.read_parquet(results_root / "return_matched_equity_curves.parquet")
    financing_sensitivity = pd.read_csv(results_root / "financing_sensitivity_summary.csv")
    rolling = pd.read_csv(results_root / "managed_winner_rolling_robustness.csv")
    leverage_meta = json.loads((results_root / "leverage_summary.json").read_text(encoding="utf-8"))
    catalogue = pd.read_csv(catalogue_path, keep_default_na=False)
    raw_exclusions = catalogue[catalogue.eligibility == "ineligible"].eligibility_reason.value_counts()
    exclusion_groups = [
        ("Apalancados o inversos", ["leveraged_exposure", "inverse_exposure", "embedded_leverage"]),
        ("Payoff estructurado o protección de cola", ["structured_path_dependent_payoff", "protective_tail_risk_strategy"]),
        ("Símbolo o vehículo no negociable", ["yahoo_non_tradable_symbol", "mutual_fund_share_class", "invalid_listing_symbol"]),
        ("No lanzados o sin negociación comprobable", ["registered_not_trading", "never_launched", "registered_only_no_trading_evidence"]),
        ("Productos de volatilidad", ["volatility_trading"]),
    ]
    exclusions = pd.DataFrame(
        [
            {"Motivo resumido": name, "Productos": int(sum(raw_exclusions.get(key, 0) for key in keys))}
            for name, keys in exclusion_groups
        ]
    )

    output_root.mkdir(parents=True, exist_ok=True)
    data_root = output_root / "data"
    data_root.mkdir(exist_ok=True)
    for source in results_root.iterdir():
        if source.suffix.lower() in {".json", ".csv", ".parquet"}:
            shutil.copy2(source, data_root / source.name)
    cash_source = PROJECT_ROOT / "data/external/macro/fred_dff_daily.csv"
    if cash_source.exists():
        shutil.copy2(cash_source, data_root / "fred_dff_daily.csv")

    headline = headline_table(selected, groups)
    headline_html = html_table(headline, {"Baten a SPY": nfmt, "No baten": nfmt, "% del universo": lambda x: pct(x)})
    management = groups[groups.dimension == "management_style"].copy()
    management["Gestión"] = management.group.map(label)
    management_table = prepare_table(
        management,
        {
            "Gestión": "Gestión",
            "n": "N",
            "beat_spy_rwm_score": "Superan RWM",
            "rate_beat_spy_rwm_score": "% del grupo",
        },
    )
    management_html = html_table(management_table, {"% del grupo": lambda x: pct(x)})

    strategies = groups[(groups.dimension == "primary_strategy") & (groups.n >= 5)].copy().head(35)
    strategies["Estrategia"] = strategies.group.map(label)
    strategy_table = prepare_table(
        strategies,
        {
            "Estrategia": "Estrategia",
            "n": "N",
            "beat_spy_rwm_score": "Superan RWM",
            "rate_beat_spy_rwm_score": "% del grupo",
        },
    )
    strategy_html = html_table(strategy_table, {"% del grupo": lambda x: pct(x)})

    winner_table = prepare_table(
        winners,
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "start_date": "Inicio Yahoo",
            "asset_class_refined": "Clase",
            "excess_cagr": "Δ CAGR",
            "excess_sortino": "Δ Sortino",
            "excess_calmar": "Δ Calmar",
            "excess_martin": "Δ Martin",
            "excess_rwm_score": "Δ RWM",
        },
    )
    winner_table["Clase"] = winner_table["Clase"].map(label)
    winner_html = html_table(
        winner_table,
        {"Δ CAGR": lambda x: pct(x), "Δ Sortino": lambda x: fmt(x), "Δ Calmar": lambda x: fmt(x), "Δ Martin": lambda x: fmt(x), "Δ RWM": lambda x: fmt(x)},
        limit=25,
    )

    rwm_ranked = rwm_leaders[rwm_leaders.beat_spy_rwm_score.astype(bool)].copy()
    rwm_ranked["beat_spy_cagr"] = rwm_ranked.cagr > rwm_ranked.spy_cagr
    rwm_table = prepare_table(
        rwm_ranked.sort_values("excess_rwm_score", ascending=False),
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "management_style": "Proceso",
            "cagr": "CAGR",
            "spy_cagr": "SPY CAGR",
            "rwm_score": "RWM",
            "spy_rwm_score": "SPY RWM",
            "excess_rwm_score": "Δ RWM",
            "beat_spy_cagr": "Supera CAGR",
        },
    )
    rwm_table["Proceso"] = rwm_table["Proceso"].map(label)
    rwm_html = html_table(
        rwm_table,
        {
            "CAGR": lambda x: pct(x),
            "SPY CAGR": lambda x: pct(x),
            "RWM": lambda x: fmt(x, 3),
            "SPY RWM": lambda x: fmt(x, 3),
            "Δ RWM": lambda x: fmt(x, 3),
            "Supera CAGR": lambda x: "Sí" if bool(x) else "No",
        },
        limit=15,
    )

    dbf_table = prepare_table(
        selected[np.isfinite(selected.dbf_signed)].sort_values("dbf_signed", ascending=False),
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "cagr": "CAGR",
            "dbf_signed": "DBF±",
            "direction": "D±",
            "breadth": "J",
        },
    )
    dbf_html = html_table(
        dbf_table,
        {
            "CAGR": lambda x: pct(x),
            "DBF±": lambda x: fmt(x, 3),
            "D±": lambda x: fmt(x, 3),
            "J": lambda x: fmt(x, 3),
        },
        limit=10,
    )

    managed_winners = managed[managed.beat_spy_rwm_score.astype(bool)].copy().sort_values("excess_rwm_score", ascending=False)
    managed_winner_table = prepare_table(
        managed_winners,
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "primary_strategy": "Estrategia",
            "cagr": "CAGR",
            "spy_cagr": "SPY CAGR",
            "rwm_score": "RWM",
            "spy_rwm_score": "SPY RWM",
            "beat_spy_cagr": "Supera CAGR",
        },
    )
    managed_winner_table["Estrategia"] = managed_winner_table["Estrategia"].map(label)
    managed_winner_html = html_table(
        managed_winner_table,
        {"CAGR": lambda x: pct(x), "SPY CAGR": lambda x: pct(x), "RWM": lambda x: fmt(x, 3), "SPY RWM": lambda x: fmt(x, 3), "Supera CAGR": lambda x: "Sí" if bool(x) else "No"},
    )

    risk_table = prepare_table(
        risk_candidates.sort_values("excess_rwm_score", ascending=False),
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "asset_class_refined": "Clase",
            "primary_strategy": "Estrategia",
            "management_style": "Proceso identificado",
            "cagr": "CAGR",
            "spy_cagr": "SPY CAGR",
            "rwm_score": "RWM",
            "spy_rwm_score": "SPY RWM",
        },
    )
    risk_table["Clase"] = risk_table["Clase"].map(label)
    risk_table["Estrategia"] = risk_table["Estrategia"].map(label)
    risk_table["Proceso identificado"] = risk_table["Proceso identificado"].map(label)
    risk_html = html_table(
        risk_table,
        {"CAGR": lambda x: pct(x), "SPY CAGR": lambda x: pct(x), "RWM": lambda x: fmt(x, 3), "SPY RWM": lambda x: fmt(x, 3)},
    )

    leverage_table = leverage_summary.rename(
        columns={
            "initial_leverage": "Apalancamiento inicial",
            "candidates": "Candidatos",
            "beat_cagr": "Baten CAGR",
            "beat_rwm_score": "Conservan RWM",
            "beat_cagr_and_rwm": "Baten ambos",
        }
    )[["Apalancamiento inicial", "Candidatos", "Baten CAGR", "Conservan RWM", "Baten ambos"]]
    leverage_html = html_table(
        leverage_table,
        {
            "Apalancamiento inicial": lambda x: f"{fmt(x)}×",
            "Candidatos": nfmt,
            "Baten CAGR": nfmt,
            "Conservan RWM": nfmt,
            "Baten ambos": nfmt,
        },
    )

    sensitivity_table = financing_sensitivity.rename(
        columns={
            "financing_spread": "Margen sobre Fed Funds",
            "feasible_at_or_below_2x": "Alcanzables ≤ 2×",
            "matched_rwm_better": "Conservan RWM",
        }
    )[["Margen sobre Fed Funds", "Alcanzables ≤ 2×", "Conservan RWM"]]
    sensitivity_html = html_table(
        sensitivity_table,
        {
            "Margen sobre Fed Funds": lambda x: pct(x),
            "Alcanzables ≤ 2×": nfmt,
            "Conservan RWM": nfmt,
        },
    )

    matched_table = return_matched.copy().sort_values("required_initial_leverage")
    matched_table["Resultado"] = np.where(
        matched_table.feasible_at_or_below_2x,
        np.where(matched_table.matched_rwm_beats_spy.fillna(False), "Iguala y conserva RWM", "Iguala; pierde RWM"),
        np.where(np.isfinite(matched_table.required_initial_leverage), "Exige más de 2×", "La financiación supera el retorno"),
    )
    matched_table = prepare_table(
        matched_table,
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "primary_strategy": "Estrategia",
            "management_style": "Proceso identificado",
            "required_initial_leverage": "Apalancamiento requerido",
            "matched_rwm_score": "RWM igualado",
            "spy_rwm_score": "SPY RWM",
            "Resultado": "Resultado",
        },
    )
    matched_table["Estrategia"] = matched_table["Estrategia"].map(label)
    matched_table["Proceso identificado"] = matched_table["Proceso identificado"].map(label)
    matched_html = html_table(
        matched_table,
        {
            "Apalancamiento requerido": lambda x: "No alcanzable" if not np.isfinite(float(x)) else f"{fmt(x)}×",
            "RWM igualado": lambda x: fmt(x, 3),
            "SPY RWM": lambda x: fmt(x, 3),
        },
    )

    rolling_display = rolling.copy()
    rolling_display["windows_rwm"] = [
        f"{int(round(rate * windows))}/{int(windows)}"
        for rate, windows in zip(rolling_display.rate_beat_rwm_score, rolling_display.rolling_windows)
    ]
    rolling_table = prepare_table(
        rolling_display,
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "windows_rwm": "Supera RWM",
            "rate_beat_cagr": "% CAGR",
            "rate_beat_rwm_score": "% RWM",
            "rate_beat_cagr_and_rwm": "% CAGR + RWM",
            "minimum_excess_cagr": "Peor Δ CAGR",
            "minimum_excess_rwm_score": "Peor Δ RWM",
        },
    )
    rolling_html = html_table(
        rolling_table,
        {"% CAGR": lambda x: pct(x), "% RWM": lambda x: pct(x), "% CAGR + RWM": lambda x: pct(x), "Peor Δ CAGR": lambda x: pct(x), "Peor Δ RWM": lambda x: fmt(x, 3)},
    )

    active_winners = active[active.beat_spy_rwm_score.astype(bool)].copy()
    active_table = prepare_table(
        active_winners,
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "start_date": "Inicio Yahoo",
            "primary_strategy": "Estrategia",
            "cagr": "CAGR",
            "spy_cagr": "SPY CAGR",
            "rwm_score": "RWM",
            "spy_rwm_score": "SPY RWM",
        },
    )
    active_table["Estrategia"] = active_table["Estrategia"].map(label)
    active_html = html_table(active_table, {"CAGR": lambda x: pct(x), "SPY CAGR": lambda x: pct(x), "RWM": lambda x: fmt(x, 3), "SPY RWM": lambda x: fmt(x, 3)})

    alternatives_table = prepare_table(
        alternatives,
        {
            "request_symbol": "Ticker",
            "name": "Producto",
            "primary_strategy": "Estrategia",
            "cagr": "CAGR",
            "spy_cagr": "SPY CAGR",
            "rwm_score": "RWM",
            "spy_rwm_score": "SPY RWM",
            "beat_spy_cagr_and_rwm": "CAGR + RWM",
        },
    )
    alternatives_table["Estrategia"] = alternatives_table["Estrategia"].map(label)
    alternatives_html = html_table(alternatives_table, {"CAGR": lambda x: pct(x), "SPY CAGR": lambda x: pct(x), "RWM": lambda x: fmt(x, 3), "SPY RWM": lambda x: fmt(x, 3)})

    aliases = qualifying[~qualifying.analysis_primary][["request_symbol", "canonical_symbol", "normalized_name"]].rename(
        columns={"request_symbol": "Ticker anterior", "canonical_symbol": "Ticker actual", "normalized_name": "Producto"}
    )
    aliases["Producto"] = aliases["Producto"].str.replace("\uf0d2", " ", regex=False).str.replace(r"\s+", " ", regex=True)
    aliases_html = html_table(aliases)
    unresolved = selected[selected.asset_class_refined == "unknown"][["request_symbol", "name", "taxonomy_evidence"]].rename(
        columns={"request_symbol": "Ticker", "name": "Producto", "taxonomy_evidence": "Evidencia"}
    )
    unresolved_html = html_table(unresolved)
    exclusions_html = html_table(exclusions)

    funnel_plot = funnel_figure(funnel)
    pass_plot = pass_rate_figure(selected)
    curve_plot = common_curve_figure(curves, len(selected))
    universe_fan_plot = universe_fan_figure(curves)
    scatter_plot = scatter_figure(selected)
    management_plot = management_figure(groups)
    management_base_rate_plot = management_base_rate_figure(groups)
    assets_plot = asset_heatmap_figure(groups)
    inception_plot = inception_figure(selected)
    strategy_plot = strategy_figure(groups)
    provenance_plot = winner_provenance_figure(evidence)
    managed_plot = managed_scorecard_figure(managed)
    leverage_plot = leverage_grid_figure(leverage_summary)
    return_match_plot = return_match_figure(return_matched, financing_sensitivity)
    return_matched_equity_plot = return_matched_equity_figure(return_matched_curves)
    rolling_plot = rolling_robustness_figure(rolling)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    logo = data_uri(logo_path)
    notebook_logo = Path(os.path.relpath(logo_path, output_root)).as_posix()
    icon = data_uri(icon_path)
    cohort = len(selected)
    qualifying_n = len(qualifying)
    cagr_n = int(selected.beat_spy_cagr.sum())
    sortino_n = int(selected.beat_spy_sortino.sum())
    calmar_n = int(selected.beat_spy_calmar.sum())
    martin_n = int(selected.beat_spy_martin.sum())
    both_n = int(selected.beat_spy_cagr_and_martin.sum())
    four_n = int(selected.beat_spy_all_four.sum())
    rwm_n = int(selected.beat_spy_rwm_score.sum())
    cagr_rwm_n = int(selected.beat_spy_cagr_and_rwm.sum())
    active_n = int((selected.management_style == "active_identified").sum())
    active_both = int(selected.loc[selected.management_style == "active_identified", "beat_spy_cagr_and_martin"].sum())
    active_four = int(selected.loc[selected.management_style == "active_identified", "beat_spy_all_four"].sum())
    active_rwm = int(selected.loc[selected.management_style == "active_identified", "beat_spy_rwm_score"].sum())
    active_cagr_rwm = int(selected.loc[selected.management_style == "active_identified", "beat_spy_cagr_and_rwm"].sum())
    dbf_n = int(selected.beat_spy_dbf_signed.sum())
    cagr_dbf_n = int((selected.beat_spy_cagr & selected.beat_spy_dbf_signed).sum())
    managed_n = len(managed)
    managed_strict_active_n = int(managed.management_style.eq("active_identified").sum())
    managed_dynamic_inferred_n = managed_n - managed_strict_active_n
    managed_cagr_n = int(managed.beat_spy_cagr.sum())
    managed_martin_n = int(managed.beat_spy_martin.sum())
    managed_both_n = int(managed.beat_spy_cagr_and_martin.sum())
    managed_four_n = int(managed.beat_spy_all_four.sum())
    managed_rwm_n = int(managed.beat_spy_rwm_score.sum())
    managed_cagr_rwm_n = int((managed.beat_spy_cagr & managed.beat_spy_rwm_score).sum())
    risk_candidate_n = len(risk_candidates)
    risk_active_n = int(risk_candidates.management_style.eq("active_identified").sum())
    risk_dynamic_inferred_n = risk_candidate_n - risk_active_n
    feasible_match_n = int(leverage_meta["return_match_feasible_at_or_below_2x"])
    feasible_martin_n = int(leverage_meta["return_match_feasible_and_martin_better"])
    feasible_rwm_n = int(leverage_meta["return_match_feasible_and_rwm_better"])
    feasible_all_risk_n = int(leverage_meta["return_match_feasible_and_all_three_risk_better"])
    robust_managed_n = int(leverage_meta["managed_winners_robust_in_majority_rolling_windows"])
    clear_beta_four_n = int(
        evidence.loc[
            evidence.evidence_bucket.isin(["broad_market_beta", "concentrated_equity_beta", "systematic_static_beta", "other_asset_beta"]),
            "beat_spy_all_four",
        ].sum()
    )
    unresolved_four_n = int(evidence.loc[evidence.evidence_bucket.eq("other_or_unresolved"), "beat_spy_all_four"].sum())
    clear_beta_rwm_n = int(
        evidence.loc[
            evidence.evidence_bucket.isin(["broad_market_beta", "concentrated_equity_beta", "systematic_static_beta", "other_asset_beta"]),
            "beat_spy_rwm_score",
        ].sum()
    )
    managed_evidence_rwm_n = int(evidence.loc[evidence.evidence_bucket.eq("intentional_management"), "beat_spy_rwm_score"].sum())
    unresolved_rwm_n = int(evidence.loc[evidence.evidence_bucket.eq("other_or_unresolved"), "beat_spy_rwm_score"].sum())
    long_short = selected[selected.primary_strategy == "long_short_market_neutral"]
    curve_metrics = summary["curve_diagnostics"]["curve_metrics"]
    spy_curve = curve_metrics["spy"]
    average_curve = curve_metrics["etf_mean_fixed_complete"]
    qqq = selected[selected.request_symbol == "QQQ"].iloc[0]
    cg = selected[selected.request_symbol.isin(["CGDV", "CGXU"])][["request_symbol", "name", "start_date", "cagr", "spy_cagr", "rwm_score", "spy_rwm_score", "beat_spy_cagr_and_rwm"]].copy()
    cg_html = html_table(cg.rename(columns={"request_symbol": "Ticker", "name": "Producto", "start_date": "Inicio Yahoo", "cagr": "CAGR", "spy_cagr": "SPY CAGR", "rwm_score": "RWM", "spy_rwm_score": "SPY RWM", "beat_spy_cagr_and_rwm": "CAGR + RWM"}), {"CAGR": lambda x: pct(x), "SPY CAGR": lambda x: pct(x), "RWM": lambda x: fmt(x, 3), "SPY RWM": lambda x: fmt(x, 3)})

    css = """
:root{--navy:#08296b;--blue:#0868d7;--cyan:#0bb9df;--ice:#eef7ff;--ink:#10213d;--muted:#62728a;--line:#dce8f4;--good:#0a9b71;--bad:#d84b5b;--amber:#d89014;--paper:#fff;color-scheme:light only}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font:15px/1.58 Inter,Segoe UI,Arial,sans-serif;color:var(--ink);background:#f3f7fb}header.qinvia-cover{width:min(1132px,calc(100% - 48px));margin:28px auto 0;padding:42px 30px 46px;background:linear-gradient(120deg,#f8fbff 0%,#eef6ff 55%,#e7faff 100%);border:1px solid #e3eaf3;border-radius:18px;box-shadow:0 18px 50px rgba(8,41,107,.09);position:relative;overflow:hidden}.qinvia-cover:after{content:'';position:absolute;right:-80px;bottom:-130px;width:360px;height:360px;border-radius:50%;background:radial-gradient(circle,rgba(11,185,223,.18),rgba(8,104,215,0) 68%);pointer-events:none}.qinvia-cover>a{display:inline-block;position:relative;z-index:1}.qinvia-logo{display:block;width:min(590px,78%);height:auto;margin:0 0 30px}.qinvia-eyebrow{position:relative;z-index:1;font-weight:800;letter-spacing:.16em;color:#0b72c9;font-size:.78rem}.qinvia-cover h1{position:relative;z-index:1;font-size:clamp(38px,5vw,58px);line-height:1.06;margin:.6rem 0 .7rem;color:var(--navy);max-width:980px;letter-spacing:-.035em}.qinvia-subtitle{position:relative;z-index:1;font-size:1.18rem;color:#3b587d;margin:0 0 1.4rem;max-width:980px}.qinvia-meta{position:relative;z-index:1;display:flex;gap:9px;flex-wrap:wrap}.qinvia-meta span{background:#fff;border:1px solid #d7e5f6;border-radius:999px;padding:5px 11px;font-size:.79rem;color:#31557d}.decision{position:relative;z-index:1;display:inline-flex;border-radius:10px;padding:10px 14px;margin-top:17px;font-size:.78rem;font-weight:850;letter-spacing:.04em;background:#fff4f5;color:#982f3d;border:1px solid #efc2c8;border-left:5px solid var(--bad)}nav{position:sticky;top:0;z-index:5;background:#ffffffed;backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:10px 0;overflow:auto;white-space:nowrap}.nav-inner{width:min(1132px,calc(100% - 48px));margin:0 auto;padding:0 30px}nav a{color:#23466d;text-decoration:none;font-weight:750;margin-right:20px;font-size:13px}main{width:min(1132px,calc(100% - 48px));margin:0 auto;padding:34px 0 70px}section{background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:30px;margin:0 0 24px;box-shadow:0 12px 34px #163b6410}h2{font-size:29px;margin:0 0 8px;letter-spacing:-.025em}h3{margin:23px 0 8px;color:#163d6b}.lede{color:var(--muted);font-size:16px;max-width:960px}.chapter{display:flex;gap:12px;align-items:center;color:#075cae;text-transform:uppercase;letter-spacing:.1em;font-size:12px;font-weight:900;margin-bottom:8px}.chapter b{display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#075cae;color:white}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:24px}.kpi{border-radius:14px;padding:18px;background:linear-gradient(145deg,#f8fbff,#eaf4ff);border:1px solid #d8eafa}.kpi b{display:block;font-size:29px;line-height:1.05}.kpi span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{border:1px solid var(--line);border-radius:14px;padding:20px;background:#fbfdff}.callout{border-left:4px solid var(--blue);background:var(--ice);padding:16px 18px;border-radius:4px 12px 12px 4px;margin:18px 0}.callout.red{border-color:var(--bad);background:#fff4f5}.callout.amber{border-color:var(--amber);background:#fff9ec}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px}table{width:100%;border-collapse:collapse;font-size:13px}th{background:#edf5fd;color:#27496f;text-align:left;padding:11px;white-space:nowrap}td{padding:10px 11px;border-top:1px solid var(--line);vertical-align:top}tr:hover td{background:#f7fbff}.figure-wrap{margin:22px 0;border:1px solid var(--line);border-radius:15px;padding:16px;background:#fff;overflow:hidden}.figure-wrap img{display:block;width:100%;height:auto}.figure-caption{margin:9px 4px 0;color:var(--muted);font-size:12px}.formula{font:17px/1.5 Cambria Math,Georgia,serif;text-align:center;background:#f6faff;border:1px solid #dbe8f6;border-radius:11px;padding:13px 16px;margin:15px 0;color:#123d73;overflow:auto}.pill{display:inline-block;border-radius:999px;padding:5px 9px;background:#eaf4ff;color:#075cae;font-weight:700;font-size:12px;margin:3px}.small{font-size:13px;color:var(--muted)}details{border:1px solid var(--line);border-radius:12px;margin-top:18px;background:#fbfdff}summary{cursor:pointer;padding:14px 17px;font-weight:800;color:#174d86}details>*:not(summary){margin-left:17px;margin-right:17px}code{background:#eff4f8;padding:2px 5px;border-radius:5px}footer{color:#708198;text-align:center;padding:20px}@media(max-width:850px){header.qinvia-cover,main{width:calc(100% - 32px)}header.qinvia-cover{margin:16px auto 0;border-radius:14px;padding:32px 24px 38px}.nav-inner{width:calc(100% - 32px);padding:0 24px}section{padding:24px}.kpis,.grid2,.grid3{grid-template-columns:1fr 1fr}}@media(max-width:560px){header.qinvia-cover,main{width:calc(100% - 20px)}.kpis,.grid2,.grid3{grid-template-columns:1fr}section{padding:20px}}@media print{nav{display:none}body{background:white}header.qinvia-cover,main{width:100%}header.qinvia-cover{margin:0;box-shadow:none}section{box-shadow:none;break-inside:avoid}}
"""

    html = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qinvia · Universo ETF · Estudio 1A</title><link rel="icon" href="{icon}"><style>{css}</style></head><body>
<header class="qinvia-cover"><a href="https://qinvia.com" target="_blank" rel="noopener noreferrer"><img src="{logo}" class="qinvia-logo" alt="Qinvia"></a><div class="qinvia-eyebrow">RESEARCH NOTEBOOK · UNIVERSO ETF</div><h1>Universo ETF · Exposición, habilidad y el listón de SPY</h1><p class="qinvia-subtitle">Un análisis escalonado del universo gratuito: primero describimos; después distinguimos exposición de gestión; por último exigimos que el resultado conserve calidad frente a cash y frente al coste de oportunidad de SPY.</p><div class="qinvia-meta"><span>Estudio 1A</span><span>Yahoo Adj Close</span><span>Corte 01/03/2022</span><span>{nfmt(cohort)} productos</span><span>Carlos Barredo Lago</span><span>{generated}</span></div><div class="decision">SOLO {rwm_n} DE {nfmt(cohort)} PRODUCTOS SUPERAN EL RWM DE SPY; {managed_evidence_rwm_n} SON GESTIÓN INTENCIONAL</div></header>
<nav><div class="nav-inner"><a href="#tesis">Tesis</a><a href="#universo">Universo</a><a href="#exposicion">Exposición</a><a href="#gestion">Gestión</a><a href="#candidatos">Candidatos</a><a href="#apalancamiento">Apalancamiento</a><a href="#igualacion">Retorno igualado</a><a href="#robustez">Robustez</a><a href="#qinvia">Ratios Qinvia</a><a href="#curva">Curva media</a><a href="#veredicto">Veredicto</a></div></nav><main>

<section id="tesis"><div class="chapter"><b>1</b> Tesis ejecutiva</div><h2>La abundancia de producto no equivale a abundancia de habilidad</h2><p class="lede">Las métricas tradicionales se conservan para describir los {nfmt(cohort)} ETF maduros. Para decidir quién presenta una trayectoria superior a SPY evitamos una votación entre ratios: RWM es el criterio principal y CAGR aporta contexto económico. {rwm_n} productos ({pct(rwm_n/cohort)}) superan el RWM de SPY sobre su misma ventana; {cagr_rwm_n} ({pct(cagr_rwm_n/cohort)}) superan además su CAGR.</p><div class="callout"><strong>Qué mide RWM:</strong> Relative-Wealth Martin calcula el ratio de Martin íntegramente sobre la riqueza del ETF relativa a cash. Relaciona el crecimiento anualizado de esa ventaja con el Ulcer Index de la misma curva: premia ganar terreno frente a cash y penaliza la profundidad y persistencia con que se pierde. Aquí lo usamos para condensar crecimiento y daño relativo en una sola lectura, no para convertir este informe en un tratado sobre la métrica. <a href="https://qinvia.com/es/research/relative-wealth-martin" target="_blank" rel="noopener noreferrer">Más información sobre RWM en Qinvia Research ↗</a></div><div class="kpis"><div class="kpi"><b>{rwm_n}</b><span>superan RWM · {pct(rwm_n/cohort)}</span></div><div class="kpi"><b>{cagr_rwm_n}</b><span>superan también CAGR</span></div><div class="kpi"><b>{clear_beta_rwm_n}</b><span>exposición beta identificable</span></div><div class="kpi"><b>{managed_evidence_rwm_n}</b><span>gestión intencional</span></div></div><div class="callout red"><strong>Conclusión adelantada:</strong> que un índice de semiconductores, oro o tecnología gane durante la ventana identifica una exposición premiada; no demuestra selección, timing ni control de riesgo por parte de un gestor. La escala comercial, la complejidad o la marca tampoco son evidencia de alfa.</div><h3>Radiografía inicial, métrica a métrica</h3>{headline_html}<div class="figure-wrap"><img src="{pass_plot}" alt="Tasas de superación"><p class="figure-caption">CAGR, Sortino, Calmar y Martin permanecen como descripción. A partir de aquí, la comparación decisiva usa RWM; CAGR se muestra como segunda coordenada, no como un jurado adicional.</p></div></section>

<section id="universo"><div class="chapter"><b>2</b> Universo y método</div><h2>Una comparación exigente, reproducible y consciente de sus límites</h2><p class="lede">El catálogo bruto conserva 9.550 identidades, incluidas históricas. Se apartan exposiciones inversas o apalancadas, volatilidad, payoffs estructurados y vehículos sin negociación comprobable; los registros no se destruyen. La muestra analítica exige inicio Yahoo utilizable en o antes del 1 de marzo de 2022 y al menos 1.008 retornos diarios.</p><div class="grid2"><div class="card"><h3>Misma ventana y total return</h3><p>Cada ETF se alinea con SPY desde su primera sesión utilizable hasta su propia última sesión. Yahoo <code>Adj Close</code> actúa como proxy de rentabilidad total y evita comparar periodos distintos.</p></div><div class="card"><h3>SPY como coste de oportunidad</h3><p>La pregunta es deliberadamente dura: “¿habría sido mejor mantener SPY?”. No afirmamos que SPY sea el benchmark natural de bonos, oro o market neutral; lo usamos como listón del inversor que busca crecimiento.</p></div></div><div class="callout"><strong>Criterio operativo:</strong> las tablas conservan CAGR, Sortino, Calmar y Martin para que la radiografía sea completa. Las conclusiones de superioridad usan Relative-Wealth Martin (RWM) frente al RWM de SPY sobre sesiones idénticas, porque reúne crecimiento sobre cash y daño de la riqueza relativa en una sola lectura; CAGR queda al lado para distinguir eficiencia de crecimiento absoluto. La discusión formal de RWM pertenece a un estudio específico, no a este informe.</div><div class="figure-wrap"><img src="{funnel_plot}" alt="Embudo del universo"><p class="figure-caption">Las unidades cambian de identidad SEC a símbolo Yahoo y después a producto económico. Los cambios de ticker se consolidan para no duplicar productos.</p></div><div class="callout amber"><strong>Survivorship bias aún material:</strong> {nfmt(summary['current_listing_count'])} de {nfmt(cohort)} productos figuran como actuales y solo {nfmt(summary['historical_identity_count'])} ({pct(summary['historical_identity_count']/cohort)}) como no actuales. Además, las 67 series no actuales llegan al menos hasta el 17/07/2026: no forman una muestra representativa de ETF muertos. El catálogo conserva identidades históricas, pero la cohorte de precios gratuita no permite afirmar una reducción material del sesgo de supervivencia.</div><h3>Motivos principales de exclusión</h3>{exclusions_html}<div class="callout"><strong>Corte de madurez:</strong> el 01/03/2022 obliga a cada producto a atravesar, como mínimo, la crisis inflacionaria seleccionada y aproximadamente cuatro años y medio de mercado hasta el cierre de datos. CGDV y CGXU entran: la primera sesión Yahoo de ambos es 24/02/2022.</div><div class="figure-wrap"><img src="{inception_plot}" alt="Distribución de incepción"><p class="figure-caption">El corte no iguala edades. Cada ETF sigue midiéndose desde su propia incepción; la robustez temporal se examina después.</p></div><details><summary>Identidades, alias y clasificación pendiente</summary><p>{nfmt(qualifying_n)} series pasan el filtro inicial. Cinco son tickers anteriores del mismo producto y se consolidan, quedando {nfmt(cohort)} productos económicos.</p>{aliases_html}<h3>Clase principal aún no resuelta</h3>{unresolved_html}</details><div class="formula">CAGR = (V<sub>T</sub>/V<sub>0</sub>)<sup>1/años</sup> − 1 &nbsp;·&nbsp; Sortino = media(r)/desviación bajista × √252</div><div class="formula">Calmar = CAGR/|MaxDD| &nbsp;·&nbsp; Martin = CAGR/Ulcer Index</div></section>

<section id="exposicion"><div class="chapter"><b>3</b> Exposición no es habilidad</div><h2>Antes de atribuir mérito, identificamos qué riesgo se compró</h2><p class="lede">La clasificación separa gestión intencional de beta de mercado amplia, beta concentrada, reglas sistemáticas estáticas, renta fija y otras exposiciones. El objetivo no es desmerecer la indexación: es impedir que el buen resultado de un sector o activo se presente como evidencia de gestión superior.</p><div class="figure-wrap"><img src="{provenance_plot}" alt="Procedencia de los ganadores"><p class="figure-caption">Procedencia de quienes superan RWM y de quienes, además, superan CAGR. “No resuelto” se mantiene explícito: no se fuerza a pasivo ni a activo.</p></div><div class="grid3"><div class="card"><h3>Beta amplia</h3><p>Una exposición diversificada puede ser una solución excelente y barata. Su éxito, sin embargo, pertenece al mercado capturado, no a una decisión repetida del gestor.</p></div><div class="card"><h3>Beta concentrada</h3><p>Sectores, temas, países, metales o estilos estrechan la cartera y aumentan la dependencia del régimen. Ganar ex post puede reflejar una prima o una época extraordinaria.</p></div><div class="card"><h3>Reglas sistemáticas</h3><p>Un índice alternativo puede incorporar una idea válida. Para hablar de habilidad hay que comprobar que la regla añade valor de forma robusta, no solo que su backtest escogió una exposición ganadora.</p></div></div><div class="callout amber"><strong>Ejemplo útil:</strong> QQQ supera el CAGR de SPY desde 1999 ({pct(qqq.cagr)} frente a {pct(qqq.spy_cagr)}), pero no su RWM ({fmt(qqq.rwm_score,3)} frente a {fmt(qqq.spy_rwm_score,3)}). Un índice estrecho puede haber capturado un régimen extraordinario sin ofrecer una trayectoria relativa superior bajo el criterio elegido.</div></section>

<section id="gestion"><div class="chapter"><b>4</b> La prueba central</div><h2>¿Qué ocurre cuando exigimos que el producto haga algo?</h2><p class="lede">Usamos dos capas para no confundir intención con habilidad: {managed_strict_active_n} productos con gestión activa identificada y un anillo ampliado de {managed_dynamic_inferred_n} estrategias dinámicas o alternativas cuya etiqueta activa no está confirmada. El bloque ampliado suma {managed_n}; la exposición económica sigue siendo un eje separado.</p><div class="figure-wrap"><img src="{managed_plot}" alt="Marcador de gestión activa y dinámica"><p class="figure-caption">Resultados del bloque ampliado activo/dinámico: CAGR como contexto, RWM como criterio y la intersección como lectura más exigente.</p></div><div class="kpis"><div class="kpi"><b>{managed_rwm_n}</b><span>superan RWM · {pct(managed_rwm_n/managed_n)}</span></div><div class="kpi"><b>{managed_cagr_rwm_n}</b><span>superan RWM + CAGR</span></div><div class="kpi"><b>{active_rwm}</b><span>activos identificados con RWM</span></div><div class="kpi"><b>{managed_rwm_n-active_rwm}</b><span>dinámicos inferidos con RWM</span></div></div><div class="figure-wrap"><img src="{management_base_rate_plot}" alt="Tasas base por estilo de gestión"><p class="figure-caption">Proporciones observadas e intervalos Wilson del 95%. El solapamiento recuerda que una etiqueta de gestión no es evidencia causal de valor añadido.</p></div><div class="callout red"><strong>El listón sigue alto:</strong> {active_rwm} de {active_n} productos activos identificados ({pct(active_rwm/active_n)}) superan el RWM de SPY; {active_cagr_rwm} superan también su CAGR. En el anillo ampliado, el total asciende a {managed_rwm_n} de {managed_n}. Existe proceso identificado; eso no demuestra que el proceso haya causado el resultado.</div><h3>Los {managed_rwm_n} casos que superan el RWM de SPY</h3>{managed_winner_html}</section>

<section id="candidatos"><div class="chapter"><b>5</b> Rebajamos el listón sin regalar el resultado</div><h2>Seis candidatos muestran mejor RWM, pero aún no alcanzan el retorno de SPY</h2><p class="lede">Seleccionamos {risk_candidate_n} productos del bloque activo/dinámico que no superan el CAGR de SPY pero sí su RWM: {risk_active_n} tienen gestión activa identificada y {risk_dynamic_inferred_n} son estrategias dinámicas inferidas. Son el lugar correcto para preguntar si una trayectoria relativa más eficiente puede convertirse en una alternativa competitiva mediante apalancamiento moderado.</p><div class="grid2"><div class="card"><h3>Por qué entran</h3><p>RWM reconoce crecimiento sobre cash y penaliza los periodos en que la riqueza relativa permanece bajo máximos. Aquí permite identificar trayectorias útiles sin confundirlas todavía con ganadores absolutos.</p></div><div class="card"><h3>Qué no concedemos</h3><p>No declaramos ganador a quien solo presenta mejor RWM. Exigimos igualar el capital final de SPY después de financiar la deuda y comprobamos si la ventaja RWM sobrevive.</p></div></div><details open><summary>Los {risk_candidate_n} candidatos de eficiencia relativa</summary>{risk_html}</details></section>

<section id="apalancamiento"><div class="chapter"><b>6</b> Escalera de apalancamiento</div><h2>El apalancamiento puede elevar CAGR; no fabrica habilidad</h2><p class="lede">Se compra la exposición al inicio con una deuda fija y se deja evolucionar. No hay rebalanceo diario ni rotación ficticia: el apalancamiento deriva con el mercado. La deuda acumula el Effective Federal Funds Rate diario más un margen base del 1,50%, con convención Actual/360.</p><div class="formula">Capital<sub>t</sub> = L × ETF<sub>t</sub> − (L−1) × Deuda<sub>t</sub></div><div class="figure-wrap"><img src="{leverage_plot}" alt="Escalera de apalancamiento"><p class="figure-caption">Los recuentos corresponden a los {risk_candidate_n} candidatos. El apalancamiento se fija al inicio; no se persigue una exposición constante.</p></div>{leverage_html}<div class="callout"><strong>Lectura:</strong> a 1,25×, cuatro productos ya superan el CAGR de SPY, cinco conservan RWM y tres logran ambas cosas. A 2,00×, cinco alcanzan el CAGR, pero solo tres mantienen RWM y dos conservan ambos criterios. El apalancamiento no crea habilidad: intercambia margen de trayectoria por crecimiento.</div><p class="small">La estructura de financiación es un escenario histórico “estilo IBKR”, no una reconstrucción exacta de todas sus tarifas pasadas. IBKR publica tipos como benchmark más margen, cálculo diario y, para USD, base Actual/360. Fuentes oficiales: <a href="https://www.interactivebrokers.com/en/trading/margin-rates.php" target="_blank" rel="noopener noreferrer">tipos de margen</a>, <a href="https://www.interactivebrokers.com/en/trading/margin-calculation-details.php" target="_blank" rel="noopener noreferrer">método de cálculo</a> y <a href="https://fred.stlouisfed.org/series/DFF" target="_blank" rel="noopener noreferrer">Effective Federal Funds Rate (FRED)</a>.</p></section>

<section id="igualacion"><div class="chapter"><b>7</b> Igualación exacta de retorno</div><h2>Mismo capital final, caminos muy distintos</h2><p class="lede">Resolvemos ex post el apalancamiento inicial exacto necesario para terminar con el mismo capital que SPY. Es un diagnóstico —no una regla invertible— y se limita a 2,00×. {feasible_match_n} de {risk_candidate_n} candidatos pueden alcanzar el objetivo; {feasible_rwm_n} conservan un RWM superior después de pagar la financiación.</p><h3>La calidad relativa se decide durante el recorrido</h3><div class="figure-wrap"><img src="{return_matched_equity_plot}" alt="Curvas de equity con retorno igualado"><p class="figure-caption">Cada panel comienza en 100 en la incepción del ETF. La línea apalancada incorpora la financiación histórica y termina por construcción junto a SPY; la diferencia relevante está en la riqueza relativa durante el recorrido.</p></div><div class="figure-wrap"><img src="{return_match_plot}" alt="Retorno igualado y sensibilidad"><p class="figure-caption">Panel izquierdo: RWM después de igualar el retorno. Panel derecho: sensibilidad al margen de financiación sobre Fed Funds.</p></div><div class="kpis"><div class="kpi"><b>{feasible_match_n}</b><span>alcanzan SPY con ≤ 2×</span></div><div class="kpi"><b>{feasible_rwm_n}</b><span>conservan RWM superior</span></div><div class="kpi"><b>1,50%</b><span>margen base sobre DFF</span></div><div class="kpi"><b>2,00×</b><span>límite diagnóstico</span></div></div><h3>Resultado por producto</h3>{matched_html}<h3>Sensibilidad al coste de financiación</h3>{sensitivity_html}<div class="callout red"><strong>Resultado central:</strong> DFAU, DUHP, JAVA y TEQI igualan el capital final con menos de 2× y conservan un RWM superior. HEQT alcanza el retorno pero pierde la ventaja RWM; SIXH requeriría más de 2×. La conclusión se deteriora a medida que aumenta el coste de la deuda.</div><p class="small">El umbral de mantenimiento del 25% es ilustrativo; las exigencias reales dependen del broker, la cartera y el producto. La igualación usa información ex post y no debe interpretarse como una estrategia ejecutable.</p></section>

<section id="robustez"><div class="chapter"><b>8</b> Estabilidad al punto de entrada</div><h2>Ganar desde la incepción no basta</h2><p class="lede">Los {managed_rwm_n} ganadores RWM del bloque gestionado se vuelven a comparar con SPY desde distintos meses de entrada, usando ventanas móviles de aproximadamente tres años. {robust_managed_n} superan el RWM de SPY en la mayoría de los puntos de entrada. Como las ventanas se solapan, esta es una prueba de sensibilidad temporal, no una estimación independiente de persistencia.</p><div class="figure-wrap"><img src="{rolling_plot}" alt="Estabilidad a distintos puntos de entrada"><p class="figure-caption">Fracción y porcentaje de meses de entrada cuya ventana posterior de 756 sesiones supera el RWM de SPY; CAGR se conserva en la tabla como contexto.</p></div>{rolling_html}<div class="callout amber"><strong>Separación importante:</strong> CGDV, CGUS, TSPA, CLSE, DFIV, SIXH y THRO superan RWM desde al menos la mitad de los meses de entrada. Los demás dependen mucho más del punto de inicio elegido. La precisión aparente de los porcentajes no debe confundirse con muestras independientes.</div></section>

<section id="qinvia"><div class="chapter"><b>9</b> Síntesis y contraste</div><h2>Una decisión clara y un descriptor complementario</h2><p class="lede">RWM ordena la decisión frente a SPY; CAGR mantiene visible la magnitud económica. DBF± no decide ganadores en este estudio: describe si la dirección neta de los retornos está sostenida por breadth.</p><div class="figure-wrap"><img src="{scatter_plot}" alt="CAGR frente a RWM"><p class="figure-caption">Los {rwm_n} puntos por encima de cero en RWM superan a SPY bajo el criterio principal; {cagr_rwm_n} quedan además a la derecha de cero en CAGR. Los límites visuales recortan extremos, pero los recuentos usan todos los datos.</p></div><div class="grid2"><div class="card"><h3>{nfmt(rwm_n)} superan RWM</h3><p>{pct(rwm_n/cohort)} del universo presenta un RWM superior al de SPY en su ventana comparable.</p></div><div class="card"><h3>{nfmt(cagr_rwm_n)} superan RWM + CAGR</h3><p>{pct(cagr_rwm_n/cohort)} mantiene la ventaja relativa y también termina con mayor crecimiento anualizado.</p></div></div><h3>Quince mayores ventajas RWM</h3>{rwm_html}<div class="formula">D± = Σr<sub>t</sub> / Σ|r<sub>t</sub>| &nbsp;·&nbsp; J = (Σ|r<sub>t</sub>|)² / (N·Σr<sub>t</sub>²) &nbsp;·&nbsp; DBF± = D± × J</div><div class="callout amber"><strong>DBF es contraste, no veredicto:</strong> es invariante al orden y a la escala positiva. No observa drawdowns, severidad económica, riesgo de cola, alpha ni rentabilidad futura; por eso no se utiliza para declarar superioridad frente a SPY.</div><h3>Diez perfiles de mayor DBF±</h3>{dbf_html}</section>

<section id="curva"><div class="chapter"><b>10</b> El universo como conjunto</div><h2>SPY no solo supera la media: termina en la parte alta de la distribución</h2><p class="lede">Cada ETF se rebasa a 100 el 01/03/2022. El abanico muestra la dispersión completa del capital buy-and-hold; la segunda figura separa media, mediana y sensibilidad de cobertura. Ninguna de las dos representa una cartera rebalanceada.</p><div class="figure-wrap"><img src="{universe_fan_plot}" alt="Abanico de curvas del universo ETF"><p class="figure-caption">Bandas transversales de {nfmt(summary['curve_diagnostics']['fixed_complete_constituents'])} productos con cobertura completa. El abanico enseña simultáneamente resultado central, dispersión y extremos.</p></div><h3>La media confirma la misma historia</h3><div class="figure-wrap"><img src="{curve_plot}" alt="Curva media frente a SPY"><p class="figure-caption">La sensibilidad de cobertura completa exige al menos 98,5% de sesiones observables hasta el final.</p></div><div class="kpis"><div class="kpi"><b>{fmt(curves.spy.iloc[-1],1)}</b><span>capital final SPY</span></div><div class="kpi"><b>{fmt(curves.etf_mean_fixed_complete.iloc[-1],1)}</b><span>capital final media ETF</span></div><div class="kpi"><b>{pct(spy_curve['cagr'])}</b><span>CAGR SPY</span></div><div class="kpi"><b>{pct(average_curve['cagr'])}</b><span>CAGR media ETF</span></div></div><div class="callout"><strong>Resultado descriptivo:</strong> la curva media no es una cartera operable ni rebalanceada. Solo resume dónde termina el universo y cuánta dispersión hubo alrededor de ese resultado.</div></section>

<section id="veredicto"><div class="chapter"><b>11</b> Veredicto Qinvia</div><h2>SPY representa un listón más alto de lo que su simplicidad aparente sugiere</h2><div class="grid2"><div class="card"><h3>Lo que sí muestra la evidencia</h3><ul><li>Solo {pct(rwm_n/cohort)} del universo supera el RWM de SPY.</li><li>Solo {pct(cagr_rwm_n/cohort)} supera simultáneamente RWM y CAGR.</li><li>La mayor parte de los ganadores atribuibles refleja exposición beta, no gestión demostrada.</li><li>{managed_rwm_n} de {managed_n} productos con gestión intencional superan RWM; {robust_managed_n} lo hacen desde la mayoría de puntos de entrada.</li><li>Al igualar retorno y cobrar financiación, {feasible_rwm_n} de {feasible_match_n} casos alcanzables conservan RWM.</li></ul></div><div class="card"><h3>Por qué el listón es estructuralmente alto</h3><ul><li>El S&amp;P 500 ya diversifica cientos de negocios rentables y líquidos.</li><li>La ponderación por capitalización deja crecer a los ganadores y reduce mecánicamente el peso de los perdedores.</li><li>Su composición se renueva; no es una cartera estática de empresas de 1957.</li><li>SPY empaqueta esa exposición con gran liquidez, bajo coste y escasa fricción operativa.</li><li>Por eso un producto más complejo carga con la prueba de demostrar qué mejora y si esa mejora persiste.</li></ul></div></div><div class="callout amber"><strong>Capacidad, escala y paradoja del éxito — hipótesis, no hallazgo causal:</strong><p>Una explicación compatible con la literatura es que el alfa tenga capacidad finita. Los buenos resultados atraen activos gestionados; desplegar posiciones mayores sobre un conjunto limitado de oportunidades puede elevar el impacto de mercado, los costes, las restricciones de liquidez y la competencia, erosionando la ventaja que originó los flujos. <a href="https://doi.org/10.1086/424739" target="_blank" rel="noopener noreferrer">Berk y Green (2004)</a> formalizan este equilibrio; <a href="https://doi.org/10.1257/0002828043052277" target="_blank" rel="noopener noreferrer">Chen et al. (2004)</a> encuentran una relación más adversa en fondos expuestos a acciones pequeñas e ilíquidas, y <a href="https://www.nber.org/system/files/working_papers/w19891/w19891.pdf" target="_blank" rel="noopener noreferrer">Pástor, Stambaugh y Taylor</a> hallan evidencia fuerte de rendimientos decrecientes a escala de la industria, pero menos concluyente al nivel de cada fondo.</p><p>El contrapunto importa: con operaciones institucionales reales, <a href="https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini%2C%20Israel%20and%20Moskowitz.pdf" target="_blank" rel="noopener noreferrer">Frazzini, Israel y Moskowitz</a> estiman una capacidad muy superior a la supuesta previamente para ciertas estrategias y muestran que una ejecución diseñada para reducir costes puede ampliarla sustancialmente. La capacidad depende del turnover, el horizonte, la liquidez, la amplitud del mercado y la ejecución. Nuestros datos ETF no identifican causalmente el efecto de los flujos ni estiman la capacidad de cada proceso; por tanto, presentamos este mecanismo como explicación plausible, no como conclusión demostrada.</p></div><div class="callout red"><strong>Conclusión:</strong> la industria ofrece miles de narrativas, envoltorios y exposiciones; la evidencia de valor añadido por gestión es mucho más escasa. El resultado no demuestra que la industria sea una estafa ni que toda exposición estrecha sea inútil. Sí demuestra que complejidad, marca y activos gestionados no bastan: frente a un índice amplio, barato y autoactualizable, la carga de la prueba es extraordinariamente alta.</div><h3>Control de calidad y límites de la fuente gratuita</h3><p>Se validaron 5.505 Parquet sin fallos de integridad. El catálogo conserva identidades históricas, pero las 67 series no actuales llegan hasta fechas recientes y no representan liquidaciones distribuidas a lo largo del tiempo. El survivorship bias sigue siendo una limitación material. RWM utiliza DFF como cash institucional idealizado —acumulación diaria, sin spread y Actual/360—; no representa una rentabilidad minorista garantizada. La taxonomía usa evidencia auditable y deja explícito lo que no puede resolver.</p><p class="small">Generado {generated}. Fuente principal: Yahoo Finance gratuita · Adj Close diario · fechas exactas comunes con SPY. Cash: FRED DFF.</p></section>
</main><footer>Qinvia · Carlos Barredo Lago</footer></body></html>'''

    html_path = output_root / f"{REPORT_BASENAME}.html"
    html_path.write_text(html, encoding="utf-8")

    notebook = nbformat.v4.new_notebook()
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "qinvia": {"report_version": "1A", "generated_at": generated, "study": "Universo ETF", "language": "es", "artifact_type": "narrative_companion"},
    }
    notebook.cells = [
        nbformat.v4.new_markdown_cell(f'''<style>{css}</style><div class="qinvia-cover"><a href="https://qinvia.com" target="_blank"><img src="{notebook_logo}" class="qinvia-logo" alt="Qinvia"></a><div class="qinvia-eyebrow">NOTEBOOK NARRATIVO · UNIVERSO ETF</div><h1>Universo ETF · Exposición, habilidad y el listón de SPY</h1><p class="qinvia-subtitle">Quién presenta una trayectoria superior, por qué y qué queda cuando igualamos retorno y cobramos la financiación.</p><div class="qinvia-meta"><span>Estudio 1A</span><span>Corte 01/03/2022</span><span>{nfmt(cohort)} productos</span><span>{generated}</span></div></div>'''),
        nbformat.v4.new_markdown_cell("Este notebook es el acompañante narrativo y autocontenido del informe HTML. Los cálculos se ejecutan en los módulos del proyecto y los datos congelados se incluyen en `data/`; la última celda permite comprobar las cifras principales."),
        nbformat.v4.new_markdown_cell(f"## 1. Tesis ejecutiva\n\nLas métricas tradicionales se conservan como radiografía. Para decidir quién presenta una trayectoria superior a SPY usamos **RWM como criterio principal** y **CAGR como contexto económico**: **{rwm_n} de {nfmt(cohort)} ({pct(rwm_n/cohort)})** superan el RWM de SPY y **{cagr_rwm_n} ({pct(cagr_rwm_n/cohort)})** superan además su CAGR. De los ganadores RWM, **{clear_beta_rwm_n}** responden a exposición beta identificable y **{managed_evidence_rwm_n}** a gestión intencional.\n\n**Qué mide RWM.** Relative-Wealth Martin calcula el ratio de Martin íntegramente sobre la riqueza del ETF relativa a cash. Relaciona el crecimiento anualizado de esa ventaja con el Ulcer Index de la misma curva: premia ganar terreno frente a cash y penaliza la profundidad y persistencia con que se pierde. Aquí lo usamos para condensar crecimiento y daño relativo en una sola lectura. [Más información sobre RWM en Qinvia Research](https://qinvia.com/es/research/relative-wealth-martin).\n\n" + markdown_table(headline)),
        nbformat.v4.new_markdown_cell(f"## 2. Universo y listón de comparación\n\n<img src=\"{funnel_plot}\" style=\"width:100%\">\n\n- Yahoo Adj Close como proxy de rentabilidad total.\n- SPY alineado a las sesiones exactas de cada ETF.\n- CAGR, Sortino, Calmar, Martin y RWM se conservan en las tablas descriptivas.\n- Las conclusiones frente a SPY usan **Relative-Wealth Martin (RWM)**; CAGR queda como segunda coordenada.\n- Cash: FRED DFF, acumulación diaria sin spread, Actual/360.\n- Primera sesión Yahoo ≤ 01/03/2022 y al menos 1.008 retornos.\n- SPY es el coste de oportunidad del inversor, no el benchmark natural de todas las clases.\n- **Survivorship bias material:** {nfmt(summary['current_listing_count'])} productos actuales y solo {nfmt(summary['historical_identity_count'])} no actuales; no representan una muestra histórica de fondos muertos.\n\n<img src=\"{inception_plot}\" style=\"width:100%\">"),
        nbformat.v4.new_markdown_cell(f"## 3. Exposición no es habilidad\n\n<img src=\"{provenance_plot}\" style=\"width:100%\">\n\nUn sector, tema, país, metal o regla sistemática puede ser una exposición excelente. Que gane ex post demuestra que ese riesgo fue premiado durante la ventana; no demuestra por sí solo selección, timing o control de riesgo del gestor."),
        nbformat.v4.new_markdown_cell(f"## 4. Gestión activa y dinámica\n\nEl núcleo contiene **{managed_strict_active_n}** productos con gestión activa identificada; se añaden **{managed_dynamic_inferred_n}** alternativas dinámicas no confirmadas como activas. De los **{managed_n}** del bloque ampliado, **{managed_rwm_n}** superan RWM y **{managed_cagr_rwm_n}** superan RWM + CAGR. La intención de gestionar se identifica; la habilidad no se presume.\n\n<img src=\"{managed_plot}\" style=\"width:100%\">\n\n<img src=\"{management_base_rate_plot}\" style=\"width:100%\">\n\n" + markdown_table(managed_winner_table)),
        nbformat.v4.new_markdown_cell(f"## 5. Candidatos de eficiencia relativa\n\nHay **{risk_candidate_n}** productos del bloque activo/dinámico que superan RWM pero no CAGR: **{risk_active_n}** activos identificados y **{risk_dynamic_inferred_n}** dinámicos inferidos. Son los candidatos a apalancamiento moderado.\n\n" + markdown_table(risk_table)),
        nbformat.v4.new_markdown_cell(f"## 6. Escalera de apalancamiento\n\nSe fija una deuda al inicio y no se rebalancea. La financiación acumula el Effective Federal Funds Rate diario + 1,50%, con Actual/360. No hay rotación ficticia.\n\n<img src=\"{leverage_plot}\" style=\"width:100%\">\n\n" + markdown_table(leverage_table)),
        nbformat.v4.new_markdown_cell(f"## 7. Retorno igualado y coste de financiación\n\n**{feasible_match_n}** candidatos alcanzan el capital final de SPY con ≤ 2× y **{feasible_rwm_n}** conservan un RWM superior después de financiar la deuda. La solución es ex post y diagnóstica, no una regla ejecutable.\n\n### Caminos distintos hacia el mismo capital final\n\n<img src=\"{return_matched_equity_plot}\" style=\"width:100%\">\n\n<img src=\"{return_match_plot}\" style=\"width:100%\">\n\n" + markdown_table(matched_table) + "\n\n### Sensibilidad al margen de financiación\n\n" + markdown_table(sensitivity_table)),
        nbformat.v4.new_markdown_cell(f"## 8. Estabilidad al punto de entrada\n\nDe los {managed_rwm_n} ganadores RWM del bloque gestionado, **{robust_managed_n}** superan el RWM de SPY desde la mayoría de los meses de entrada. Las ventanas de tres años se solapan: es una sensibilidad temporal, no una prueba independiente de persistencia.\n\n<img src=\"{rolling_plot}\" style=\"width:100%\">\n\n" + markdown_table(rolling_table)),
        nbformat.v4.new_markdown_cell(f"## 9. Síntesis RWM y contraste DBF\n\n<img src=\"{scatter_plot}\" style=\"width:100%\">\n\nRWM decide la comparación con SPY; CAGR mantiene visible la magnitud económica. **{rwm_n} ({pct(rwm_n/cohort)})** productos superan RWM y **{cagr_rwm_n} ({pct(cagr_rwm_n/cohort)})** superan RWM + CAGR. DBF± permanece como descriptor de dirección y breadth; no decide ganadores.\n\n### Mayores ventajas RWM\n\n" + markdown_table(rwm_table, 15) + "\n\n### Mayores perfiles DBF±\n\n" + markdown_table(dbf_table, 10)),
        nbformat.v4.new_markdown_cell(f"## 10. Curva común desde el corte\n\n<img src=\"{universe_fan_plot}\" style=\"width:100%\">\n\nEl abanico muestra los percentiles 10–90 y 25–75 de {nfmt(summary['curve_diagnostics']['fixed_complete_constituents'])} productos con cobertura completa.\n\n<img src=\"{curve_plot}\" style=\"width:100%\">\n\nMedia y mediana transversal de capital buy-and-hold. Es una descripción del universo, no una cartera rebalanceada ni una estrategia operable."),
        nbformat.v4.new_markdown_cell(f"## 11. Veredicto Qinvia\n\n- Solo {pct(rwm_n/cohort)} del universo supera el RWM de SPY.\n- Solo {pct(cagr_rwm_n/cohort)} supera RWM + CAGR.\n- La mayoría de ganadores atribuibles refleja beta, no gestión demostrada.\n- {managed_rwm_n} de {managed_n} productos con gestión intencional superan RWM; {robust_managed_n} lo hacen desde la mayoría de puntos de entrada.\n- Al igualar retorno y cobrar financiación, {feasible_rwm_n} de {feasible_match_n} casos alcanzables conservan RWM.\n\n### Capacidad, escala y paradoja del éxito\n\n**Hipótesis compatible con la literatura, no hallazgo causal.** Una explicación posible es que el alfa tenga capacidad finita: los buenos resultados atraen activos gestionados y desplegar posiciones mayores sobre un conjunto limitado de oportunidades puede elevar el impacto de mercado, los costes, las restricciones de liquidez y la competencia. [Berk y Green (2004)](https://doi.org/10.1086/424739) formalizan este equilibrio; [Chen et al. (2004)](https://doi.org/10.1257/0002828043052277) encuentran una relación más adversa en fondos expuestos a acciones pequeñas e ilíquidas, y [Pástor, Stambaugh y Taylor](https://www.nber.org/system/files/working_papers/w19891/w19891.pdf) hallan evidencia fuerte de rendimientos decrecientes a escala de la industria, pero menos concluyente al nivel de cada fondo.\n\nEl contrapunto importa: con operaciones institucionales reales, [Frazzini, Israel y Moskowitz](https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini%2C%20Israel%20and%20Moskowitz.pdf) estiman una capacidad muy superior a la supuesta previamente para ciertas estrategias y muestran que una ejecución diseñada para reducir costes puede ampliarla sustancialmente. La capacidad depende del turnover, el horizonte, la liquidez, la amplitud del mercado y la ejecución. Nuestros datos ETF no identifican causalmente el efecto de los flujos ni estiman la capacidad de cada proceso; presentamos el mecanismo como explicación plausible, no como conclusión demostrada.\n\n**Conclusión:** SPY constituye un listón estructuralmente alto: diversificación, ponderación por capitalización, renovación de componentes, liquidez y bajo coste. La industria ofrece miles de narrativas y exposiciones; la evidencia de valor añadido por gestión es mucho más escasa. Complejidad, marca y activos gestionados no sustituyen a la prueba empírica."),
        nbformat.v4.new_markdown_cell("## 12. Límites y fuentes\n\n- SPY no es el benchmark natural de todos los mandatos.\n- La taxonomía gratuita conserva los casos no resueltos.\n- El apalancamiento exacto se resuelve ex post.\n- El 25% de mantenimiento es ilustrativo.\n- La cohorte Yahoo no contiene una muestra representativa de ETF muertos; el survivorship bias sigue siendo material.\n- La siguiente prueba causal requiere un benchmark pasivo comparable por exposición para cada gestor.\n\nFuentes de financiación: [IBKR Margin Rates](https://www.interactivebrokers.com/en/trading/margin-rates.php), [IBKR Margin Calculation](https://www.interactivebrokers.com/en/trading/margin-calculation-details.php) y [FRED DFF](https://fred.stlouisfed.org/series/DFF).\n\nLa carpeta `data/` contiene la cohorte, taxonomía, resultados de apalancamiento, sensibilidad y robustez."),
        nbformat.v4.new_markdown_cell("## 13. Comprobación reproducible\n\nEsta celda opcional carga los datos congelados incluidos junto al notebook y verifica las magnitudes principales."),
        nbformat.v4.new_code_cell('''from pathlib import Path\nimport pandas as pd\n\ndata_dir = Path("data")\nselected_check = pd.read_parquet(data_dir / "selected_etfs.parquet")\nmanaged_check = pd.read_csv(data_dir / "intentional_management_products.csv")\nmatched_check = pd.read_csv(data_dir / "return_matched_leverage.csv")\ncurves_check = pd.read_parquet(data_dir / "return_matched_equity_curves.parquet")\n\n{\n    "productos": len(selected_check),\n    "superan_rwm_spy": int(selected_check.beat_spy_rwm_score.sum()),\n    "superan_rwm_y_cagr": int(selected_check.beat_spy_cagr_and_rwm.sum()),\n    "gestion_intencional_supera_rwm": int(managed_check.beat_spy_rwm_score.sum()),\n    "igualan_spy_hasta_2x": int(matched_check.feasible_at_or_below_2x.sum()),\n    "igualan_y_conservan_rwm": int((matched_check.feasible_at_or_below_2x & matched_check.matched_rwm_beats_spy.fillna(False)).sum()),\n    "curvas_retorno_igualado": int(curves_check.request_symbol.nunique()),\n}\n'''),
        nbformat.v4.new_markdown_cell("---\n\n**Qinvia · Carlos Barredo Lago**"),
    ]
    notebook_path = output_root / f"{REPORT_BASENAME}.ipynb"
    nbformat.write(notebook, notebook_path)

    set_language("en")
    headline_en = headline_table(selected, groups)
    headline_en_html = html_table(
        headline_en,
        {"Beat SPY": nfmt, "Do not beat SPY": nfmt, "% of universe": lambda x: pct(x)},
    )
    exclusions_en = english_frame(exclusions)
    exclusions_en_html = html_table(exclusions_en)
    aliases_en = english_frame(aliases)
    aliases_en_html = html_table(aliases_en)
    unresolved_en = english_frame(unresolved)
    unresolved_en_html = html_table(unresolved_en)

    managed_winner_en = english_frame(managed_winner_table)
    managed_winner_en_html = html_table(
        managed_winner_en,
        {
            "CAGR": lambda x: pct(x),
            "SPY CAGR": lambda x: pct(x),
            "RWM": lambda x: fmt(x, 3),
            "SPY RWM": lambda x: fmt(x, 3),
        },
    )
    risk_en = english_frame(risk_table)
    risk_en_html = html_table(
        risk_en,
        {
            "CAGR": lambda x: pct(x),
            "SPY CAGR": lambda x: pct(x),
            "RWM": lambda x: fmt(x, 3),
            "SPY RWM": lambda x: fmt(x, 3),
        },
    )
    leverage_en = english_frame(leverage_table)
    leverage_en_html = html_table(
        leverage_en,
        {
            "Initial leverage": lambda x: f"{fmt(x)}×",
            "Candidates": nfmt,
            "Beat CAGR": nfmt,
            "Preserve RWM": nfmt,
            "Beat both": nfmt,
        },
    )
    matched_en = english_frame(matched_table)
    matched_en_html = html_table(
        matched_en,
        {
            "Required leverage": lambda x: "Not feasible" if not np.isfinite(float(x)) else f"{fmt(x)}×",
            "Matched RWM": lambda x: fmt(x, 3),
            "SPY RWM": lambda x: fmt(x, 3),
        },
    )
    sensitivity_en = english_frame(sensitivity_table)
    sensitivity_en_html = html_table(
        sensitivity_en,
        {
            "Spread over Fed Funds": lambda x: pct(x),
            "Feasible at ≤ 2×": nfmt,
            "Preserve RWM": nfmt,
        },
    )
    rolling_en = english_frame(rolling_table)
    rolling_en_html = html_table(
        rolling_en,
        {
            "% CAGR": lambda x: pct(x),
            "% RWM": lambda x: pct(x),
            "% CAGR + RWM": lambda x: pct(x),
            "Worst Δ CAGR": lambda x: pct(x),
            "Worst Δ RWM": lambda x: fmt(x, 3),
        },
    )
    rwm_en = english_frame(rwm_table)
    rwm_en_html = html_table(
        rwm_en,
        {
            "CAGR": lambda x: pct(x),
            "SPY CAGR": lambda x: pct(x),
            "RWM": lambda x: fmt(x, 3),
            "SPY RWM": lambda x: fmt(x, 3),
            "Δ RWM": lambda x: fmt(x, 3),
        },
        limit=15,
    )
    dbf_en = english_frame(dbf_table)
    dbf_en_html = html_table(
        dbf_en,
        {
            "CAGR": lambda x: pct(x),
            "DBF±": lambda x: fmt(x, 3),
            "D±": lambda x: fmt(x, 3),
            "J": lambda x: fmt(x, 3),
        },
        limit=10,
    )

    funnel_plot_en = funnel_figure(funnel)
    pass_plot_en = pass_rate_figure(selected)
    curve_plot_en = common_curve_figure(curves, len(selected))
    universe_fan_plot_en = universe_fan_figure(curves)
    scatter_plot_en = scatter_figure(selected)
    inception_plot_en = inception_figure(selected)
    provenance_plot_en = winner_provenance_figure(evidence)
    managed_plot_en = managed_scorecard_figure(managed)
    management_base_rate_plot_en = management_base_rate_figure(groups)
    leverage_plot_en = leverage_grid_figure(leverage_summary)
    return_match_plot_en = return_match_figure(return_matched, financing_sensitivity)
    return_matched_equity_plot_en = return_matched_equity_figure(return_matched_curves)
    rolling_plot_en = rolling_robustness_figure(rolling)

    html_en = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qinvia · ETF Universe · Exposure, Skill, and Why SPY Is So Hard to Beat</title><link rel="icon" href="{icon}"><style>{css}</style></head><body>
<header class="qinvia-cover"><a href="https://qinvia.com" target="_blank" rel="noopener noreferrer"><img src="{logo}" class="qinvia-logo" alt="Qinvia"></a><div class="qinvia-eyebrow">RESEARCH NOTEBOOK · ETF UNIVERSE</div><h1>ETF Universe · Exposure, Skill, and Why SPY Is So Hard to Beat</h1><p class="qinvia-subtitle">A stepwise test of the free-data universe: describe it first, separate exposure from management next, then ask whether the result survives cash, financing and SPY as the investor's opportunity cost.</p><div class="qinvia-meta"><span>Study 1A</span><span>Yahoo Adj Close</span><span>Cutoff 1 Mar 2022</span><span>{nfmt(cohort)} products</span><span>Carlos Barredo Lago</span><span>{generated}</span></div><div class="decision">ONLY {rwm_n} OF {nfmt(cohort)} PRODUCTS BEAT SPY'S RWM; {managed_evidence_rwm_n} INVOLVE INTENTIONAL MANAGEMENT</div></header>
<nav><div class="nav-inner"><a href="#tesis">Thesis</a><a href="#universo">Universe</a><a href="#exposicion">Exposure</a><a href="#gestion">Management</a><a href="#candidatos">Candidates</a><a href="#apalancamiento">Leverage</a><a href="#igualacion">Return matching</a><a href="#robustez">Robustness</a><a href="#qinvia">Qinvia ratios</a><a href="#curva">Universe curve</a><a href="#veredicto">Verdict</a></div></nav><main>

<section id="tesis"><div class="chapter"><b>1</b> Executive thesis</div><h2>Product abundance is not skill abundance</h2><p class="lede">Traditional metrics remain in place to describe the {nfmt(cohort)} mature ETFs. To decide which products produced a superior path to SPY, we avoid a vote among ratios: RWM is the primary criterion and CAGR provides economic context. {rwm_n} products ({pct(rwm_n/cohort)}) beat SPY's RWM over the same window; {cagr_rwm_n} ({pct(cagr_rwm_n/cohort)}) also beat its CAGR.</p><div class="callout"><strong>What RWM measures:</strong> Relative-Wealth Martin calculates the Martin ratio entirely on ETF wealth relative to cash. It relates the annualised growth of that advantage to the Ulcer Index of the same curve: gaining ground versus cash is rewarded, while the depth and persistence of losing it are penalised. Here it condenses relative growth and damage into one reading; the metric itself is not the subject of this report. <a href="https://qinvia.com/research/relative-wealth-martin" target="_blank" rel="noopener noreferrer">Read more about RWM at Qinvia Research ↗</a></div><div class="kpis"><div class="kpi"><b>{rwm_n}</b><span>beat RWM · {pct(rwm_n/cohort)}</span></div><div class="kpi"><b>{cagr_rwm_n}</b><span>also beat CAGR</span></div><div class="kpi"><b>{clear_beta_rwm_n}</b><span>identifiable beta exposure</span></div><div class="kpi"><b>{managed_evidence_rwm_n}</b><span>intentional management</span></div></div><div class="callout red"><strong>The conclusion up front:</strong> a semiconductor, gold or technology index winning during the sample identifies a rewarded exposure. It does not demonstrate manager selection, timing or risk control. Commercial scale, complexity and brand recognition are not evidence of alpha either.</div><h3>The initial scorecard, metric by metric</h3>{headline_en_html}<div class="figure-wrap"><img src="{pass_plot_en}" alt="Pass rates"><p class="figure-caption">CAGR, Sortino, Calmar and Martin remain descriptive. From here on, RWM drives the comparison and CAGR is the second coordinate—not another vote.</p></div></section>

<section id="universo"><div class="chapter"><b>2</b> Universe and method</div><h2>A demanding comparison that remains reproducible—and honest about its limits</h2><p class="lede">The raw catalogue preserves 9,550 identities, including historical records. Inverse and leveraged exposures, volatility products, structured payoffs and vehicles without verified trading are set aside, not deleted. The analytical sample requires a usable Yahoo start on or before 1 March 2022 and at least 1,008 daily returns.</p><div class="grid2"><div class="card"><h3>Same window, total return</h3><p>Each ETF is aligned with SPY from its first usable session to its own final session. Yahoo <code>Adj Close</code> is used as a total-return proxy, preventing different periods from being compared as if they were equivalent.</p></div><div class="card"><h3>SPY as opportunity cost</h3><p>The question is deliberately hard: “would holding SPY have been better?”. We do not claim that SPY is the natural benchmark for bonds, gold or market-neutral mandates; it is the bar faced by a growth-seeking investor.</p></div></div><div class="callout"><strong>Operating rule:</strong> the tables retain CAGR, Sortino, Calmar and Martin for a complete diagnostic. Superiority is decided by comparing each ETF's RWM with SPY's over identical sessions; CAGR remains beside it to separate efficiency from absolute growth.</div><div class="figure-wrap"><img src="{funnel_plot_en}" alt="Universe funnel"><p class="figure-caption">The unit changes from SEC identity to Yahoo symbol and then to economic product. Ticker changes are consolidated to avoid double counting.</p></div><div class="callout amber"><strong>Survivorship bias remains material:</strong> {nfmt(summary['current_listing_count'])} of {nfmt(cohort)} products are flagged as current and only {nfmt(summary['historical_identity_count'])} ({pct(summary['historical_identity_count']/cohort)}) as non-current. Moreover, all 67 non-current series extend at least to 17 July 2026; they are not a representative history of dead ETFs. The free price cohort therefore cannot support a claim that survivorship bias has been materially removed.</div><h3>Main exclusion groups</h3>{exclusions_en_html}<div class="callout"><strong>Maturity cutoff:</strong> 1 March 2022 requires every product to have lived through at least the selected inflation shock and roughly four and a half years of market history by the data close. CGDV and CGXU qualify: both have a first Yahoo session of 24 February 2022.</div><div class="figure-wrap"><img src="{inception_plot_en}" alt="Inception distribution"><p class="figure-caption">The cutoff does not equalise age. Each ETF is still measured from its own inception; temporal robustness is examined later.</p></div><details><summary>Identities, aliases and unresolved classification</summary><p>{nfmt(qualifying_n)} series pass the initial filter. Five are former tickers for the same product and are consolidated, leaving {nfmt(cohort)} economic products.</p>{aliases_en_html}<h3>Primary class still unresolved</h3>{unresolved_en_html}</details><div class="formula">CAGR = (V<sub>T</sub>/V<sub>0</sub>)<sup>1/years</sup> − 1 &nbsp;·&nbsp; Sortino = mean(r)/downside deviation × √252</div><div class="formula">Calmar = CAGR/|MaxDD| &nbsp;·&nbsp; Martin = CAGR/Ulcer Index</div></section>

<section id="exposicion"><div class="chapter"><b>3</b> Exposure is not skill</div><h2>Before assigning credit, identify the risk that was bought</h2><p class="lede">The taxonomy separates intentional management from broad-market beta, concentrated beta, static systematic rules, fixed income and other exposures. The aim is not to diminish index investing; it is to stop a winning sector or asset from being presented as evidence of superior management.</p><div class="figure-wrap"><img src="{provenance_plot_en}" alt="Where winners come from"><p class="figure-caption">Origin of products that beat RWM and those that also beat CAGR. “Unresolved” stays explicit rather than being forced into active or passive.</p></div><div class="grid3"><div class="card"><h3>Broad beta</h3><p>A diversified exposure can be an excellent, inexpensive solution. Its success belongs to the market captured, however—not to a manager repeatedly making superior decisions.</p></div><div class="card"><h3>Concentrated beta</h3><p>Sectors, themes, countries, metals and styles narrow the portfolio and increase regime dependence. Winning ex post may reflect a premium or an exceptional period.</p></div><div class="card"><h3>Systematic rules</h3><p>An alternative index may embody a valid idea. Skill requires evidence that the rule adds value robustly, not merely that its backtest selected a winning exposure.</p></div></div><div class="callout amber"><strong>A useful example:</strong> QQQ beats SPY's CAGR since 1999 ({pct(qqq.cagr)} versus {pct(qqq.spy_cagr)}), but not its RWM ({fmt(qqq.rwm_score,3)} versus {fmt(qqq.spy_rwm_score,3)}). A narrower index may capture an extraordinary regime without delivering a superior relative path under the chosen criterion.</div></section>

<section id="gestion"><div class="chapter"><b>4</b> The central test</div><h2>What remains when the product is expected to make decisions?</h2><p class="lede">Two layers prevent intention from being confused with skill: {managed_strict_active_n} products with identified active management and a wider ring of {managed_dynamic_inferred_n} dynamic or alternative strategies whose active label is not confirmed. The extended block contains {managed_n} products; economic exposure remains a separate axis.</p><div class="figure-wrap"><img src="{managed_plot_en}" alt="Active and dynamic management scorecard"><p class="figure-caption">Results for the extended active/dynamic block: CAGR as context, RWM as the criterion and their intersection as the stricter reading.</p></div><div class="kpis"><div class="kpi"><b>{managed_rwm_n}</b><span>beat RWM · {pct(managed_rwm_n/managed_n)}</span></div><div class="kpi"><b>{managed_cagr_rwm_n}</b><span>beat RWM + CAGR</span></div><div class="kpi"><b>{active_rwm}</b><span>identified active · RWM</span></div><div class="kpi"><b>{managed_rwm_n-active_rwm}</b><span>inferred dynamic · RWM</span></div></div><div class="figure-wrap"><img src="{management_base_rate_plot_en}" alt="Base rates by management style"><p class="figure-caption">Observed proportions and 95% Wilson intervals. Their overlap is a reminder that a management label is not causal evidence of added value.</p></div><div class="callout red"><strong>The bar stays high:</strong> {active_rwm} of {active_n} identified active products ({pct(active_rwm/active_n)}) beat SPY's RWM; {active_cagr_rwm} also beat its CAGR. Across the extended ring, the total rises to {managed_rwm_n} of {managed_n}. A process has been identified; that does not prove the process caused the outcome.</div><h3>The {managed_rwm_n} cases that beat SPY's RWM</h3>{managed_winner_en_html}</section>

<section id="candidatos"><div class="chapter"><b>5</b> Lowering the return bar—without giving away the result</div><h2>{risk_candidate_n} candidates show better RWM but still trail SPY's return</h2><p class="lede">We select {risk_candidate_n} products from the active/dynamic block that do not beat SPY's CAGR but do beat its RWM: {risk_active_n} have identified active management and {risk_dynamic_inferred_n} are inferred dynamic strategies. This is the right place to ask whether a more efficient relative path can become competitive through moderate leverage.</p><div class="grid2"><div class="card"><h3>Why they qualify</h3><p>RWM recognises growth over cash and penalises periods in which relative wealth remains below prior highs. It identifies useful paths without prematurely declaring absolute winners.</p></div><div class="card"><h3>What they have not earned</h3><p>Better RWM alone is not enough. They must match SPY's terminal wealth after financing the debt—and the RWM advantage must survive.</p></div></div><details open><summary>The {risk_candidate_n} relative-efficiency candidates</summary>{risk_en_html}</details></section>

<section id="apalancamiento"><div class="chapter"><b>6</b> Leverage ladder</div><h2>Leverage can lift CAGR. It cannot manufacture skill.</h2><p class="lede">Exposure is purchased once with fixed initial debt and then allowed to evolve. There is no daily rebalancing or invented turnover: leverage drifts with the market. Debt accrues the daily Effective Federal Funds Rate plus a 1.50% base spread under Actual/360.</p><div class="formula">Equity<sub>t</sub> = L × ETF<sub>t</sub> − (L−1) × Debt<sub>t</sub></div><div class="figure-wrap"><img src="{leverage_plot_en}" alt="Leverage ladder"><p class="figure-caption">Counts refer to the {risk_candidate_n} candidates. Leverage is fixed at inception; constant exposure is not targeted.</p></div>{leverage_en_html}<div class="callout"><strong>Reading the ladder:</strong> at 1.25×, four products already beat SPY's CAGR, five preserve RWM and three achieve both. At 2.00×, five reach the CAGR, but only three retain RWM and two retain both criteria. Leverage does not create skill; it exchanges path headroom for growth.</div><p class="small">The financing structure is a historical “IBKR-style” scenario, not an exact reconstruction of every past rate. IBKR publishes rates as benchmark plus spread, calculated daily and, for USD, on Actual/360. Official sources: <a href="https://www.interactivebrokers.com/en/trading/margin-rates.php" target="_blank" rel="noopener noreferrer">margin rates</a>, <a href="https://www.interactivebrokers.com/en/trading/margin-calculation-details.php" target="_blank" rel="noopener noreferrer">calculation method</a> and the <a href="https://fred.stlouisfed.org/series/DFF" target="_blank" rel="noopener noreferrer">Effective Federal Funds Rate (FRED)</a>.</p></section>

<section id="igualacion"><div class="chapter"><b>7</b> Exact return matching</div><h2>Same ending. Very different journey.</h2><p class="lede">We solve ex post for the exact initial leverage required to finish with the same wealth as SPY. This is a diagnostic—not an invertible rule—and it is capped at 2.00×. {feasible_match_n} of {risk_candidate_n} candidates can reach the target; {feasible_rwm_n} retain a higher RWM after financing.</p><h3>Different paths to the same terminal wealth</h3><div class="figure-wrap"><img src="{return_matched_equity_plot_en}" alt="Return-matched equity curves"><p class="figure-caption">Each panel begins at 100 on the ETF's inception date. The levered line includes historical financing and ends beside SPY by construction; the relevant difference is the path of relative wealth.</p></div><div class="figure-wrap"><img src="{return_match_plot_en}" alt="Return matching and financing sensitivity"><p class="figure-caption">Left: RWM after matching return. Right: sensitivity to the financing spread over Fed Funds.</p></div><div class="kpis"><div class="kpi"><b>{feasible_match_n}</b><span>reach SPY at ≤ 2×</span></div><div class="kpi"><b>{feasible_rwm_n}</b><span>preserve higher RWM</span></div><div class="kpi"><b>1.50%</b><span>base spread over DFF</span></div><div class="kpi"><b>2.00×</b><span>diagnostic cap</span></div></div><h3>Outcome by product</h3>{matched_en_html}<h3>Financing-cost sensitivity</h3>{sensitivity_en_html}<div class="callout red"><strong>Central result:</strong> DFAU, DUHP, JAVA and TEQI match terminal wealth below 2× and preserve higher RWM. HEQT reaches the return but loses its RWM advantage; SIXH would require more than 2×. The conclusion deteriorates as debt becomes more expensive.</div><p class="small">The 25% maintenance threshold is illustrative; actual requirements depend on broker, portfolio and product. Return matching uses ex-post information and must not be interpreted as an executable strategy.</p></section>

<section id="robustez"><div class="chapter"><b>8</b> Entry-point stability</div><h2>A launch-to-date win is not enough</h2><p class="lede">The {managed_rwm_n} RWM winners in the managed block are compared with SPY again from different entry months using rolling windows of roughly three years. {robust_managed_n} beat SPY's RWM from a majority of entry points. Because the windows overlap, this is temporal sensitivity—not an independent estimate of persistence.</p><div class="figure-wrap"><img src="{rolling_plot_en}" alt="Stability across entry points"><p class="figure-caption">Fraction and share of entry months whose subsequent 756-session window beats SPY's RWM; CAGR remains in the table as context.</p></div>{rolling_en_html}<div class="callout amber"><strong>An important separation:</strong> CGDV, CGUS, TSPA, CLSE, DFIV, SIXH and THRO beat RWM from at least half of the entry months. The others depend much more heavily on the chosen start. Apparent percentage precision should not be mistaken for independent samples.</div></section>

<section id="qinvia"><div class="chapter"><b>9</b> Synthesis and contrast</div><h2>One decision criterion, one complementary descriptor</h2><p class="lede">RWM orders the comparison with SPY; CAGR keeps economic magnitude visible. DBF± does not select winners in this study: it describes whether net return direction is supported by breadth.</p><div class="figure-wrap"><img src="{scatter_plot_en}" alt="CAGR versus RWM"><p class="figure-caption">The {rwm_n} points above zero on RWM beat SPY under the primary criterion; {cagr_rwm_n} also lie to the right of zero on CAGR. Visual limits trim extremes, but counts use every observation.</p></div><div class="grid2"><div class="card"><h3>{nfmt(rwm_n)} beat RWM</h3><p>{pct(rwm_n/cohort)} of the universe has a higher RWM than SPY over its comparable window.</p></div><div class="card"><h3>{nfmt(cagr_rwm_n)} beat RWM + CAGR</h3><p>{pct(cagr_rwm_n/cohort)} preserves the relative advantage and also finishes with higher annualised growth.</p></div></div><h3>The fifteen largest RWM advantages</h3>{rwm_en_html}<div class="formula">D± = Σr<sub>t</sub> / Σ|r<sub>t</sub>| &nbsp;·&nbsp; J = (Σ|r<sub>t</sub>|)² / (N·Σr<sub>t</sub>²) &nbsp;·&nbsp; DBF± = D± × J</div><div class="callout amber"><strong>DBF is a contrast, not a verdict:</strong> it is invariant to order and positive scale. It does not observe drawdowns, economic severity, tail risk, alpha or future return; it is therefore not used to declare superiority to SPY.</div><h3>The ten highest DBF± profiles</h3>{dbf_en_html}</section>

<section id="curva"><div class="chapter"><b>10</b> The universe as a whole</div><h2>SPY does not merely beat the average—it finishes high in the distribution</h2><p class="lede">Every ETF is rebased to 100 on 1 March 2022. The fan displays the full dispersion of buy-and-hold wealth; the second figure separates mean, median and coverage sensitivity. Neither represents a rebalanced portfolio.</p><div class="figure-wrap"><img src="{universe_fan_plot_en}" alt="ETF universe fan chart"><p class="figure-caption">Cross-sectional bands for {nfmt(summary['curve_diagnostics']['fixed_complete_constituents'])} products with complete coverage. The fan shows the centre, dispersion and extremes at the same time.</p></div><h3>The mean tells the same story</h3><div class="figure-wrap"><img src="{curve_plot_en}" alt="Average curve versus SPY"><p class="figure-caption">The complete-coverage sensitivity requires at least 98.5% observable sessions through the end.</p></div><div class="kpis"><div class="kpi"><b>{fmt(curves.spy.iloc[-1],1)}</b><span>SPY terminal wealth</span></div><div class="kpi"><b>{fmt(curves.etf_mean_fixed_complete.iloc[-1],1)}</b><span>mean ETF terminal wealth</span></div><div class="kpi"><b>{pct(spy_curve['cagr'])}</b><span>SPY CAGR</span></div><div class="kpi"><b>{pct(average_curve['cagr'])}</b><span>mean ETF CAGR</span></div></div><div class="callout"><strong>Descriptive result:</strong> the mean curve is neither tradable nor rebalanced. It only summarises where the universe ended and how much dispersion surrounded that outcome.</div></section>

<section id="veredicto"><div class="chapter"><b>11</b> Qinvia verdict</div><h2>Simple does not mean easy to beat</h2><div class="grid2"><div class="card"><h3>What the evidence does show</h3><ul><li>Only {pct(rwm_n/cohort)} of the universe beats SPY's RWM.</li><li>Only {pct(cagr_rwm_n/cohort)} beats RWM and CAGR simultaneously.</li><li>Most attributable winners reflect beta exposure, not demonstrated management skill.</li><li>{managed_rwm_n} of {managed_n} intentional-management products beat RWM; {robust_managed_n} do so from a majority of entry points.</li><li>After return matching and financing, {feasible_rwm_n} of {feasible_match_n} feasible cases preserve RWM.</li></ul></div><div class="card"><h3>Why the bar is structurally high</h3><ul><li>The S&amp;P 500 already diversifies hundreds of profitable, liquid businesses.</li><li>Capitalisation weighting lets winners grow and mechanically reduces the weight of losers.</li><li>Its membership renews; it is not a static portfolio of the companies selected in 1957.</li><li>SPY packages that exposure with deep liquidity, low cost and little operational friction.</li><li>A more complex product therefore carries the burden of showing what improves—and whether the improvement persists.</li></ul></div></div><div class="callout amber"><strong>Capacity, scale and the success paradox — hypothesis, not causal finding:</strong><p>One explanation consistent with the literature is that alpha has finite capacity. Strong results attract assets under management; deploying larger positions across a limited opportunity set can increase market impact, costs, liquidity constraints and competition, eroding the edge that attracted the flows. <a href="https://doi.org/10.1086/424739" target="_blank" rel="noopener noreferrer">Berk and Green (2004)</a> formalise this equilibrium; <a href="https://doi.org/10.1257/0002828043052277" target="_blank" rel="noopener noreferrer">Chen et al. (2004)</a> find a more adverse size relationship among funds exposed to small and illiquid stocks, while <a href="https://www.nber.org/system/files/working_papers/w19891/w19891.pdf" target="_blank" rel="noopener noreferrer">Pástor, Stambaugh and Taylor</a> find strong decreasing returns at the industry level but less conclusive evidence at the individual-fund level.</p><p>The counterpoint matters. Using real institutional trades, <a href="https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini%2C%20Israel%20and%20Moskowitz.pdf" target="_blank" rel="noopener noreferrer">Frazzini, Israel and Moskowitz</a> estimate far greater capacity than previously assumed for some strategies and show that cost-aware execution can expand it substantially. Capacity depends on turnover, horizon, liquidity, market breadth and execution. Our ETF data do not causally identify the effect of flows or estimate the capacity of each process; this mechanism is therefore presented as a plausible explanation, not a demonstrated conclusion.</p></div><div class="callout red"><strong>Conclusion:</strong> the industry offers thousands of narratives, wrappers and exposures; evidence of management-added value is far scarcer. The result does not prove that the industry is a fraud or that every narrow exposure is useless. It does show that complexity, brand and assets under management are not enough: against a broad, inexpensive, self-renewing index, the burden of proof is exceptionally high.</div><h3>Quality control and limits of free data</h3><p>We validated 5,505 Parquet files without integrity failures. The catalogue preserves historical identities, but the 67 non-current series all reach recent dates and do not represent liquidations distributed through time. Survivorship bias remains a material limitation. RWM uses DFF as idealised institutional cash—daily accrual, no spread, Actual/360—and does not represent a guaranteed retail return. The taxonomy uses auditable evidence and leaves unresolved cases explicit.</p><p class="small">Generated {generated}. Primary source: free Yahoo Finance · daily Adj Close · exact dates shared with SPY. Cash: FRED DFF.</p></section>
</main><footer>Qinvia · Carlos Barredo Lago</footer></body></html>'''

    html_path_en = output_root / f"{REPORT_BASENAME}_EN.html"
    html_path_en.write_text(html_en, encoding="utf-8")

    notebook_en = nbformat.v4.new_notebook()
    notebook_en.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "qinvia": {
            "report_version": "1A",
            "generated_at": generated,
            "study": "ETF Universe",
            "language": "en",
            "artifact_type": "narrative_companion",
        },
    }
    notebook_en.cells = [
        nbformat.v4.new_markdown_cell(f'''<style>{css}</style><div class="qinvia-cover"><a href="https://qinvia.com" target="_blank"><img src="{notebook_logo}" class="qinvia-logo" alt="Qinvia"></a><div class="qinvia-eyebrow">NARRATIVE NOTEBOOK · ETF UNIVERSE</div><h1>ETF Universe · Exposure, Skill, and Why SPY Is So Hard to Beat</h1><p class="qinvia-subtitle">Who produced a superior path, why—and what remains after return matching and financing.</p><div class="qinvia-meta"><span>Study 1A</span><span>Cutoff 1 Mar 2022</span><span>{nfmt(cohort)} products</span><span>{generated}</span></div></div>'''),
        nbformat.v4.new_markdown_cell("This notebook is the narrative, self-contained companion to the HTML report. Project modules perform the calculations and the frozen datasets are included in `data/`; the final cell reproduces the headline counts."),
        nbformat.v4.new_markdown_cell(f"## 1. Executive thesis\n\nTraditional metrics remain as a diagnostic. To decide which products produced a superior path to SPY, we use **RWM as the primary criterion** and **CAGR as economic context**: **{rwm_n} of {nfmt(cohort)} ({pct(rwm_n/cohort)})** beat SPY's RWM and **{cagr_rwm_n} ({pct(cagr_rwm_n/cohort)})** also beat its CAGR. Of the RWM winners, **{clear_beta_rwm_n}** reflect identifiable beta exposure and **{managed_evidence_rwm_n}** involve intentional management.\n\n**What RWM measures.** Relative-Wealth Martin calculates the Martin ratio entirely on ETF wealth relative to cash. It relates the annualised growth of that advantage to the Ulcer Index of the same curve: gaining ground versus cash is rewarded, while the depth and persistence of losing it are penalised. Here it condenses relative growth and damage into a single reading. [Read more about RWM at Qinvia Research](https://qinvia.com/research/relative-wealth-martin).\n\n" + markdown_table(headline_en)),
        nbformat.v4.new_markdown_cell(f"## 2. Universe and comparison bar\n\n<img src=\"{funnel_plot_en}\" style=\"width:100%\">\n\n- Yahoo Adj Close is used as a total-return proxy.\n- SPY is aligned to the exact sessions of each ETF.\n- CAGR, Sortino, Calmar, Martin and RWM remain in the descriptive tables.\n- Conclusions versus SPY use **Relative-Wealth Martin (RWM)**; CAGR is the second coordinate.\n- Cash: FRED DFF, daily accrual without spread, Actual/360.\n- First Yahoo session ≤ 1 Mar 2022 and at least 1,008 returns.\n- SPY is the investor's opportunity cost, not the natural benchmark for every asset class.\n- **Material survivorship bias:** {nfmt(summary['current_listing_count'])} current products and only {nfmt(summary['historical_identity_count'])} non-current products; they are not a representative history of dead funds.\n\n<img src=\"{inception_plot_en}\" style=\"width:100%\">"),
        nbformat.v4.new_markdown_cell(f"## 3. Exposure is not skill\n\n<img src=\"{provenance_plot_en}\" style=\"width:100%\">\n\nA sector, theme, country, metal or systematic rule may be an excellent exposure. Winning ex post shows that the risk was rewarded during the sample; it does not by itself demonstrate manager selection, timing or risk control."),
        nbformat.v4.new_markdown_cell(f"## 4. Active and dynamic management\n\nThe core contains **{managed_strict_active_n}** products with identified active management, plus **{managed_dynamic_inferred_n}** dynamic alternatives not confirmed as active. Of the **{managed_n}** products in the extended block, **{managed_rwm_n}** beat RWM and **{managed_cagr_rwm_n}** beat RWM + CAGR. Intent to manage is identified; skill is not presumed.\n\n<img src=\"{managed_plot_en}\" style=\"width:100%\">\n\n<img src=\"{management_base_rate_plot_en}\" style=\"width:100%\">\n\n" + markdown_table(managed_winner_en)),
        nbformat.v4.new_markdown_cell(f"## 5. Relative-efficiency candidates\n\nThere are **{risk_candidate_n}** products in the active/dynamic block that beat RWM but not CAGR: **{risk_active_n}** identified active products and **{risk_dynamic_inferred_n}** inferred dynamic strategies. These are the candidates for moderate leverage.\n\n" + markdown_table(risk_en)),
        nbformat.v4.new_markdown_cell(f"## 6. Leverage ladder\n\nDebt is fixed at inception and the position is not rebalanced. Financing accrues the daily Effective Federal Funds Rate + 1.50% under Actual/360. No fictional turnover is introduced.\n\n<img src=\"{leverage_plot_en}\" style=\"width:100%\">\n\n" + markdown_table(leverage_en)),
        nbformat.v4.new_markdown_cell(f"## 7. Return matching and financing cost\n\n**{feasible_match_n}** candidates reach SPY's terminal wealth at ≤ 2× and **{feasible_rwm_n}** preserve a higher RWM after financing. The solution is ex post and diagnostic, not an executable rule.\n\n### Different paths to the same terminal wealth\n\n<img src=\"{return_matched_equity_plot_en}\" style=\"width:100%\">\n\n<img src=\"{return_match_plot_en}\" style=\"width:100%\">\n\n" + markdown_table(matched_en) + "\n\n### Financing-spread sensitivity\n\n" + markdown_table(sensitivity_en)),
        nbformat.v4.new_markdown_cell(f"## 8. Entry-point stability\n\nOf the {managed_rwm_n} RWM winners in the managed block, **{robust_managed_n}** beat SPY's RWM from a majority of entry months. The three-year windows overlap: this is temporal sensitivity, not an independent test of persistence.\n\n<img src=\"{rolling_plot_en}\" style=\"width:100%\">\n\n" + markdown_table(rolling_en)),
        nbformat.v4.new_markdown_cell(f"## 9. RWM synthesis and DBF contrast\n\n<img src=\"{scatter_plot_en}\" style=\"width:100%\">\n\nRWM decides the comparison with SPY; CAGR keeps economic magnitude visible. **{rwm_n} ({pct(rwm_n/cohort)})** products beat RWM and **{cagr_rwm_n} ({pct(cagr_rwm_n/cohort)})** beat RWM + CAGR. DBF± remains a direction-and-breadth descriptor; it does not select winners.\n\n### Largest RWM advantages\n\n" + markdown_table(rwm_en, 15) + "\n\n### Highest DBF± profiles\n\n" + markdown_table(dbf_en, 10)),
        nbformat.v4.new_markdown_cell(f"## 10. Common curve from the cutoff\n\n<img src=\"{universe_fan_plot_en}\" style=\"width:100%\">\n\nThe fan displays the 10th–90th and 25th–75th percentiles for {nfmt(summary['curve_diagnostics']['fixed_complete_constituents'])} products with complete coverage.\n\n<img src=\"{curve_plot_en}\" style=\"width:100%\">\n\nCross-sectional mean and median buy-and-hold wealth. This describes the universe; it is neither a rebalanced portfolio nor a tradable strategy."),
        nbformat.v4.new_markdown_cell(f"## 11. Qinvia verdict\n\n- Only {pct(rwm_n/cohort)} of the universe beats SPY's RWM.\n- Only {pct(cagr_rwm_n/cohort)} beats RWM + CAGR.\n- Most attributable winners reflect beta, not demonstrated management skill.\n- {managed_rwm_n} of {managed_n} intentional-management products beat RWM; {robust_managed_n} do so from a majority of entry points.\n- After return matching and financing, {feasible_rwm_n} of {feasible_match_n} feasible cases preserve RWM.\n\n### Capacity, scale and the success paradox\n\n**A literature-consistent hypothesis, not a causal finding.** One possible explanation is that alpha has finite capacity: strong results attract assets under management, and deploying larger positions across a limited opportunity set can increase market impact, costs, liquidity constraints and competition. [Berk and Green (2004)](https://doi.org/10.1086/424739) formalise this equilibrium; [Chen et al. (2004)](https://doi.org/10.1257/0002828043052277) find a more adverse size relationship among funds exposed to small and illiquid stocks, while [Pástor, Stambaugh and Taylor](https://www.nber.org/system/files/working_papers/w19891/w19891.pdf) find strong decreasing returns at the industry level but less conclusive evidence at the individual-fund level.\n\nThe counterpoint matters. Using real institutional trades, [Frazzini, Israel and Moskowitz](https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini%2C%20Israel%20and%20Moskowitz.pdf) estimate far greater capacity than previously assumed for some strategies and show that cost-aware execution can expand it substantially. Capacity depends on turnover, horizon, liquidity, market breadth and execution. Our ETF data do not causally identify the effect of flows or estimate the capacity of each process; this mechanism is presented as a plausible explanation, not a demonstrated conclusion.\n\n**Conclusion:** SPY sets a structurally high bar through diversification, capitalisation weighting, constituent renewal, liquidity and low cost. The industry offers thousands of narratives and exposures; evidence of management-added value is far scarcer. Complexity, brand and assets under management do not replace empirical proof."),
        nbformat.v4.new_markdown_cell("## 12. Limits and sources\n\n- SPY is not the natural benchmark for every mandate.\n- The free taxonomy preserves unresolved cases.\n- Exact leverage is solved ex post.\n- The 25% maintenance threshold is illustrative.\n- The Yahoo cohort does not contain a representative history of dead ETFs; survivorship bias remains material.\n- A causal follow-up requires an exposure-matched passive benchmark for every manager.\n\nFinancing sources: [IBKR Margin Rates](https://www.interactivebrokers.com/en/trading/margin-rates.php), [IBKR Margin Calculation](https://www.interactivebrokers.com/en/trading/margin-calculation-details.php) and [FRED DFF](https://fred.stlouisfed.org/series/DFF).\n\nThe `data/` directory contains the cohort, taxonomy, leverage, sensitivity and robustness outputs."),
        nbformat.v4.new_markdown_cell("## 13. Reproducibility check\n\nThis optional cell loads the frozen datasets distributed alongside the notebook and verifies the headline counts."),
        nbformat.v4.new_code_cell('''from pathlib import Path
import pandas as pd

data_dir = Path("data")
selected_check = pd.read_parquet(data_dir / "selected_etfs.parquet")
managed_check = pd.read_csv(data_dir / "intentional_management_products.csv")
matched_check = pd.read_csv(data_dir / "return_matched_leverage.csv")
curves_check = pd.read_parquet(data_dir / "return_matched_equity_curves.parquet")

{
    "products": len(selected_check),
    "beat_spy_rwm": int(selected_check.beat_spy_rwm_score.sum()),
    "beat_spy_rwm_and_cagr": int(selected_check.beat_spy_cagr_and_rwm.sum()),
    "intentional_management_beats_rwm": int(managed_check.beat_spy_rwm_score.sum()),
    "match_spy_at_or_below_2x": int(matched_check.feasible_at_or_below_2x.sum()),
    "match_and_preserve_rwm": int((matched_check.feasible_at_or_below_2x & matched_check.matched_rwm_beats_spy.fillna(False)).sum()),
    "return_matched_curves": int(curves_check.request_symbol.nunique()),
}
'''),
        nbformat.v4.new_markdown_cell("---\n\n**Qinvia · Carlos Barredo Lago**"),
    ]
    notebook_path_en = output_root / f"{REPORT_BASENAME}_EN.ipynb"
    nbformat.write(notebook_en, notebook_path_en)
    set_language("es")
    return html_path, notebook_path, html_path_en, notebook_path_en


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=PROJECT_ROOT / "data/processed/studies/etf_universe_1A")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "reports/etf_universe_1A")
    parser.add_argument("--catalogue", type=Path, default=PROJECT_ROOT / "data/interim/universe/catalog.csv")
    parser.add_argument("--logo", type=Path, default=PROJECT_ROOT / "assets/qinvia-logo-horizontal.svg")
    parser.add_argument("--icon", type=Path, default=PROJECT_ROOT / "assets/qinvia-favicon.svg")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    html_path, notebook_path, html_path_en, notebook_path_en = build(
        args.results_root,
        args.output_root,
        args.logo,
        args.icon,
        args.catalogue,
    )
    print(
        json.dumps(
            {
                "html_es": str(html_path),
                "notebook_es": str(notebook_path),
                "html_en": str(html_path_en),
                "notebook_en": str(notebook_path_en),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

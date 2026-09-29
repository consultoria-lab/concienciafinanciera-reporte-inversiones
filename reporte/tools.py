"""
Centralized LangChain @tool definitions.

Wraps existing data-fetching logic (yfinance, datos.gov.co) as LangChain tools
so they can be used by ReAct agents for dynamic tool selection.
"""
from __future__ import annotations

import json

from langchain.tools import tool


@tool
def fetch_yfinance_data(ticker: str, years: int = 10) -> str:
    """Fetch market data from Yahoo Finance for a given ticker.

    Retrieves daily closing prices and computes CAGR, annualized volatility,
    1-sigma band, and current price.

    Args:
        ticker: Yahoo Finance ticker symbol (e.g. "SPY", "GLD", "BTC-USD").
        years: Number of years of historical data to fetch. Defaults to 10.

    Returns:
        JSON string with keys: precio_actual, cagr, volatilidad,
        rango_1sigma, periodo, ticker, n_dias.
    """
    from reporte.assets.yfinance_base import fetch_metrics

    metrics = fetch_metrics(ticker, years=years)
    # Convert tuple to list for JSON serialization
    metrics["rango_1sigma"] = list(metrics["rango_1sigma"])
    return json.dumps(metrics, ensure_ascii=False)


@tool
def fetch_datosgovco_data(
    codigo_negocio: int,
    tipo_participacion: int,
    years: int = 1,
) -> str:
    """Fetch FIC (Fondo de Inversion Colectiva) data from datos.gov.co.

    Queries the Colombian government open-data API for collective investment
    fund metrics: average annual return, volatility, and 1-sigma band.

    Args:
        codigo_negocio: Fund business code in datos.gov.co.
        tipo_participacion: Participation type code.
        years: Number of years of historical data. Defaults to 1.

    Returns:
        JSON string with keys: rentabilidad_media, volatilidad,
        rango_1sigma, periodo, nombre_patrimonio, n_registros, tipo.
    """
    from reporte.assets.datosgovco_base import fetch_fic_metrics

    metrics = fetch_fic_metrics(
        codigo_negocio=codigo_negocio,
        tipo_participacion=tipo_participacion,
        years=years,
    )
    metrics["rango_1sigma"] = list(metrics["rango_1sigma"])
    return json.dumps(metrics, ensure_ascii=False)


@tool
def compare_assets_benchmark(assets_json: str) -> str:
    """Compare multiple assets by computing a simplified Sharpe-like ratio.

    Takes a JSON array of asset objects (each with 'name', 'cagr', 'volatilidad')
    and ranks them by return-to-risk ratio (CAGR / volatility).

    Args:
        assets_json: JSON string — array of objects with keys:
            name (str), cagr (float, e.g. 0.08 = 8%), volatilidad (float).

    Returns:
        JSON string — array sorted by sharpe_ratio descending, each entry
        with keys: name, cagr, volatilidad, sharpe_ratio, rank.
    """
    assets = json.loads(assets_json)
    ranked = []
    for a in assets:
        vol = a.get("volatilidad", 0)
        cagr = a.get("cagr", 0)
        sharpe = round(cagr / vol, 4) if vol > 0 else 0.0
        ranked.append({
            "name": a["name"],
            "cagr": cagr,
            "volatilidad": vol,
            "sharpe_ratio": sharpe,
        })
    ranked.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
    for i, entry in enumerate(ranked, 1):
        entry["rank"] = i
    return json.dumps(ranked, ensure_ascii=False, indent=2)

"""
Base de extracción y cálculo para activos de mercado vía yfinance.

Función pública: fetch_metrics(ticker, years) → dict con CAGR, volatilidad y rango 1σ.
Usada por todos los analyzers de activos de mercado (SPY, GLD, WTI, USDCOP, BTC).
"""
import warnings
from datetime import date

import numpy as np

warnings.filterwarnings("ignore")


def fetch_metrics(ticker: str, years: int = 10) -> dict:
    """
    Descarga precios de cierre diarios de Yahoo Finance y calcula:
      - CAGR: (precio_final / precio_inicial)^(1/anos) - 1
      - Volatilidad anualizada: std(retornos_diarios) * sqrt(252)
      - Rango 1-sigma: (CAGR - vol, CAGR + vol)
      - Precio actual: ultimo cierre disponible
      - Periodo: "YYYY-MM-DD / YYYY-MM-DD"

    Returns dict con claves:
        precio_actual (float), cagr (float), volatilidad (float),
        rango_1sigma (tuple[float, float]), periodo (str),
        ticker (str), n_dias (int)

    Raises ValueError si hay menos de 200 dias de datos.
    """
    import yfinance as yf

    # Usar Ticker.history() para mayor compatibilidad con yfinance 1.x
    t = yf.Ticker(ticker)
    hist = t.history(period=f"{years}y", auto_adjust=True)

    if hist is None or hist.empty:
        raise ValueError(f"[yfinance_base] Sin datos para {ticker}")

    prices = hist["Close"].dropna()

    if len(prices) < 200:
        raise ValueError(
            f"[yfinance_base] Solo {len(prices)} días para {ticker} — "
            f"mínimo requerido: 200"
        )

    years_actual = len(prices) / 252
    cagr = float((prices.iloc[-1] / prices.iloc[0]) ** (1 / years_actual) - 1)

    daily_returns = prices.pct_change().dropna()
    ann_vol = float(daily_returns.std() * (252 ** 0.5))

    periodo = (
        f"{prices.index[0].date()} / {prices.index[-1].date()}"
    )

    return {
        "precio_actual": round(float(prices.iloc[-1]), 2),
        "cagr": round(cagr, 4),
        "volatilidad": round(ann_vol, 4),
        "rango_1sigma": (
            round(cagr - ann_vol, 4),
            round(cagr + ann_vol, 4),
        ),
        "periodo": periodo,
        "ticker": ticker,
        "n_dias": len(prices),
    }

"""Analyzer para Bitcoin (BTC-USD) vía yfinance."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[2]))

from models import AssetData
from assets.yfinance_base import fetch_metrics

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def analyze() -> AssetData:
    config = yaml.safe_load(open(_CONFIG_PATH, encoding="utf-8"))
    m = fetch_metrics(config["ticker"], years=config["years"])
    print(f"[btc] CAGR={m['cagr']*100:.2f}%  Vol={m['volatilidad']*100:.2f}%  ({m['n_dias']} días)")
    return AssetData(
        asset_name=config["asset_name"],
        categoria=config["categoria"],
        subcategoria=config.get("subcategoria", ""),
        nivel_riesgo=config["nivel_riesgo"],
        tasa_referencia=round(m["cagr"] * 100, 2),
        fuente=config["fuente"],
        corte=m["periodo"].split(" / ")[1],
        metricas_mercado={**m, "moneda": config["moneda"]},
    )

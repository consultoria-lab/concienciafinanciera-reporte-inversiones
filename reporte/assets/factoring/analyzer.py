"""Analyzer para Factoring (FIC) vía datos.gov.co."""
from pathlib import Path

import yaml

from reporte.assets.datosgovco_base import fetch_fic_metrics
from reporte.models import AssetData

_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def analyze() -> AssetData:
    config = yaml.safe_load(open(_CONFIG_PATH, encoding="utf-8"))
    m = fetch_fic_metrics(
        codigo_negocio=config["codigo_negocio"],
        tipo_participacion=config["tipo_participacion"],
        years=config["years"],
    )
    print(
        f"[factoring] Media={m['rentabilidad_media']*100:.2f}%  "
        f"Vol={m['volatilidad']*100:.2f}%  ({m['n_registros']} registros)"
    )
    return AssetData(
        asset_name=config["asset_name"],
        categoria=config["categoria"],
        subcategoria=config.get("subcategoria", ""),
        nivel_riesgo=config["nivel_riesgo"],
        tasa_referencia=round(m["rentabilidad_media"] * 100, 2),
        fuente=config["fuente"],
        corte=m["periodo"].split(" / ")[1],
        metricas_mercado=m,
    )

"""
Base de extracción y cálculo para activos FIC vía datos.gov.co.

Función pública: fetch_fic_metrics(codigo_negocio, tipo_participacion, years)
→ dict con rentabilidad media, volatilidad y rango 1σ.

Usada por los analyzers de Factoring y Deuda Corporativa.
"""
import os
from datetime import date, timedelta

import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

_API_URL = "https://www.datos.gov.co/resource/qhpu-8ixx.json"


def fetch_fic_metrics(
    codigo_negocio: int,
    tipo_participacion: int,
    years: int = 1,
) -> dict:
    """
    Consulta la API de FICs en datos.gov.co y calcula:
      - Rentabilidad media anual (promedio de rentabilidad_anual)
      - Volatilidad (desviación estándar de rentabilidad_anual)
      - Rango 1σ: (media - vol, media + vol)

    Los valores se retornan en escala 0-1 (divididos entre 100)
    para compatibilidad con el renderer existente.

    Returns dict con claves:
        rentabilidad_media (float), volatilidad (float),
        rango_1sigma (tuple[float, float]), periodo (str),
        nombre_patrimonio (str), n_registros (int), tipo (str)

    Raises ValueError si no hay datos suficientes.
    """
    fecha_desde = (date.today() - timedelta(days=365 * years)).isoformat()

    params = {
        "codigo_negocio": str(codigo_negocio),
        "tipo_participacion": str(tipo_participacion),
        "$where": f"fecha_corte >= '{fecha_desde}'",
        "$select": "fecha_corte, rentabilidad_anual, nombre_patrimonio",
        "$order": "fecha_corte ASC",
        "$limit": 5000,
    }

    auth = None
    api_key = os.getenv("DATOS_GOV_API_KEY")
    api_secret = os.getenv("DATOS_GOV_API_SECRET")
    if api_key and api_secret:
        auth = (api_key, api_secret)

    resp = requests.get(_API_URL, params=params, auth=auth, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        raise ValueError(
            f"[datosgovco_base] Sin datos para codigo_negocio={codigo_negocio}, "
            f"tipo_participacion={tipo_participacion} desde {fecha_desde}"
        )

    rentabilidades = []
    for row in data:
        val = row.get("rentabilidad_anual")
        if val is not None:
            rentabilidades.append(float(val))

    if len(rentabilidades) < 10:
        raise ValueError(
            f"[datosgovco_base] Solo {len(rentabilidades)} registros para "
            f"codigo_negocio={codigo_negocio} — mínimo requerido: 10"
        )

    arr = np.array(rentabilidades)
    # rentabilidad_anual viene en porcentaje (e.g. 12.5 = 12.5%)
    # Convertir a escala 0-1 para compatibilidad
    media = float(np.mean(arr)) / 100
    vol = float(np.std(arr)) / 100

    nombre = data[0].get("nombre_patrimonio", "N/A")
    fecha_min = data[0].get("fecha_corte", "")[:10]
    fecha_max = data[-1].get("fecha_corte", "")[:10]

    return {
        "rentabilidad_media": round(media, 4),
        "volatilidad": round(vol, 4),
        "rango_1sigma": (
            round(media - vol, 4),
            round(media + vol, 4),
        ),
        "periodo": f"{fecha_min} / {fecha_max}",
        "nombre_patrimonio": nombre,
        "n_registros": len(rentabilidades),
        "tipo": "fic",
    }

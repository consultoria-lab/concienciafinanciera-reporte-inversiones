"""
Orquestador del pipeline con LangGraph.

Flujo: scrape_node → analyze_node → report_node

El estado del grafo (ReportState) acumula los AssetData de cada activo.
Los errores en scraping/análisis se loguean pero no detienen el pipeline.
"""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import TypedDict

from reporte.models import AssetData, ReportData

try:
    from langgraph.graph import StateGraph, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Estado del grafo
# ---------------------------------------------------------------------------

class ReportState(TypedDict):
    activos_data: list[AssetData]
    errores: list[str]
    report_path: str
    _raw_paths: dict  # paths de archivos descargados por scrape_node


# ---------------------------------------------------------------------------
# Nodos del grafo
# ---------------------------------------------------------------------------

def scrape_node(state: ReportState) -> ReportState:
    """Descarga los datos crudos de todos los activos registrados."""
    from reporte.assets.cuentas_ahorro.scraper import download_excel
    from reporte.assets.cdts.scraper import download_excel as download_cdt

    paths = {}
    errores = list(state.get("errores", []))

    try:
        path = download_excel(headless=True)
        paths["cuentas_ahorro"] = path
        print(f"[orchestrator] scrape_node ✓ cuentas_ahorro → {path.name}")
    except Exception as e:
        msg = f"[orchestrator] scrape_node ERROR cuentas_ahorro: {e}"
        print(msg)
        errores.append(msg)

    try:
        path = download_cdt(headless=True)
        paths["cdts"] = path
        print(f"[orchestrator] scrape_node ✓ cdts → {path.name}")
    except Exception as e:
        msg = f"[orchestrator] scrape_node ERROR cdts: {e}"
        print(msg)
        errores.append(msg)

    # Estado inmutable: retornar copia con nuevos campos
    return {**state, "_raw_paths": paths, "errores": errores}


_YFINANCE_ASSETS = ["spy", "gld", "wti", "usdcop", "btc"]
_DATOSGOVCO_ASSETS = ["factoring", "deuda_corporativa"]


def analyze_node(state: ReportState) -> ReportState:
    """Analiza los datos descargados y construye AssetData por activo."""
    import importlib
    from reporte.assets.cuentas_ahorro.analyzer import analyze
    from reporte.models import AssetData, AssetGroup, Entidad

    raw_paths: dict = state.get("_raw_paths", {})
    activos_data: list[AssetData] = list(state.get("activos_data", []))
    errores = list(state.get("errores", []))

    if "cuentas_ahorro" in raw_paths:
        try:
            result = analyze(raw_paths["cuentas_ahorro"])

            grupos = []
            for g in result["grupos"]:
                entidades = [
                    Entidad(
                        nombre=e["nombre"],
                        tasa_activa=e["tasa_activa"],
                        tasa_inactiva=e.get("tasa_inactiva"),
                    )
                    for e in g["entidades"]
                ]
                grupos.append(
                    AssetGroup(
                        nombre=g["nombre"],
                        entidades=entidades,
                        percentil_75=g["percentil_75"],
                        rango=tuple(g.get("rango", [0.0, 0.0])),
                    )
                )

            asset_data = AssetData(
                asset_name="Cuentas de Ahorro",
                categoria="Renta Fija",
                nivel_riesgo="Bajo",
                tasa_referencia=result["tasa_referencia_global"],
                grupos=grupos,
                fuente="Superintendencia Financiera de Colombia",
                corte=result.get("corte", ""),
            )
            activos_data.append(asset_data)
            print(f"[orchestrator] analyze_node ✓ cuentas_ahorro P75={asset_data.tasa_referencia}%")
        except Exception as e:
            msg = f"[orchestrator] analyze_node ERROR cuentas_ahorro: {e}\n{traceback.format_exc()}"
            print(msg)
            errores.append(msg)

    if "cdts" in raw_paths:
        try:
            from reporte.assets.cdts.analyzer import analyze as analyze_cdts
            result = analyze_cdts(raw_paths["cdts"])

            grupos = []
            for g in result["grupos"]:
                entidades = [
                    Entidad(
                        nombre=e["nombre"],
                        tasa_activa=e["tasa_activa"],
                        tasa_inactiva=e.get("tasa_inactiva"),
                    )
                    for e in g["entidades"]
                ]
                grupos.append(
                    AssetGroup(
                        nombre=g["nombre"],
                        entidades=entidades,
                        percentil_75=g["percentil_75"],
                        rango=tuple(g.get("rango", [0.0, 0.0])),
                    )
                )

            asset_data = AssetData(
                asset_name="CDT",
                categoria="Renta Fija",
                nivel_riesgo="Bajo",
                tasa_referencia=result["tasa_referencia_global"],
                grupos=grupos,
                fuente="Superintendencia Financiera de Colombia",
                corte=result.get("corte", ""),
            )
            activos_data.append(asset_data)
            print(f"[orchestrator] analyze_node ✓ cdts P75={asset_data.tasa_referencia}%")
        except Exception as e:
            msg = f"[orchestrator] analyze_node ERROR cdts: {e}\n{traceback.format_exc()}"
            print(msg)
            errores.append(msg)

    # Activos de mercado vía yfinance (no requieren scraping de archivo)
    for asset_key in _YFINANCE_ASSETS:
        try:
            module = importlib.import_module(f"reporte.assets.{asset_key}.analyzer")
            asset_data = module.analyze()
            activos_data.append(asset_data)
            print(f"[orchestrator] analyze_node ✓ {asset_key} CAGR={asset_data.tasa_referencia}%")
        except Exception as e:
            msg = f"[orchestrator] analyze_node ERROR {asset_key}: {e}\n{traceback.format_exc()}"
            print(msg)
            errores.append(msg)

    # Activos FIC vía datos.gov.co (no requieren scraping de archivo)
    for asset_key in _DATOSGOVCO_ASSETS:
        try:
            module = importlib.import_module(f"reporte.assets.{asset_key}.analyzer")
            asset_data = module.analyze()
            activos_data.append(asset_data)
            print(f"[orchestrator] analyze_node ✓ {asset_key} Media={asset_data.tasa_referencia}%")
        except Exception as e:
            msg = f"[orchestrator] analyze_node ERROR {asset_key}: {e}\n{traceback.format_exc()}"
            print(msg)
            errores.append(msg)

    return {**state, "activos_data": activos_data, "errores": errores}


def report_node(state: ReportState) -> ReportState:
    """Genera el reporte HTML a partir de los AssetData acumulados."""
    from reporte.pipeline.report_generator import generate_html

    activos_data = state.get("activos_data", [])
    errores = list(state.get("errores", []))

    try:
        report_data = ReportData(activos=activos_data)
        report_path = generate_html(report_data)
        print(f"[orchestrator] report_node ✓ → {report_path}")
        return {**state, "report_path": str(report_path), "errores": errores}
    except Exception as e:
        msg = f"[orchestrator] report_node ERROR: {e}\n{traceback.format_exc()}"
        print(msg)
        errores.append(msg)
        return {**state, "report_path": "", "errores": errores}


# ---------------------------------------------------------------------------
# Construcción y ejecución del grafo
# ---------------------------------------------------------------------------

def build_graph():
    """Construye el grafo LangGraph del pipeline."""
    if not _LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph no está instalado. Ejecuta: uv add langgraph")

    graph = StateGraph(ReportState)
    graph.add_node("scrape", scrape_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("scrape")
    graph.add_edge("scrape", "analyze")
    graph.add_edge("analyze", "report")
    graph.add_edge("report", END)

    return graph.compile()


def run_pipeline() -> ReportState:
    """Ejecuta el pipeline completo y retorna el estado final."""
    if _LANGGRAPH_AVAILABLE:
        app = build_graph()
        initial_state: ReportState = {
            "activos_data": [],
            "errores": [],
            "report_path": "",
            "_raw_paths": {},
        }
        final_state = app.invoke(initial_state)
    else:
        # Modo fallback sin LangGraph: ejecutar nodos en secuencia
        print("[orchestrator] langgraph no disponible, ejecutando en modo secuencial.")
        state: ReportState = {"activos_data": [], "errores": [], "report_path": "", "_raw_paths": {}}
        state = scrape_node(state)
        state = analyze_node(state)
        state = report_node(state)
        final_state = state

    if final_state.get("errores"):
        print(f"\n[orchestrator] Errores registrados ({len(final_state['errores'])}):")
        for err in final_state["errores"]:
            print(f"  - {err[:200]}")

    return final_state

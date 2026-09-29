"""
Orquestador del pipeline con LangGraph.

Flujo avanzado con conditional edges y iteration loop:

  scrape -> prepare_assets -> analyze_asset --+--> should_continue
                                  ^           |         |
                                  |           |    "recommend"
                                  +-----------+         |
                               "analyze_asset"    recommend -> report -> END

Patrones LangGraph demostrados:
  - Annotated reducers (operator.add) para acumulacion automatica de estado
  - Conditional edges (should_continue) para loop de iteracion
  - Structured output con with_structured_output (recommend_node)
  - Graceful degradation sin OPENAI_API_KEY
  - GraphRecursionError handling
"""
from __future__ import annotations

import importlib
import os
import traceback
from pathlib import Path
from typing import Annotated, TypedDict

import operator

from reporte.models import AssetData, AssetGroup, Entidad, ReportData

try:
    from langgraph.graph import StateGraph, END
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Estado del grafo con Annotated reducers
# ---------------------------------------------------------------------------

class ReportState(TypedDict):
    activos_data: Annotated[list[AssetData], operator.add]  # reducer: append
    errores: Annotated[list[str], operator.add]              # reducer: append
    asset_keys: list[str]          # lista ordenada de assets a procesar
    current_index: int             # puntero de iteracion
    _raw_paths: dict[str, Path]    # archivos descargados por scrape_node
    report_path: str               # ruta del reporte generado
    recomendaciones: dict          # output del recommend_node


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_ALL_ASSET_KEYS = [
    "cuentas_ahorro", "cdts",
    "spy", "gld", "wti", "usdcop", "btc",
    "factoring", "deuda_corporativa",
]

_YFINANCE_ASSETS = {"spy", "gld", "wti", "usdcop", "btc"}
_DATOSGOVCO_ASSETS = {"factoring", "deuda_corporativa"}
_RENTA_FIJA_ASSETS = {"cuentas_ahorro", "cdts"}

_RENTA_FIJA_CONFIG = {
    "cuentas_ahorro": {
        "analyzer_module": "reporte.assets.cuentas_ahorro.analyzer",
        "asset_name": "Cuentas de Ahorro",
    },
    "cdts": {
        "analyzer_module": "reporte.assets.cdts.analyzer",
        "asset_name": "CDT",
    },
}


# ---------------------------------------------------------------------------
# Helper: build AssetData from renta fija result dict
# ---------------------------------------------------------------------------

def _build_asset_data_from_result(asset_key: str, result: dict) -> AssetData:
    """Converts an analyzer result dict into an AssetData for renta fija assets.

    Eliminates duplication between cuentas_ahorro and cdts processing.
    """
    config = _RENTA_FIJA_CONFIG[asset_key]
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

    return AssetData(
        asset_name=config["asset_name"],
        categoria="Renta Fija",
        nivel_riesgo="Bajo",
        tasa_referencia=result["tasa_referencia_global"],
        grupos=grupos,
        fuente="Superintendencia Financiera de Colombia",
        corte=result.get("corte", ""),
    )


# ---------------------------------------------------------------------------
# Nodos del grafo
# ---------------------------------------------------------------------------

def scrape_node(state: ReportState) -> dict:
    """Descarga los datos crudos (Excel) de activos de renta fija."""
    from reporte.assets.cuentas_ahorro.scraper import download_excel
    from reporte.assets.cdts.scraper import download_excel as download_cdt

    paths: dict[str, Path] = {}
    nuevos_errores: list[str] = []

    try:
        path = download_excel(headless=True)
        paths["cuentas_ahorro"] = path
        print(f"[orchestrator] scrape_node ✓ cuentas_ahorro → {path.name}")
    except Exception as e:
        msg = f"[orchestrator] scrape_node ERROR cuentas_ahorro: {e}"
        print(msg)
        nuevos_errores.append(msg)

    try:
        path = download_cdt(headless=True)
        paths["cdts"] = path
        print(f"[orchestrator] scrape_node ✓ cdts → {path.name}")
    except Exception as e:
        msg = f"[orchestrator] scrape_node ERROR cdts: {e}"
        print(msg)
        nuevos_errores.append(msg)

    # Reducer-compatible: return only new data
    return {"_raw_paths": paths, "errores": nuevos_errores}


def prepare_assets_node(state: ReportState) -> dict:
    """Builds the ordered list of asset keys to iterate over.

    Only includes renta fija assets if their Excel was successfully downloaded.
    Market assets (yfinance, datos.gov.co) are always included.
    """
    raw_paths = state.get("_raw_paths", {})
    keys: list[str] = []
    for k in _ALL_ASSET_KEYS:
        if k in _RENTA_FIJA_ASSETS:
            if k in raw_paths:
                keys.append(k)
        else:
            keys.append(k)
    return {"asset_keys": keys, "current_index": 0}


def analyze_single_asset_node(state: ReportState) -> dict:
    """Analyzes a single asset based on current_index and increments the pointer.

    Returns reducer-compatible dict with the new AssetData (or error) and
    the incremented index.
    """
    idx = state["current_index"]
    asset_key = state["asset_keys"][idx]
    raw_paths = state.get("_raw_paths", {})

    try:
        if asset_key in _RENTA_FIJA_ASSETS:
            config = _RENTA_FIJA_CONFIG[asset_key]
            module = importlib.import_module(config["analyzer_module"])
            result = module.analyze(raw_paths[asset_key])
            asset_data = _build_asset_data_from_result(asset_key, result)
            print(f"[orchestrator] analyze_asset ✓ {asset_key} P75={asset_data.tasa_referencia}%")
        else:
            # yfinance or datos.gov.co — module.analyze() returns AssetData directly
            module = importlib.import_module(f"reporte.assets.{asset_key}.analyzer")
            asset_data = module.analyze()
            metric_label = "CAGR" if asset_key in _YFINANCE_ASSETS else "Media"
            print(f"[orchestrator] analyze_asset ✓ {asset_key} {metric_label}={asset_data.tasa_referencia}%")

        return {
            "activos_data": [asset_data],
            "current_index": idx + 1,
        }
    except Exception as e:
        msg = f"[orchestrator] analyze_asset ERROR {asset_key}: {e}\n{traceback.format_exc()}"
        print(msg)
        return {
            "errores": [msg],
            "current_index": idx + 1,
        }


def should_continue(state: ReportState) -> str:
    """Conditional edge: loop back to analyze_asset or proceed to recommend.

    This is the core iteration pattern — processes assets one at a time
    until all have been analyzed.
    """
    if state["current_index"] < len(state["asset_keys"]):
        return "analyze_asset"
    return "recommend"


def recommend_node(state: ReportState) -> dict:
    """Generates investment recommendations using LLM with structured output.

    Uses with_structured_output(Recomendaciones) to produce typed recommendations
    for 3 investor profiles (Conservador, Moderado, Agresivo).

    Graceful degradation: returns empty dict if no OPENAI_API_KEY available.
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("[orchestrator] recommend_node: sin OPENAI_API_KEY, omitiendo recomendaciones.")
        return {"recomendaciones": {}}

    try:
        from langchain_openai import ChatOpenAI
        from reporte.models import Recomendaciones
    except ImportError:
        print("[orchestrator] recommend_node: langchain-openai no disponible.")
        return {"recomendaciones": {}}

    activos_data: list[AssetData] = state.get("activos_data", [])
    if not activos_data:
        return {"recomendaciones": {}}

    # Build context summary for the LLM
    resumen_lineas = []
    for a in activos_data:
        if a.metricas_mercado and a.metricas_mercado.get("tipo") == "fic":
            m = a.metricas_mercado
            resumen_lineas.append(
                f"- {a.asset_name} ({a.categoria}/{a.subcategoria}): "
                f"Rentabilidad media={m['rentabilidad_media']*100:.2f}%, "
                f"Vol={m['volatilidad']*100:.2f}%, Riesgo={a.nivel_riesgo}"
            )
        elif a.metricas_mercado:
            m = a.metricas_mercado
            resumen_lineas.append(
                f"- {a.asset_name} ({a.categoria}/{a.subcategoria}): "
                f"CAGR={m['cagr']*100:.2f}%, "
                f"Vol={m['volatilidad']*100:.2f}%, Riesgo={a.nivel_riesgo}"
            )
        else:
            resumen_lineas.append(
                f"- {a.asset_name} ({a.categoria}): "
                f"Tasa ref={a.tasa_referencia:.2f}%, Riesgo={a.nivel_riesgo}"
            )

    resumen_activos = "\n".join(resumen_lineas)

    prompt = (
        "Eres un asesor financiero colombiano. A partir de los siguientes activos "
        "y sus métricas, genera recomendaciones de asignación para 3 perfiles de "
        "inversor: Conservador, Moderado y Agresivo.\n\n"
        "Activos disponibles:\n"
        f"{resumen_activos}\n\n"
        "Para cada perfil:\n"
        "- Asigna porcentajes (que sumen 100%) entre los activos disponibles.\n"
        "- Justifica cada asignación brevemente.\n"
        "- Incluye una nota general para el perfil.\n"
        "- Incluye un resumen del contexto actual del mercado colombiano e internacional.\n\n"
        "IMPORTANTE: Este reporte es informativo, no constituye asesoría de inversión."
    )

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
        structured_llm = llm.with_structured_output(Recomendaciones)
        result: Recomendaciones = structured_llm.invoke(prompt)
        print(f"[orchestrator] recommend_node ✓ {len(result.perfiles)} perfiles generados")
        return {"recomendaciones": result.model_dump()}
    except Exception as e:
        print(f"[orchestrator] recommend_node ERROR: {e}")
        return {"recomendaciones": {}}


def report_node(state: ReportState) -> dict:
    """Genera el reporte HTML a partir de los AssetData acumulados."""
    from reporte.pipeline.report_generator import generate_html

    activos_data = state.get("activos_data", [])
    recomendaciones = state.get("recomendaciones", {})

    try:
        report_data = ReportData(activos=activos_data)
        report_path = generate_html(report_data, recomendaciones=recomendaciones or None)
        print(f"[orchestrator] report_node ✓ → {report_path}")
        return {"report_path": str(report_path)}
    except Exception as e:
        msg = f"[orchestrator] report_node ERROR: {e}\n{traceback.format_exc()}"
        print(msg)
        return {"report_path": "", "errores": [msg]}


# ---------------------------------------------------------------------------
# Construccion y ejecucion del grafo
# ---------------------------------------------------------------------------

def build_graph():
    """Builds the LangGraph StateGraph with conditional edges and iteration loop.

    Topology:
        scrape -> prepare_assets -> analyze_asset -+-> should_continue
                                        ^          |        |
                                        |          |   "recommend"
                                        +----------+        |
                                      "analyze_asset"  recommend -> report -> END
    """
    if not _LANGGRAPH_AVAILABLE:
        raise ImportError("langgraph no está instalado. Ejecuta: uv add langgraph")

    graph = StateGraph(ReportState)

    # Nodes
    graph.add_node("scrape", scrape_node)
    graph.add_node("prepare_assets", prepare_assets_node)
    graph.add_node("analyze_asset", analyze_single_asset_node)
    graph.add_node("recommend", recommend_node)
    graph.add_node("report", report_node)

    # Edges
    graph.set_entry_point("scrape")
    graph.add_edge("scrape", "prepare_assets")
    graph.add_edge("prepare_assets", "analyze_asset")

    # Conditional edge: iteration loop
    graph.add_conditional_edges(
        "analyze_asset",
        should_continue,
        {"analyze_asset": "analyze_asset", "recommend": "recommend"},
    )

    graph.add_edge("recommend", "report")
    graph.add_edge("report", END)

    return graph.compile()


def run_pipeline() -> ReportState:
    """Ejecuta el pipeline completo y retorna el estado final."""
    initial_state: ReportState = {
        "activos_data": [],
        "errores": [],
        "asset_keys": [],
        "current_index": 0,
        "_raw_paths": {},
        "report_path": "",
        "recomendaciones": {},
    }

    if _LANGGRAPH_AVAILABLE:
        try:
            app = build_graph()
            final_state = app.invoke(initial_state, {"recursion_limit": 25})
        except Exception as e:
            if "recursion" in str(e).lower():
                print(f"[orchestrator] GraphRecursionError: {e}")
                print("[orchestrator] Ejecutando en modo secuencial como fallback.")
                final_state = _run_sequential(initial_state)
            else:
                raise
    else:
        print("[orchestrator] langgraph no disponible, ejecutando en modo secuencial.")
        final_state = _run_sequential(initial_state)

    if final_state.get("errores"):
        print(f"\n[orchestrator] Errores registrados ({len(final_state['errores'])}):")
        for err in final_state["errores"]:
            print(f"  - {err[:200]}")

    return final_state


def _run_sequential(state: dict) -> dict:
    """Fallback: executes nodes sequentially without LangGraph."""
    # scrape
    updates = scrape_node(state)
    state = {**state, **updates}
    state["errores"] = state.get("errores", []) + updates.get("errores", [])

    # prepare_assets
    updates = prepare_assets_node(state)
    state = {**state, **updates}

    # analyze each asset
    while state["current_index"] < len(state["asset_keys"]):
        updates = analyze_single_asset_node(state)
        state["current_index"] = updates["current_index"]
        state["activos_data"] = state.get("activos_data", []) + updates.get("activos_data", [])
        state["errores"] = state.get("errores", []) + updates.get("errores", [])

    # recommend
    updates = recommend_node(state)
    state = {**state, **updates}

    # report
    updates = report_node(state)
    state = {**state, **updates}
    state["errores"] = state.get("errores", []) + updates.get("errores", [])

    return state

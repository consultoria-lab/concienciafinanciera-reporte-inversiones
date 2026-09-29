"""
Streamlit dashboard for Conciencia Financiera — Reporte Weekly Alpha.

Run with:
    uv run streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

st.set_page_config(
    page_title="Reporte Weekly Alpha",
    page_icon="📊",
    layout="wide",
)


def main():
    st.title("Reporte Weekly Alpha")
    st.caption("Conciencia Financiera — Dashboard de inversiones")

    # Sidebar
    with st.sidebar:
        st.header("Configuracion")
        skip_scraping = st.checkbox(
            "Omitir scraping (demo — usa datos de muestra)",
            help="Usa los archivos Excel mas recientes en data/downloads/ en vez de descargar nuevos.",
        )
        run_btn = st.button("Ejecutar Pipeline", type="primary", use_container_width=True)

        st.divider()
        st.markdown("**Archivos generados**")
        reports_dir = Path("reports")
        if reports_dir.exists():
            html_files = sorted(reports_dir.glob("reporte_*.html"), reverse=True)
            if html_files:
                for f in html_files[:5]:
                    st.text(f.name)
            else:
                st.text("Sin reportes generados")
        else:
            st.text("Sin directorio reports/")

    # Pipeline execution
    if run_btn:
        _execute_pipeline(skip_scraping)
    elif "final_state" in st.session_state:
        _render_results(st.session_state["final_state"])
    else:
        st.info("Presiona 'Ejecutar Pipeline' en la barra lateral para comenzar.")


def _execute_pipeline(skip_scraping: bool):
    """Run the pipeline and store results in session state."""
    with st.spinner("Ejecutando pipeline..."):
        try:
            if skip_scraping:
                final_state = _run_skip_scraping()
            else:
                from reporte.pipeline.orchestrator import run_pipeline
                final_state = run_pipeline()

            st.session_state["final_state"] = final_state
            st.success("Pipeline ejecutado correctamente.")
            _render_results(final_state)
        except Exception as e:
            st.error(f"Error en el pipeline: {e}")


def _run_skip_scraping():
    """Run pipeline skipping Playwright scraping — uses latest downloaded files."""
    from reporte.pipeline.orchestrator import (
        ReportState,
        analyze_single_asset_node,
        prepare_assets_node,
        recommend_node,
        report_node,
    )

    downloads_dir = Path("data/downloads")
    sample_dir = Path("data/sample")
    raw_paths = {}

    ca_files = sorted(downloads_dir.glob("cuentas_ahorro_*.xls*"), reverse=True)
    if not ca_files:
        ca_files = sorted(sample_dir.glob("cuentas_ahorro_*.xls*"))
    if ca_files:
        raw_paths["cuentas_ahorro"] = ca_files[0]

    cdt_files = sorted(downloads_dir.glob("cdt_*.xls*"), reverse=True)
    if not cdt_files:
        cdt_files = sorted(sample_dir.glob("cdt_*.xls*"))
    if cdt_files:
        raw_paths["cdts"] = cdt_files[0]

    state: dict = {
        "activos_data": [],
        "errores": [],
        "asset_keys": [],
        "current_index": 0,
        "_raw_paths": raw_paths,
        "report_path": "",
        "recomendaciones": {},
    }

    updates = prepare_assets_node(state)
    state = {**state, **updates}

    while state["current_index"] < len(state["asset_keys"]):
        updates = analyze_single_asset_node(state)
        state["current_index"] = updates["current_index"]
        state["activos_data"] = state.get("activos_data", []) + updates.get("activos_data", [])
        state["errores"] = state.get("errores", []) + updates.get("errores", [])

    updates = recommend_node(state)
    state = {**state, **updates}

    updates = report_node(state)
    state = {**state, **updates}
    state["errores"] = state.get("errores", []) + updates.get("errores", [])

    return state


def _render_results(final_state: dict):
    """Render pipeline results: chart, table, recommendations, download."""
    import plotly.express as px
    import pandas as pd

    activos_data = final_state.get("activos_data", [])
    errores = final_state.get("errores", [])
    report_path = final_state.get("report_path", "")
    recomendaciones = final_state.get("recomendaciones", {})

    if not activos_data:
        st.warning("No se encontraron activos para mostrar.")
        return

    # Build dataframe
    rows = []
    for a in activos_data:
        rows.append({
            "Activo": a.asset_name,
            "Categoria": a.categoria,
            "Riesgo": a.nivel_riesgo,
            "Retorno (%)": a.tasa_referencia,
        })
    df = pd.DataFrame(rows)

    # Bar chart
    st.subheader("Retorno por activo")
    risk_colors = {"Bajo": "#27ae60", "Medio": "#f39c12", "Alto": "#e74c3c"}
    fig = px.bar(
        df,
        x="Activo",
        y="Retorno (%)",
        color="Riesgo",
        color_discrete_map=risk_colors,
        title="Retorno de referencia por activo (% anual)",
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    # Data table
    st.subheader("Datos de activos")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Recommendations
    if recomendaciones and recomendaciones.get("perfiles"):
        st.subheader("Recomendaciones por perfil")
        resumen = recomendaciones.get("resumen_mercado", "")
        if resumen:
            st.info(resumen)

        cols = st.columns(len(recomendaciones["perfiles"]))
        for col, perfil in zip(cols, recomendaciones["perfiles"]):
            with col:
                st.markdown(f"**{perfil['perfil']}**")
                for asig in perfil.get("asignacion", []):
                    st.markdown(f"- **{asig['activo']}**: {asig['porcentaje']}% — {asig['razon']}")
                if perfil.get("nota"):
                    st.caption(perfil["nota"])

    # Download HTML report
    if report_path and Path(report_path).exists():
        st.divider()
        html_content = Path(report_path).read_text(encoding="utf-8")
        st.download_button(
            label="Descargar reporte HTML",
            data=html_content,
            file_name=Path(report_path).name,
            mime="text/html",
            use_container_width=True,
        )

    # Errors
    if errores:
        with st.expander(f"Errores ({len(errores)})", expanded=False):
            for err in errores:
                st.text(err[:300])


if __name__ == "__main__":
    main()

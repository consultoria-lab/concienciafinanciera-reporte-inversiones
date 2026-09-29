"""
Generador de reporte HTML.

Toma un ReportData con los AssetData de todos los activos y genera
un archivo HTML en reports/reporte_YYYYMMDD.html.

Opcionalmente incluye una seccion de recomendaciones por perfil de inversor
generada por el recommend_node del pipeline.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reporte.models import AssetData, AssetGroup, ReportData

REPORTS_DIR = Path(__file__).parents[2] / "reports"


def _render_group_table(grupo: AssetGroup) -> str:
    rows = ""
    for e in grupo.entidades:
        tasa = f"{e.tasa_activa:.2f}%" if e.tasa_activa is not None else "—"
        highlight = ' class="top-rate"' if e.tasa_activa == grupo.entidades[0].tasa_activa else ""
        rows += f"<tr{highlight}><td>{e.nombre}</td><td>{tasa}</td></tr>\n"

    rango_text = f"{grupo.rango[0]:.2f}% – {grupo.rango[1]:.2f}%"
    return f"""
    <div class="group-card">
      <h3>{grupo.nombre}</h3>
      <div class="p75-badge">P75: <strong>{grupo.percentil_75:.2f}%</strong></div>
      <div class="rango-badge">Rango: {rango_text}</div>
      <table>
        <thead><tr><th>Entidad</th><th>Tasa Activa EA</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """


def _render_asset_section(asset: AssetData) -> str:
    if asset.metricas_mercado is not None:
        if asset.metricas_mercado.get("tipo") == "fic":
            return _render_fic_section(asset)
        return _render_market_asset_section(asset)
    return _render_renta_fija_section(asset)


def _render_renta_fija_section(asset: AssetData) -> str:
    grupos_html = "".join(_render_group_table(g) for g in asset.grupos)
    corte_text = f"Corte: {asset.corte}" if asset.corte else ""
    sub_badge = f'<span class="badge subcat">{asset.subcategoria}</span>' if asset.subcategoria else ""
    return f"""
    <section class="asset-section">
      <div class="asset-header">
        <h2>{asset.asset_name}</h2>
        <span class="badge riesgo-{asset.nivel_riesgo.lower()}">{asset.nivel_riesgo} Riesgo</span>
        <span class="badge cat">{asset.categoria}</span>
        {sub_badge}
      </div>
      <div class="tasa-ref">
        Tasa de referencia (P75 global): <strong>{asset.tasa_referencia:.2f}%</strong> EA
        {"&nbsp;·&nbsp;" + corte_text if corte_text else ""}
      </div>
      <div class="groups-container">
        {grupos_html}
      </div>
      <p class="fuente">Fuente: {asset.fuente}</p>
    </section>
    """


def _render_fic_section(asset: AssetData) -> str:
    """Renderiza seccion para activos FIC (Fondos de Inversion Colectiva)."""
    m = asset.metricas_mercado
    media_pct = m["rentabilidad_media"] * 100
    vol_pct = m["volatilidad"] * 100
    r0, r1 = m["rango_1sigma"][0] * 100, m["rango_1sigma"][1] * 100
    nombre_fondo = m.get("nombre_patrimonio", "N/A")
    n_registros = m.get("n_registros", 0)
    periodo = m.get("periodo", "")
    sub_badge = f'<span class="badge subcat">{asset.subcategoria}</span>' if asset.subcategoria else ""
    sign = "+" if media_pct >= 0 else ""
    r0_sign = "+" if r0 >= 0 else ""
    r1_sign = "+" if r1 >= 0 else ""
    return f"""
    <section class="asset-section">
      <div class="asset-header">
        <h2>{asset.asset_name}</h2>
        <span class="badge riesgo-{asset.nivel_riesgo.lower()}">{asset.nivel_riesgo} Riesgo</span>
        <span class="badge cat">{asset.categoria}</span>
        {sub_badge}
      </div>
      <div class="market-metrics-strip">
        <div class="metric-tile">
          <div class="metric-label">Rentabilidad media anual</div>
          <div class="metric-value cagr">{sign}{media_pct:.2f}%</div>
          <div class="metric-sub">promedio ultimo ano</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Volatilidad (sigma)</div>
          <div class="metric-value vol">{vol_pct:.2f}%</div>
          <div class="metric-sub">desv. estandar rentabilidad anual</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Banda +/-1sigma</div>
          <div class="metric-value band">{r0_sign}{r0:.2f}% / {r1_sign}{r1:.2f}%</div>
          <div class="metric-sub">escenario tipico</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Fondo</div>
          <div class="metric-value price" style="font-size: 0.85rem;">{nombre_fondo}</div>
          <div class="metric-sub">{n_registros} registros</div>
        </div>
      </div>
      <p class="fuente">Fuente: {asset.fuente}&nbsp;·&nbsp;Periodo: {periodo}</p>
    </section>
    """


def _render_market_asset_section(asset: AssetData) -> str:
    m = asset.metricas_mercado
    cagr_pct = m["cagr"] * 100
    vol_pct = m["volatilidad"] * 100
    r0, r1 = m["rango_1sigma"][0] * 100, m["rango_1sigma"][1] * 100
    precio = m["precio_actual"]
    moneda = m.get("moneda", "USD")
    periodo = m.get("periodo", "")
    sub_badge = f'<span class="badge subcat">{asset.subcategoria}</span>' if asset.subcategoria else ""
    sign = "+" if cagr_pct >= 0 else ""
    r0_sign = "+" if r0 >= 0 else ""
    r1_sign = "+" if r1 >= 0 else ""
    return f"""
    <section class="asset-section">
      <div class="asset-header">
        <h2>{asset.asset_name}</h2>
        <span class="badge riesgo-{asset.nivel_riesgo.lower()}">{asset.nivel_riesgo} Riesgo</span>
        <span class="badge cat">{asset.categoria}</span>
        {sub_badge}
      </div>
      <div class="market-metrics-strip">
        <div class="metric-tile">
          <div class="metric-label">Retorno anualizado (CAGR)</div>
          <div class="metric-value cagr">{sign}{cagr_pct:.2f}%</div>
          <div class="metric-sub">ultimos 10 anos</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Volatilidad anualizada</div>
          <div class="metric-value vol">{vol_pct:.2f}%</div>
          <div class="metric-sub">desv. estandar diaria x sqrt(252)</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Banda 1sigma (CAGR +/- Vol)</div>
          <div class="metric-value band">{r0_sign}{r0:.2f}% / {r1_sign}{r1:.2f}%</div>
          <div class="metric-sub">escenario tipico</div>
        </div>
        <div class="metric-tile">
          <div class="metric-label">Precio actual</div>
          <div class="metric-value price">{moneda} {precio:,.2f}</div>
          <div class="metric-sub">{asset.corte}</div>
        </div>
      </div>
      <p class="fuente">Fuente: {asset.fuente}&nbsp;·&nbsp;Periodo: {periodo}</p>
    </section>
    """


def _render_recommendations_section(recomendaciones: dict) -> str:
    """Renders the recommendations section with profile cards.

    Each profile (Conservador/Moderado/Agresivo) gets a card with an
    allocation table and a summary note.
    """
    perfiles = recomendaciones.get("perfiles", [])
    resumen = recomendaciones.get("resumen_mercado", "")

    if not perfiles:
        return ""

    perfil_colors = {
        "conservador": ("#d4edda", "#155724"),
        "moderado": ("#fff3cd", "#856404"),
        "agresivo": ("#f8d7da", "#721c24"),
    }

    cards_html = ""
    for perfil in perfiles:
        nombre = perfil.get("perfil", "")
        asignaciones = perfil.get("asignacion", [])
        nota = perfil.get("nota", "")
        bg, fg = perfil_colors.get(nombre.lower(), ("#e8eaf6", "#3949ab"))

        rows = ""
        for a in asignaciones:
            rows += (
                f'<tr><td>{a["activo"]}</td>'
                f'<td><strong>{a["porcentaje"]}%</strong></td>'
                f'<td>{a["razon"]}</td></tr>\n'
            )

        cards_html += f"""
        <div class="group-card" style="margin-bottom: 16px;">
          <h3 style="background: {bg}; color: {fg};">{nombre}</h3>
          <table>
            <thead><tr><th>Activo</th><th>Asignacion</th><th>Razon</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
          <div style="padding: 10px 14px; font-size: 0.85rem; color: #555;
                      background: #fafafa; border-top: 1px solid #e0e0e0;">
            {nota}
          </div>
        </div>
        """

    resumen_html = ""
    if resumen:
        resumen_html = f"""
        <div class="tasa-ref" style="margin-bottom: 20px;">
          <strong>Contexto de mercado:</strong> {resumen}
        </div>
        """

    return f"""
    <section class="asset-section">
      <div class="asset-header">
        <h2>Recomendaciones por Perfil de Inversor</h2>
        <span class="badge cat">Asignacion Sugerida</span>
      </div>
      {resumen_html}
      <div class="groups-container">
        {cards_html}
      </div>
      <p class="fuente" style="margin-top: 14px;">
        Generado con IA (GPT-4o-mini) · No constituye asesoria de inversion
      </p>
    </section>
    """


def generate_html(
    report_data: ReportData,
    recomendaciones: dict | None = None,
) -> Path:
    """Genera el reporte HTML y retorna su Path.

    Args:
        report_data: Asset data collected by the pipeline.
        recomendaciones: Optional recommendations dict from recommend_node.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / f"reporte_{date.today().strftime('%Y%m%d')}.html"

    secciones = "".join(_render_asset_section(a) for a in report_data.activos)
    recomendaciones_html = ""
    if recomendaciones:
        recomendaciones_html = _render_recommendations_section(recomendaciones)
    generado = report_data.generado_en.strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reporte Weekly Alpha — Conciencia Financiera</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Arial, sans-serif; background: #f5f6fa; color: #222; }}

    header {{
      background: #1a1a2e;
      color: #fff;
      padding: 24px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    header h1 {{ font-size: 1.6rem; letter-spacing: 1px; }}
    header .fecha {{ font-size: 0.9rem; color: #aaa; }}

    main {{ max-width: 1100px; margin: 32px auto; padding: 0 20px; }}

    .disclaimer {{
      background: #fff3cd;
      border-left: 4px solid #ffc107;
      padding: 12px 16px;
      margin-bottom: 28px;
      font-size: 0.85rem;
      color: #555;
    }}

    .asset-section {{
      background: #fff;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 28px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.07);
    }}
    .asset-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .asset-header h2 {{ font-size: 1.3rem; color: #1a1a2e; }}
    .badge {{
      padding: 3px 10px;
      border-radius: 12px;
      font-size: 0.78rem;
      font-weight: bold;
    }}
    .badge.riesgo-bajo {{ background: #d4edda; color: #155724; }}
    .badge.riesgo-medio {{ background: #fff3cd; color: #856404; }}
    .badge.riesgo-alto {{ background: #f8d7da; color: #721c24; }}
    .badge.cat {{ background: #e8eaf6; color: #3949ab; }}
    .badge.subcat {{ background: #fce4ec; color: #880e4f; }}

    .market-metrics-strip {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 14px;
    }}
    .metric-tile {{
      background: #f8f9ff;
      border: 1px solid #e0e4f0;
      border-radius: 8px;
      padding: 14px 16px;
      text-align: center;
    }}
    .metric-label {{ font-size: 0.75rem; color: #888; margin-bottom: 6px; }}
    .metric-value {{ font-size: 1.25rem; font-weight: bold; }}
    .metric-value.cagr {{ color: #1a73e8; }}
    .metric-value.vol {{ color: #e67e22; }}
    .metric-value.band {{ color: #555; font-size: 1rem; }}
    .metric-value.price {{ color: #1a1a2e; }}
    .metric-sub {{ font-size: 0.72rem; color: #aaa; margin-top: 4px; }}

    .tasa-ref {{
      font-size: 1rem;
      color: #444;
      margin-bottom: 20px;
      padding: 10px 14px;
      background: #e8f4fd;
      border-radius: 6px;
      border-left: 3px solid #1a73e8;
    }}
    .tasa-ref strong {{ color: #1a73e8; font-size: 1.1rem; }}

    .groups-container {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }}
    .group-card {{
      border: 1px solid #e0e0e0;
      border-radius: 6px;
      overflow: hidden;
    }}
    .group-card h3 {{
      background: #1a1a2e;
      color: #fff;
      padding: 10px 14px;
      font-size: 0.95rem;
    }}
    .p75-badge {{
      background: #e8f4fd;
      padding: 6px 14px;
      font-size: 0.85rem;
      color: #1a73e8;
      border-bottom: 1px solid #e0e0e0;
    }}
    .rango-badge {{
      background: #f5f5f5;
      padding: 4px 14px;
      font-size: 0.8rem;
      color: #666;
      border-bottom: 1px solid #e0e0e0;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
    thead tr {{ background: #f5f6fa; }}
    th, td {{ padding: 8px 14px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
    tr.top-rate td {{ font-weight: bold; color: #155724; background: #f0fff4; }}
    tr:hover td {{ background: #fafafa; }}

    .fuente {{ font-size: 0.78rem; color: #999; margin-top: 14px; }}

    footer {{
      text-align: center;
      padding: 24px;
      font-size: 0.8rem;
      color: #999;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Reporte Weekly Alpha - Conciencia Financiera</h1>
    <span class="fecha">Generado: {generado}</span>
  </header>

  <main>
    <div class="disclaimer">
      <strong>Aviso legal:</strong> Este reporte es de caracter informativo y no constituye
      una recomendacion de inversion. La informacion proviene de fuentes publicas (Superintendencia
      Financiera de Colombia). Consulte con un asesor financiero certificado antes de tomar
      decisiones de inversion.
    </div>

    {secciones}

    {recomendaciones_html}
  </main>

  <footer>
    Conciencia Financiera - Medellin, Colombia - Informacion de caracter publico
  </footer>
</body>
</html>"""

    output_path.write_text(html, encoding="utf-8")
    return output_path

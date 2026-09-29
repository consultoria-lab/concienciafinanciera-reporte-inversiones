"""
Conciencia Financiera — Reporte Weekly Alpha
Entry point principal.

Uso:
    uv run main.py                   # Pipeline completo (scrape + analyze + report)
    uv run main.py --analyze-only    # Solo analiza el Excel más reciente (sin Playwright)
    uv run main.py --test-analyzer   # Prueba el analyzer con el Excel de contexto/
    uv run main.py --test-fic        # Prueba activos FIC datos.gov.co (Factoring, Deuda Corp.)
"""
import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Conciencia Financiera — Reporte Weekly Alpha")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Analiza el Excel más reciente sin descargar (sin Playwright)")
    parser.add_argument("--test-analyzer", action="store_true",
                        help="Prueba el analyzer con contexto/CuentaAhorroPersonaNatural.xls")
    parser.add_argument("--test-cdt", action="store_true",
                        help="Prueba el analyzer CDT con contexto/CDT (2).xls")
    parser.add_argument("--test-market", action="store_true",
                        help="Prueba todos los activos yfinance (SPY, GLD, WTI, USDCOP, BTC)")
    parser.add_argument("--test-fic", action="store_true",
                        help="Prueba los activos FIC datos.gov.co (Factoring, Deuda Corporativa)")
    args = parser.parse_args()

    if args.test_analyzer:
        _test_analyzer()
    elif args.test_cdt:
        _test_cdt()
    elif args.test_market:
        _test_market()
    elif args.test_fic:
        _test_fic()
    elif args.analyze_only:
        _run_analyze_only()
    else:
        _run_full_pipeline()


def _run_full_pipeline():
    """Ejecuta el pipeline completo: scrape → analyze → report."""
    from reporte.pipeline.orchestrator import run_pipeline
    print("=" * 60)
    print("Conciencia Financiera · Reporte Weekly Alpha")
    print("=" * 60)
    final_state = run_pipeline()
    report_path = final_state.get("report_path", "")
    if report_path:
        print(f"\nReporte generado: {report_path}")
    else:
        print("\nNo se pudo generar el reporte. Revisa los errores arriba.")
        sys.exit(1)


def _run_analyze_only():
    """Analiza el Excel descargado más reciente sin usar Playwright."""
    from reporte.assets.cuentas_ahorro.analyzer import analyze

    downloads_dir = Path("data/downloads")
    sample_dir = Path("data/sample")
    excel_files = sorted(downloads_dir.glob("cuentas_ahorro_*.xls*"), reverse=True)
    if not excel_files:
        excel_files = sorted(sample_dir.glob("cuentas_ahorro_*.xls*"))

    if not excel_files:
        print("No hay archivos en data/downloads/ ni data/sample/. Ejecuta sin --analyze-only primero.")
        sys.exit(1)

    latest = excel_files[0]
    print(f"Analizando: {latest.name}")
    result = analyze(latest)
    _print_result(result)

    # Generar reporte HTML
    from reporte.models import AssetData, AssetGroup, Entidad, ReportData
    from reporte.pipeline.report_generator import generate_html

    grupos = [
        AssetGroup(
            nombre=g["nombre"],
            entidades=[Entidad(e["nombre"], e["tasa_activa"], e.get("tasa_inactiva")) for e in g["entidades"]],
            percentil_75=g["percentil_75"],
            rango=tuple(g.get("rango", [0.0, 0.0])),
        )
        for g in result["grupos"]
    ]
    asset_data = AssetData("Cuentas de Ahorro", "Renta Fija", "Bajo",
                           result["tasa_referencia_global"], grupos,
                           fuente="Superintendencia Financiera de Colombia",
                           corte=result.get("corte", ""))
    report_path = generate_html(ReportData(activos=[asset_data]))
    print(f"\nReporte generado: {report_path}")


def _test_analyzer():
    """Prueba rápida con el Excel de referencia en contexto/."""
    from reporte.assets.cuentas_ahorro.analyzer import analyze

    test_file = Path("contexto/CuentaAhorroPersonaNatural.xls")
    if not test_file.exists():
        print(f"No encontrado: {test_file}")
        sys.exit(1)

    print(f"Probando analyzer con: {test_file.name}\n")
    result = analyze(test_file)
    _print_result(result)


def _test_market():
    """Prueba los 5 activos yfinance: SPY, GLD, WTI, USDCOP, BTC."""
    import importlib
    assets = ["spy", "gld", "wti", "usdcop", "btc"]
    print("Probando activos de mercado (yfinance)...\n")
    for key in assets:
        try:
            module = importlib.import_module(f"reporte.assets.{key}.analyzer")
            asset = module.analyze()
            m = asset.metricas_mercado
            rango = m["rango_1sigma"]
            print(
                f"  [{asset.asset_name}]  CAGR: {asset.tasa_referencia:+.2f}%"
                f"  Vol: {m['volatilidad']*100:.2f}%"
                f"  Banda: {rango[0]*100:+.2f}% / {rango[1]*100:+.2f}%"
                f"  Precio: {m['moneda']} {m['precio_actual']:,.2f}"
                f"  ({m['periodo']})"
            )
        except Exception as e:
            print(f"  [{key}] ERROR: {e}")
    print()


def _test_fic():
    """Prueba los 2 activos FIC datos.gov.co: Factoring y Deuda Corporativa."""
    import importlib
    assets = ["factoring", "deuda_corporativa"]
    print("Probando activos FIC (datos.gov.co)...\n")
    for key in assets:
        try:
            module = importlib.import_module(f"reporte.assets.{key}.analyzer")
            asset = module.analyze()
            m = asset.metricas_mercado
            rango = m["rango_1sigma"]
            print(
                f"  [{asset.asset_name}]  Media: {asset.tasa_referencia:+.2f}%"
                f"  Vol: {m['volatilidad']*100:.2f}%"
                f"  Banda: {rango[0]*100:+.2f}% / {rango[1]*100:+.2f}%"
                f"  Fondo: {m['nombre_patrimonio']}"
                f"  ({m['n_registros']} registros, {m['periodo']})"
            )
        except Exception as e:
            print(f"  [{key}] ERROR: {e}")
    print()


def _test_cdt():
    """Prueba rápida del analyzer CDT con el Excel de referencia en contexto/."""
    from reporte.assets.cdts.analyzer import analyze

    test_file = Path("contexto/CDT (2).xls")
    if not test_file.exists():
        print(f"No encontrado: {test_file}")
        sys.exit(1)

    print(f"Probando analyzer CDT con: {test_file.name}\n")
    result = analyze(test_file)
    _print_result(result)


def _print_result(result: dict):
    print(f"Corte: {result.get('corte', 'N/A')}")
    print(f"Tasa de referencia global (P75): {result['tasa_referencia_global']:.2f}%\n")
    for g in result["grupos"]:
        rango = g.get("rango", [0.0, 0.0])
        print(f"  [{g['nombre']}] P75: {g['percentil_75']:.2f}%  Rango: {rango[0]:.2f}% – {rango[1]:.2f}%  ({len(g['entidades'])} entidades)")
        for e in g["entidades"][:3]:
            tasa = f"{e['tasa_activa']:.2f}%" if e['tasa_activa'] else "—"
            print(f"    · {e['nombre']}: {tasa}")
        if len(g["entidades"]) > 3:
            print(f"    ... y {len(g['entidades']) - 3} más")
        print()


if __name__ == "__main__":
    main()

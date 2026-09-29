"""
Scraper para CDT — Superintendencia Financiera de Colombia.

Descarga el reporte Excel de tasas de CDT navegando el portal de la
Superfinanciera con Playwright. Misma URL que Cuentas de Ahorro, pero
selecciona el producto "CDT".
"""
import shutil
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

DOWNLOADS_DIR = Path(__file__).parents[3] / "data" / "downloads"
SOURCE_URL = (
    "https://www.superfinanciera.gov.co"
    "/Superfinanciera-Tasas/faces/generic/passiveInterestRates.xhtml"
)


def _target_path() -> Path:
    """Retorna el path destino con fecha de hoy, sin re-descargar si ya existe."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return DOWNLOADS_DIR / f"cdt_{date.today().strftime('%Y%m%d')}.xls"


def download_excel(headless: bool = True) -> Path:
    """
    Navega al portal de Superfinanciera, selecciona 'CDT'
    y descarga el Excel de tasas. Retorna el Path del archivo descargado.

    Es idempotente: si el archivo de hoy ya existe, lo retorna sin re-descargar.
    """
    target = _target_path()
    if target.exists():
        print(f"[cdts] Archivo ya descargado: {target.name}")
        return target

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        print(f"[cdts] Navegando a Superfinanciera...")
        page.goto(SOURCE_URL, wait_until="networkidle", timeout=30_000)

        # El portal usa PrimeFaces tabs. El tab CDT está oculto por defecto;
        # hay que activarlo primero para que el botón sea visible y clickeable.
        page.get_by_text("Certificado de depósito a término (CDT)", exact=False).click()
        page.wait_for_load_state("networkidle", timeout=15_000)

        with page.expect_download(timeout=30_000) as download_info:
            page.locator("button[id*='PreferentialCreditForm']").filter(has_text="Excel").click()
        download = download_info.value

        tmp_path = Path(download.path())
        shutil.copy(tmp_path, target)
        browser.close()

    print(f"[cdts] Descargado: {target.name}")
    return target

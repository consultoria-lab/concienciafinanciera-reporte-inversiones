# Conciencia Financiera — Reporte Weekly Alpha

## Ejecucion

```bash
# Pipeline completo (scrape Playwright + yfinance + datos.gov.co + reporte HTML)
uv run main.py

# Solo analizar el Excel de cuentas de ahorro mas reciente (sin Playwright)
uv run main.py --analyze-only

# Probar analyzer cuentas de ahorro con Excel de contexto/
uv run main.py --test-analyzer

# Probar analyzer CDT con Excel de contexto/
uv run main.py --test-cdt

# Probar activos de mercado yfinance (SPY, GLD, WTI, USDCOP, BTC)
uv run main.py --test-market

# Probar activos FIC datos.gov.co (Factoring, Deuda Corporativa)
uv run main.py --test-fic
```

## Variables de entorno

Crear un archivo `.env` en la raiz del proyecto:

```
DATOS_GOV_API_KEY=tu_api_key
DATOS_GOV_API_SECRET=tu_api_secret
```

Las keys se obtienen en https://www.datos.gov.co/ (registro gratuito).

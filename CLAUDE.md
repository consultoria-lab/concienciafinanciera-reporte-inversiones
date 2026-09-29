# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Conciencia Financiera** — an automated investment report generator for the Colombian market. Produces a weekly HTML report ("Reporte Weekly Alpha") covering 9 asset classes across fixed income, equities, alternatives, forex, and digital assets.

Python 3.12, managed with `uv`. User-facing report content and domain terminology are in **Spanish**. Code comments and docstrings are mixed Spanish/English.

## Commands

```bash
# Full pipeline (Playwright scrape + analyze + recommend + HTML report)
uv run main.py

# Test yfinance analyzers only (no Playwright, no API keys needed)
uv run main.py --test-market

# Test FIC analyzers (datos.gov.co — works without API keys)
uv run main.py --test-fic

# Test cuentas de ahorro analyzer with reference Excel in contexto/
uv run main.py --test-analyzer

# Test CDT analyzer with reference Excel in contexto/
uv run main.py --test-cdt

# Analyze latest downloaded Excel without re-scraping
uv run main.py --analyze-only

# Streamlit dashboard
uv run streamlit run app.py

# Sync dependencies
uv sync
```

## Architecture

LangGraph `StateGraph` pipeline with conditional edges and an iteration loop:

```
scrape -> prepare_assets -> analyze_asset --+--> should_continue
                                 ^          |         |
                                 |          |    "recommend"
                                 +-----------+        |
                              "analyze_asset"   recommend -> report -> END
```

- **`ReportState`** uses `Annotated[list, operator.add]` reducers on `activos_data` and `errores` — nodes return only new elements, LangGraph accumulates. All other state fields (`asset_keys`, `current_index`, `_raw_paths`, etc.) are overwritten on each update.
- **`should_continue`** is a conditional edge that loops `analyze_asset` until all assets are processed, then routes to `recommend`.
- **`recommend_node`** uses `ChatOpenAI.with_structured_output(Recomendaciones)` for typed LLM output. Degrades gracefully without `OPENAI_API_KEY`.
- **Fallback**: if LangGraph is unavailable or `GraphRecursionError` occurs, `_run_sequential()` replicates the graph topology manually.

## Three Analyzer Archetypes

Every asset uses one of three patterns. The archetype determines the analyzer signature, config schema, and how the orchestrator handles the return value.

### A. yfinance-based (spy, gld, wti, usdcop, btc)

- **Signature:** `analyze() -> AssetData`
- **Config keys:** `ticker`, `moneda`, `years`, `asset_name`, `categoria`, `nivel_riesgo`, `fuente`
- **Base module:** `yfinance_base.fetch_metrics(ticker, years)` — returns dict with `cagr`, `volatilidad`, `precio_actual`, `rango_1sigma`, `periodo`, `n_dias`
- `tasa_referencia` = CAGR × 100 (decimal to percentage)
- `metricas_mercado` = metrics dict merged with `{"moneda": config["moneda"]}`

### B. datos.gov.co FIC-based (factoring, deuda_corporativa)

- **Signature:** `analyze() -> AssetData`
- **Config keys:** `codigo_negocio`, `tipo_participacion`, `years`, `asset_name`, `categoria`, `nivel_riesgo`, `fuente`
- **Base module:** `datosgovco_base.fetch_fic_metrics()` — returns dict with `rentabilidad_media`, `nombre_patrimonio`, and critically `"tipo": "fic"` (used as rendering discriminator)
- `tasa_referencia` = `rentabilidad_media` × 100

### C. Renta Fija / Excel-scraped (cuentas_ahorro, cdts)

- **Signature:** `analyze(file_path: Path) -> dict` — returns raw dict, NOT `AssetData`
- **Config keys:** `nombre`, `categoria`, `nivel_riesgo`, `fuente`, `fuente_url`, `columna_referencia`, `percentil`, `clasificacion`
- Requires a downloaded Excel file as input (from Playwright scraper)
- The orchestrator converts the dict to `AssetData` via `_build_asset_data_from_result()`
- Has dual-mode: ReAct agent (with `OPENAI_API_KEY`) or direct `parse_excel()` fallback
- Includes `scraper.py` (Playwright) and `skill.md` (LLM prompt) files

## Asset Registration

Assets are registered in `orchestrator.py` via four constants:

```python
_ALL_ASSET_KEYS = ["cuentas_ahorro", "cdts", "spy", "gld", "wti", "usdcop", "btc", "factoring", "deuda_corporativa"]
_YFINANCE_ASSETS = {"spy", "gld", "wti", "usdcop", "btc"}
_DATOSGOVCO_ASSETS = {"factoring", "deuda_corporativa"}
_RENTA_FIJA_ASSETS = {"cuentas_ahorro", "cdts"}
```

The orchestrator uses these sets to determine how to call each analyzer and how to handle the return value. Asset directory names must match the key (used for `importlib.import_module(f"reporte.assets.{key}.analyzer")`).

### Adding a yfinance asset (e.g., QQQ)

1. Create `reporte/assets/qqq/` with `__init__.py`, `config.yaml`, `analyzer.py` (copy from `spy/`, change log tag)
2. Add `"qqq"` to `_ALL_ASSET_KEYS` (position = report order) and `_YFINANCE_ASSETS` in orchestrator.py
3. No changes needed in models.py, report_generator.py, or app.py

### Adding a datos.gov.co FIC asset

Same as above but config needs `codigo_negocio`/`tipo_participacion` instead of `ticker`/`moneda`, and register in `_DATOSGOVCO_ASSETS`.

## Rendering Dispatch

`report_generator.py` dispatches HTML rendering based on `AssetData.metricas_mercado`:

```python
if metricas_mercado is None:        -> _render_renta_fija_section()   # groups, P75, entity tables
elif metricas_mercado["tipo"] == "fic": -> _render_fic_section()      # rentabilidad, fund name
else:                               -> _render_market_asset_section() # CAGR, volatility, price
```

The `"tipo": "fic"` key set by `datosgovco_base` is the discriminator between FIC and yfinance rendering.

## Degradation Matrix

| Component | Full Mode | Degraded Mode | Trigger |
|-----------|-----------|---------------|---------|
| Pipeline | LangGraph StateGraph | `_run_sequential()` manual loop | `langgraph` not installed or `GraphRecursionError` |
| Renta fija analyzer | ReAct agent + structured output | Direct `parse_excel()` | No `OPENAI_API_KEY` or agent exception |
| Recommendations | GPT-4o-mini structured output | Section omitted from report | No `OPENAI_API_KEY` or import/call error |
| Scraping | Playwright downloads Excel | Renta fija assets excluded from report | Playwright failure |
| Individual asset | `AssetData` added to report | Error logged to `errores`, asset skipped | Any analyzer exception |

## Key Conventions

- **Percentage scale:** Base modules (`yfinance_base`, `datosgovco_base`) return values in decimal (0.08 = 8%). Analyzers multiply by 100 for `tasa_referencia`. Renta fija values from Excel are already in percentage scale.
- **Lazy imports:** Heavy dependencies (yfinance, playwright, langchain_openai) are imported inside function bodies or `try/except` blocks. This ensures test modes don't pull in unneeded dependencies.
- **Error isolation:** Each asset analyzer failure is caught individually, logged to `errores`, and `current_index` is incremented. One asset failing never stops the pipeline.
- **`metricas_mercado` is untyped:** It's `dict | None` with different key sets depending on the data source. No schema validation — the renderer must know which keys to expect.
- **Scrapers are idempotent:** `download_excel()` checks if today's file exists and skips re-downloading. Pattern: `cuentas_ahorro_YYYYMMDD.xls`.
- **Streamlit `_run_skip_scraping()`** duplicates `_run_sequential()` logic from the orchestrator — both must be updated together if node signatures change.

## Environment Variables

```
OPENAI_API_KEY=sk-...           # Optional: enables ReAct agents + recommend_node
DATOS_GOV_API_KEY=...           # Optional: higher rate limits for datos.gov.co
DATOS_GOV_API_SECRET=...
```

Without `OPENAI_API_KEY` the pipeline runs fully — analyzers use direct Python parsing and recommendations are skipped.

## Gitignored Directories

`data/downloads/`, `reports/`, `backup/`, `contexto/` — scraped files, generated reports, and reference documents are local-only. The `--test-analyzer` and `--test-cdt` modes expect reference Excel files in `contexto/`.

## Domain Notes

- CDT = Certificado de Deposito a Termino (Colombian fixed-term deposit)
- COP = Colombian Peso; report handles both COP and USD denominated assets
- Fogafin = Colombia's deposit insurance (covers up to $50M COP per bank)
- FIC = Fondo de Inversion Colectiva (collective investment fund)
- P75 = percentile 75 reference rate for fixed income assets
- The report must include a prominent disclaimer (Superintendencia Financiera compliance)

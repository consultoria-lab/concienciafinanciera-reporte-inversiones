# Investment Report Generator — Weekly Alpha

> **Disclaimer:** This is an adapted version for portfolio purposes. The original project is a shared venture where I serve as the developer and analytics lead.

Automated investment report pipeline for the Colombian market. Scrapes financial data from regulatory sources and market APIs, analyzes 9 asset classes, generates allocation recommendations via LLM, and produces a styled HTML report.

## LangGraph Architecture

```
scrape ──> prepare_assets ──> analyze_asset ──+──> should_continue
                                  ^           |         |
                                  |           |    "recommend"
                                  +-----------+         |
                               "analyze_asset"    recommend ──> report ──> END
```

The pipeline uses a **conditional edge loop** (`should_continue`) to iterate over assets one at a time, accumulating results via **Annotated reducers**. After all assets are processed, the `recommend` node uses **structured output** (`with_structured_output`) to generate typed allocation recommendations.

## LangChain / LangGraph Patterns Demonstrated

| Pattern | Where |
|---------|-------|
| `StateGraph` with typed state | `orchestrator.py` — `ReportState(TypedDict)` |
| `Annotated` reducers (`operator.add`) | `ReportState.activos_data`, `ReportState.errores` |
| Conditional edges | `should_continue` — routes to loop or next stage |
| Iteration loop | `analyze_asset` node processes one asset per cycle |
| `@tool` decorated functions | `tools.py` — `fetch_yfinance_data`, `fetch_datosgovco_data`, `compare_assets_benchmark` |
| ReAct agents (`create_react_agent`) | `cuentas_ahorro/analyzer.py`, `cdts/analyzer.py` |
| `with_structured_output` (Pydantic) | `recommend_node` — `Recomendaciones` model |
| Graceful degradation | Falls back to direct analysis without `OPENAI_API_KEY` |
| `GraphRecursionError` handling | `run_pipeline` — catches recursion limit and falls back to sequential |

## Quick Start

```bash
# Install dependencies
uv sync

# Run full pipeline (scrape + analyze + report)
uv run main.py

# Test market analyzers only (no Playwright needed)
uv run main.py --test-market

# Test FIC analyzers (datos.gov.co)
uv run main.py --test-fic

# Launch Streamlit dashboard
uv run streamlit run app.py
```

## Environment Variables

Create a `.env` file in the project root:

```
# Optional — enables LLM-based analysis and recommendations
OPENAI_API_KEY=sk-...

# Optional — higher rate limits for datos.gov.co API
DATOS_GOV_API_KEY=your_key
DATOS_GOV_API_SECRET=your_secret
```

Without `OPENAI_API_KEY`, the pipeline runs in direct mode (pure Python analysis, no recommendations).

## Project Structure

```
.
├── main.py                          # CLI entry point
├── app.py                           # Streamlit dashboard
├── pyproject.toml                   # Dependencies (uv)
├── reporte/
│   ├── models.py                    # Pydantic + dataclass models
│   ├── tools.py                     # @tool definitions for LangChain agents
│   ├── pipeline/
│   │   ├── orchestrator.py          # LangGraph StateGraph pipeline
│   │   └── report_generator.py      # HTML report renderer
│   └── assets/
│       ├── yfinance_base.py         # Shared yfinance fetch logic
│       ├── datosgovco_base.py       # Shared datos.gov.co fetch logic
│       ├── cuentas_ahorro/          # Savings accounts (Superfinanciera)
│       ├── cdts/                    # Fixed-term deposits (Superfinanciera)
│       ├── spy/                     # S&P 500 (yfinance)
│       ├── gld/                     # Gold (yfinance)
│       ├── wti/                     # Crude oil (yfinance)
│       ├── usdcop/                  # USD/COP exchange rate (yfinance)
│       ├── btc/                     # Bitcoin (yfinance)
│       ├── factoring/               # Factoring FIC (datos.gov.co)
│       └── deuda_corporativa/       # Corporate debt FIC (datos.gov.co)
├── data/downloads/                  # Scraped Excel files (gitignored)
└── reports/                         # Generated HTML reports (gitignored)
```

## Asset Classes

| Asset | Source | Category | Risk |
|-------|--------|----------|------|
| Cuentas de Ahorro | Superfinanciera (Playwright) | Fixed Income | Low |
| CDT | Superfinanciera (Playwright) | Fixed Income | Low |
| S&P 500 (SPY) | Yahoo Finance | Equities | High |
| Gold (GLD) | Yahoo Finance | Alternatives | Medium |
| Crude Oil (WTI) | Yahoo Finance | Alternatives | High |
| USD/COP | Yahoo Finance | Forex | Medium |
| Bitcoin (BTC) | Yahoo Finance | Digital Assets | High |
| Factoring | datos.gov.co | Alternative Credit | Medium |
| Corporate Debt | datos.gov.co | Alternative Credit | Medium |

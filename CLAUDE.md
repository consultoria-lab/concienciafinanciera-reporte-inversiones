# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Conciencia Financiera** — an automated investment report generator for the Colombian market. The system produces a weekly PDF report ("Reporte Weekly Alpha") with asset allocation guidance across 8 asset classes: Renta Fija (CDTs), Real Estate, Factoring/Deuda, Alternativos, Divisas (USD/COP), Mercados Internacionales (ETFs), Digital Assets (BTC/ETH), and Venture Capital.

The project is in early-stage scaffolding (Python 3.12, `uv` managed). The primary language is **Spanish** — all report content, user-facing text, and domain terminology should remain in Spanish.

## Commands

```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Run the application
uv run main.py

# Add dependencies
uv add <package>

# Sync dependencies from pyproject.toml
uv sync
```

## Architecture (Planned)

Per `contexto/objetivo.md`, the target architecture is:

- **Orchestration:** LangGraph agentic workflow for consistent multi-section report generation
- **Data extraction:** Playwright for web scraping; APIs (Firecrawl, Tavily) for real-time data; `yfinance` for international markets (SPY, GLD, oil)
- **Data processing:** Excel/xlsx parsing for CDT rates, percentile segmentation, asset classification
- **Persistence:** Supabase for historical yield time series
- **Output:** PDF report with yield curve chart, investment matrix table, and narrative market analysis per category

## Key Context Files

- `contexto/objetivo.md` — Strategic vision document defining all asset classes, data sources, report structure, and the full technical pipeline
- `contexto/reporte_inversiones_ejecutivo_20260223.pdf` — Reference PDF showing the target report format (yield curve chart, comparison tables, risk/return analysis)
- `contexto/reporte_inversiones_20260307.html` — HTML version of the investment report
- `contexto/reporte_curva_20260227_172852.html` — Yield curve report in HTML

## Domain Notes

- CDT = Certificado de Depósito a Término (Colombian fixed-term deposit)
- COP = Colombian Peso; report handles both COP and USD denominated assets
- Fogafín = Colombia's deposit insurance (covers up to $50M COP per bank)
- Asset risk levels: Bajo (low), Medio (medium), Alto (high)
- Benchmark for CDTs: percentile 70 at 180-day term
- The report must include a prominent "No es recomendación de inversión" disclaimer (Superintendencia Financiera compliance)

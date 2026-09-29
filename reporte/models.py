from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Entidad:
    nombre: str
    tasa_activa: float | None
    tasa_inactiva: float | None = None


@dataclass
class AssetGroup:
    nombre: str
    entidades: list[Entidad] = field(default_factory=list)
    percentil_75: float = 0.0
    rango: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    # rango = (tasa_min, tasa_max) de entidades con tasa_activa > 0

    @property
    def tasa_referencia(self) -> float:
        return self.percentil_75


@dataclass
class AssetData:
    asset_name: str
    categoria: str
    nivel_riesgo: str  # Bajo / Medio / Alto
    tasa_referencia: float  # P75 (Renta Fija) o CAGR×100 (mercados)
    grupos: list[AssetGroup] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    fuente: str = ""
    corte: str = ""  # Fecha de corte del dato, e.g. "2026-03-12"
    subcategoria: str = ""  # e.g. "Mercados Internacionales", "Divisas"
    metricas_mercado: dict | None = None
    # Para activos yfinance. Keys:
    #   precio_actual, cagr, volatilidad, rango_1sigma, periodo, moneda, ticker


@dataclass
class ReportData:
    activos: list[AssetData] = field(default_factory=list)
    generado_en: datetime = field(default_factory=datetime.now)
    version: str = "1.0"

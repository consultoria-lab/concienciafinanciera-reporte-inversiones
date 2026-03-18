"""
Analyzer para CDT (Certificado de Depósito a Término).

Implementa un LangGraph ReAct agent (GPT-4o-mini) que lee el Excel de Superfinanciera,
clasifica las entidades en 3 grupos y calcula el percentil 75 de la tasa "A 180 días"
como tasa de referencia.

Diferencia clave vs. Cuentas de Ahorro: el Excel de CDT tiene UNA fila por entidad,
no filas en pares. La columna de referencia es la 12 (índice 0-based): "A 180 días".

Para usar el agente se requiere OPENAI_API_KEY en el entorno.
Si no está disponible, se ejecuta el análisis en modo directo (sin LLM).
"""
import json
import os
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel

warnings.filterwarnings("ignore")

_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_SKILL_PATH = Path(__file__).parent / "skill.md"

# Importaciones lazy para LangChain/LangGraph (opcionales)
try:
    from langchain_openai import ChatOpenAI
    from langchain.tools import tool
    from langgraph.prebuilt import create_react_agent
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False


# ---------------------------------------------------------------------------
# Modelos Pydantic para structured output del agente
# ---------------------------------------------------------------------------

class _EntidadOutput(BaseModel):
    nombre: str
    tasa_activa: float | None = None
    tasa_inactiva: float | None = None


class _AssetGroupOutput(BaseModel):
    nombre: str
    percentil_75: float
    rango: tuple[float, float]
    entidades: list[_EntidadOutput]


class ExtractionOutput(BaseModel):
    corte: str
    tasa_referencia_global: float
    grupos: list[_AssetGroupOutput]


# ---------------------------------------------------------------------------
# Lógica de análisis pura
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _parse_tasa(val) -> float | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    s = str(val).strip()
    if s in ("---", "", "nan"):
        return None
    try:
        return float(s.replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None


def _classify_entity(nombre: str, clasificacion: dict) -> str:
    nombre_lower = nombre.lower()
    for keyword in clasificacion.get("neobancos", []):
        if keyword.lower() in nombre_lower:
            return "Neobancos"
    for keyword in clasificacion.get("cfcs_cooperativas", []):
        if keyword.lower() in nombre_lower:
            return "CFCs / Cooperativas"
    return "Bancos Tradicionales"


def parse_excel(file_path: Path) -> dict:
    """
    Parsea el Excel de CDT de Superfinanciera.
    Retorna un dict con la estructura definida en skill.md.

    Estructura del Excel:
    - Fila 0: encabezado con fecha de corte
    - Fila 3: headers de columnas
    - Filas 4+: una fila por entidad (col 1=nombre, col 12=tasa A 180 días)
    """
    config = _load_config()
    clasificacion = config["clasificacion"]

    df = pd.read_excel(file_path, sheet_name=0, header=None)

    # Extraer fecha de corte desde fila 0
    corte = ""
    header_text = str(df.iloc[0, 1]) if len(df) > 0 else ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", header_text)
    if match:
        corte = match.group(0)

    # Parsear una fila por entidad (a partir de fila 4)
    groups_data: dict[str, list[dict]] = {
        "Neobancos": [],
        "Bancos Tradicionales": [],
        "CFCs / Cooperativas": [],
    }

    for i in range(4, len(df)):
        nombre_raw = df.iloc[i, 1]
        if pd.isna(nombre_raw):
            continue
        nombre = str(nombre_raw).strip().strip('"').replace("\n", " ").strip()
        if not nombre or nombre.startswith("¿"):  # excluir disclaimer final
            continue

        tasa = _parse_tasa(df.iloc[i, 12])  # col 12 = "A 180 días"

        grupo = _classify_entity(nombre, clasificacion)
        groups_data[grupo].append({
            "nombre": nombre,
            "tasa_activa": tasa,
            "tasa_inactiva": None,
        })

    # Ordenar por tasa desc dentro de cada grupo
    for grupo_list in groups_data.values():
        grupo_list.sort(key=lambda e: e["tasa_activa"] or 0.0, reverse=True)

    # Calcular P75 y rango por grupo (solo tasas > 0)
    resultado_grupos = []
    all_tasas = []
    for nombre_grupo, entidades in groups_data.items():
        tasas = [e["tasa_activa"] for e in entidades if e["tasa_activa"] and e["tasa_activa"] > 0]
        all_tasas.extend(tasas)
        p75 = float(np.percentile(tasas, 75)) if tasas else 0.0
        rango = [round(min(tasas), 2), round(max(tasas), 2)] if tasas else [0.0, 0.0]
        resultado_grupos.append({
            "nombre": nombre_grupo,
            "percentil_75": round(p75, 2),
            "rango": rango,
            "entidades": entidades,
        })

    tasa_global = float(np.percentile(all_tasas, 75)) if all_tasas else 0.0

    return {
        "corte": corte,
        "tasa_referencia_global": round(tasa_global, 2),
        "grupos": resultado_grupos,
    }


# ---------------------------------------------------------------------------
# Tools para el ReAct agent
# ---------------------------------------------------------------------------

def _make_tools(file_path: Path):
    @tool
    def read_and_parse_excel(path: str) -> str:
        """Lee el Excel de CDT de Superfinanciera y extrae entidades con sus tasas A 180 días.
        Input: path absoluto al archivo .xls/.xlsx"""
        result = parse_excel(Path(path))
        summary = {
            "corte": result["corte"],
            "grupos": [
                {
                    "nombre": g["nombre"],
                    "n_entidades": len(g["entidades"]),
                    "tasas_activas": [
                        {"nombre": e["nombre"], "tasa": e["tasa_activa"]}
                        for e in g["entidades"]
                        if e["tasa_activa"] is not None
                    ],
                }
                for g in result["grupos"]
            ],
        }
        return json.dumps(summary, ensure_ascii=False, indent=2)

    @tool
    def calculate_percentile(tasas_json: str, percentil: int = 75) -> str:
        """Calcula el percentil de una lista de tasas.
        Input: JSON string con lista de floats, e.g. '[11.12, 12.44, 10.00]'"""
        tasas = [t for t in json.loads(tasas_json) if t and t > 0]
        if not tasas:
            return "0.0"
        return str(round(float(np.percentile(tasas, percentil)), 2))

    return [read_and_parse_excel, calculate_percentile]


# ---------------------------------------------------------------------------
# Punto de entrada principal
# ---------------------------------------------------------------------------

def analyze(file_path: Path) -> dict:
    """
    Analiza el Excel de CDT y retorna el dict estructurado de resultados.

    Si OPENAI_API_KEY está disponible usa un ReAct agent (GPT-4o-mini).
    En caso contrario usa el modo directo (sin LLM).
    """
    skill_text = _SKILL_PATH.read_text(encoding="utf-8")

    if _LANGCHAIN_AVAILABLE and os.getenv("OPENAI_API_KEY"):
        return _analyze_with_agent(file_path, skill_text)
    else:
        print("[cdts] Usando análisis directo (sin LLM).")
        return parse_excel(file_path)


def _analyze_with_agent(file_path: Path, skill_text: str) -> dict:
    """Análisis vía LangGraph ReAct agent con GPT-4o-mini y structured output."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = _make_tools(file_path)

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=skill_text,
        response_format=ExtractionOutput,
    )

    task = (
        f"Analiza el archivo CDT en: {file_path}\n"
        "Usa read_and_parse_excel para leer el Excel, luego calculate_percentile "
        "para verificar el P75 global y por grupo. "
        "Recuerda: una fila por entidad, columna 12 = 'A 180 días'. "
        "Incluye el campo rango [tasa_min, tasa_max] de tasas > 0 por grupo."
    )

    try:
        result = agent.invoke({"messages": [("user", task)]})
        structured: ExtractionOutput = result["structured_response"]
        return {
            "corte": structured.corte,
            "tasa_referencia_global": structured.tasa_referencia_global,
            "grupos": [
                {
                    "nombre": g.nombre,
                    "percentil_75": g.percentil_75,
                    "rango": list(g.rango),
                    "entidades": [
                        {"nombre": e.nombre, "tasa_activa": e.tasa_activa, "tasa_inactiva": e.tasa_inactiva}
                        for e in g.entidades
                    ],
                }
                for g in structured.grupos
            ],
        }
    except Exception as e:
        print(f"[cdts] Agente falló ({e}), usando análisis directo.")
        return parse_excel(file_path)

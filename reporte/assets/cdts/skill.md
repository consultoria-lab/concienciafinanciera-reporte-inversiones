# Skill: Análisis de Tasas — CDT (Superintendencia Financiera)

## Descripción
Analiza el archivo Excel descargado del portal de la Superintendencia Financiera de Colombia
que contiene las tasas efectivas anuales de Certificados de Depósito a Término (CDT).

---

## Estructura del Excel

El archivo tiene una sola hoja ("cdt") con la siguiente estructura:
- **Fila 0**: Encabezado con "ESTABLECIMIENTOS DE CRÉDITO" y fecha de corte
- **Fila 1**: Descripción del producto
- **Fila 2**: Vacía
- **Fila 3**: Nombres de columnas
- **A partir de fila 4**: **Una fila por entidad** (nombre + tasas en la misma fila)

**Diferencia clave vs. Cuentas de Ahorro**: NO hay filas en pares. Cada entidad ocupa UNA sola fila.

### Columnas de tasas (índice 0-based):
| Col | Nombre |
|-----|--------|
| 1   | Entidad |
| 2   | A 30 días |
| 3   | Entre 31 y 44 días |
| 4   | A 45 días |
| 5   | Entre 46 y 59 días |
| 6   | A 60 días |
| 7   | Entre 61 y 89 días |
| 8   | A 90 días |
| 9   | Entre 91 y 119 días |
| 10  | A 120 días |
| 11  | Entre 121 y 179 días |
| **12** | **A 180 días** ← columna principal |
| 13  | Entre 181 y 359 días |
| 14  | A 360 días |
| 15  | Superior a 360 días |

---

## Pasos de Análisis

### Paso 1: Leer el Excel
```python
import pandas as pd
df = pd.read_excel(file_path, sheet_name=0, header=None)
```

### Paso 2: Extraer entidades (una fila por entidad)
Iterar filas desde índice 4:
```python
for i in range(4, len(df)):
    nombre_raw = df.iloc[i, 1]
    tasa_raw = df.iloc[i, 12]  # columna "A 180 días"
    # Limpiar nombre: quitar comillas, saltos de línea
    # Parsear tasa: "11.12 %" → 11.12 | "---" → None
    # Excluir filas de disclaimer (texto empieza con "¿")
```

### Paso 3: Parsear tasas
- Formato en el Excel: `"11.12 %"` o `"11.12%"` → float `11.12`
- Valores nulos: `"---"` o `NaN` → `None`
```python
def parse_tasa(val) -> float | None:
    if pd.isna(val) or str(val).strip() in ("---", ""):
        return None
    return float(str(val).replace("%", "").replace(",", ".").strip())
```

### Paso 4: Clasificar entidades en 3 grupos
Usar las listas de `config.yaml` para clasificar cada entidad (coincidencia parcial, case-insensitive):
- Si el nombre contiene alguna keyword de "neobancos" → Neobancos
- Si contiene alguna de "cfcs_cooperativas" → CFCs / Cooperativas
- De lo contrario → Bancos Tradicionales

### Paso 5: Calcular Percentil 75 por grupo y global
Solo usar tasas "A 180 días" **no nulas** (excluir None y 0.0%):
```python
import numpy as np
tasas = [e["tasa_activa"] for e in grupo["entidades"] if e["tasa_activa"] and e["tasa_activa"] > 0]
p75 = float(np.percentile(tasas, 75)) if tasas else 0.0
rango = [round(min(tasas), 2), round(max(tasas), 2)] if tasas else [0.0, 0.0]
```

### Paso 6: Retornar resultado estructurado
```json
{
  "corte": "2026-03-16",
  "tasa_referencia_global": 11.83,
  "grupos": [
    {
      "nombre": "Neobancos",
      "percentil_75": 12.21,
      "rango": [10.00, 13.23],
      "entidades": [
        {"nombre": "Bold C.F.", "tasa_activa": 13.23},
        ...
      ]
    },
    {
      "nombre": "Bancos Tradicionales",
      "percentil_75": 11.53,
      "rango": [9.94, 12.19],
      "entidades": [...]
    },
    {
      "nombre": "CFCs / Cooperativas",
      "percentil_75": 9.22,
      "rango": [7.74, 9.31],
      "entidades": [...]
    }
  ]
}
```

---

## Notas importantes
- La `tasa_referencia_global` es el P75 calculado sobre **todas** las tasas "A 180 días" (sin filtrar por grupo)
- Ordenar entidades dentro de cada grupo de mayor a menor tasa
- Si una entidad no clasifica en ningún grupo conocido, agregarla a "Bancos Tradicionales" por defecto
- La fecha de corte está en la fila 0, col 1: extraerla con regex `r'\d{4}-\d{2}-\d{2}'`
- La última fila puede contener un disclaimer (empieza con "¿"): ignorarla

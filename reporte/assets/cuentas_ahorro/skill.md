# Skill: Análisis de Tasas — Cuentas de Ahorro (Superfinanciera)

## Descripción
Analiza el archivo Excel descargado del portal de la Superintendencia Financiera de Colombia
que contiene las tasas efectivas anuales de cuentas de ahorro para persona natural.

---

## Estructura del Excel

El archivo tiene una sola hoja ("IndividualSavingsAccount") con la siguiente estructura especial:
- **Fila 0**: Encabezado con "ESTABLECIMIENTOS DE CRÉDITO" y fecha de corte
- **Fila 1**: Título del producto
- **Fila 2**: Nombres de columnas (col 1: "Entidad", col 2: "Depósitos de ahorro activos", etc.)
- **A partir de fila 3**: Los datos están en pares de filas:
  - Fila impar (3, 5, 7...): nombre de la entidad en **columna 1** (col index 1)
  - Fila par (4, 6, 8...): tasas correspondientes en columnas 2-6

### Columnas de tasas (índice 0-based):
| Col | Nombre |
|-----|--------|
| 2 | Depósitos de ahorro activos ← **columna principal** |
| 3 | Depósitos de ahorro inactivos |
| 4 | Cuenta de ahorro especial en pesos |
| 5 | Cuentas de ahorro AFC en pesos |
| 6 | Certificado de ahorro valor real |

---

## Pasos de Análisis

### Paso 1: Leer el Excel
```python
import pandas as pd
df = pd.read_excel(file_path, sheet_name=0, header=None)
```

### Paso 2: Extraer pares entidad → tasa
Iterar filas desde índice 3, tomando de dos en dos:
```python
entidades = []
for i in range(3, len(df) - 1, 2):
    nombre_raw = df.iloc[i, 1]
    tasa_raw = df.iloc[i + 1, 2]  # columna "Depósitos de ahorro activos"
    tasa_inactiva_raw = df.iloc[i + 1, 3]
    # Limpiar nombre: quitar comillas, saltos de línea
    # Parsear tasa: "6.53 %" → 6.53 | "---" → None
```

### Paso 3: Parsear tasas
- Formato en el Excel: `"6.53 %"` o `"6.53%"` → float `6.53`
- Valores nulos: `"---"` o `NaN` → `None`
```python
def parse_tasa(val) -> float | None:
    if pd.isna(val) or str(val).strip() in ("---", ""):
        return None
    return float(str(val).replace("%", "").replace(",", ".").strip())
```

### Paso 4: Clasificar entidades en 3 grupos
Usar las listas de `config.yaml` para clasificar cada entidad.
La clasificación es por **coincidencia parcial** (case-insensitive):
- Si el nombre de la entidad contiene alguna keyword de "neobancos" → Neobancos
- Si contiene alguna de "cfcs_cooperativas" → CFCs/Cooperativas
- De lo contrario → Bancos Tradicionales

### Paso 5: Calcular Percentil 75 por grupo y global
Solo usar tasas activas **no nulas** (excluir None y 0.0%):
```python
import numpy as np
tasas = [e.tasa_activa for e in grupo.entidades if e.tasa_activa and e.tasa_activa > 0]
p75 = float(np.percentile(tasas, 75)) if tasas else 0.0
```

### Paso 6: Retornar resultado estructurado
Retornar un dict JSON con:
```json
{
  "corte": "2026-03-12",
  "tasa_referencia_global": 3.84,
  "grupos": [
    {
      "nombre": "Neobancos",
      "percentil_75": 8.74,
      "rango": [0.0, 9.75],
      "entidades": [
        {"nombre": "BAN100 S.A.", "tasa_activa": 9.75},
        ...
      ]
    },
    {
      "nombre": "Bancos Tradicionales",
      "percentil_75": 2.06,
      "rango": [0.0, 4.88],
      "entidades": [...]
    },
    {
      "nombre": "CFCs / Cooperativas",
      "percentil_75": 1.64,
      "rango": [0.0, 3.12],
      "entidades": [...]
    }
  ]
}
```

---

## Notas importantes
- La `tasa_referencia_global` es el P75 calculado sobre **todas** las tasas activas (sin filtrar por grupo)
- Ordenar entidades dentro de cada grupo de mayor a menor tasa activa
- Si una entidad no clasifica en ningún grupo conocido, agregarla a "Bancos Tradicionales" por defecto
- La fecha de corte está en la fila 0, col 1: extraerla con regex `r'\d{4}-\d{2}-\d{2}'`

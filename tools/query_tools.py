"""
Implementación de herramientas de consulta y definiciones para la API de Anthropic.
Cada función corresponde a una herramienta que Claude puede invocar durante el chat.
"""

import json
import numpy as np
import pandas as pd
from tools.data_loader import (
    obtener_df_metricas, obtener_df_ordenes,
    COLS_SEMANAS_METRICAS, COLS_SEMANAS_ORDENES, obtener_columna_semana
)


# ──────────────────────────────────────────────
# Funciones auxiliares internas
# ──────────────────────────────────────────────

def _df_a_registros(df: pd.DataFrame, max_filas: int = 50) -> list[dict]:
    """
    Convierte un DataFrame a una lista de diccionarios serializable en JSON.

    Args:
        df (pd.DataFrame): DataFrame a convertir.
        max_filas (int): Número máximo de filas a incluir. Default 50.

    Returns:
        list[dict]: Lista de registros listos para JSON.
    """
    df = df.head(max_filas).copy()
    # Redondear columnas float para legibilidad
    for col in df.select_dtypes(include=[np.floating]).columns:
        df[col] = df[col].round(4)
    return df.replace({np.nan: None}).to_dict(orient="records")


def _buscar_metrica(df: pd.DataFrame, metrica: str) -> pd.Series:
    """
    Retorna una máscara booleana para filas que coinciden con la métrica dada.
    Primero intenta coincidencia exacta (sin distinción de mayúsculas),
    luego coincidencia parcial como fallback.

    Args:
        df (pd.DataFrame): DataFrame de métricas.
        metrica (str): Nombre de la métrica a buscar.

    Returns:
        pd.Series: Máscara booleana con True en las filas que coinciden.
    """
    metrica_lower = metrica.lower().strip()

    # Intento 1: coincidencia exacta (case-insensitive)
    exacta = df["METRIC"].str.lower().str.strip() == metrica_lower
    if exacta.any():
        return exacta

    # Intento 2: coincidencia parcial (substring)
    parcial = df["METRIC"].str.lower().str.contains(metrica_lower, regex=False)
    return parcial


# ──────────────────────────────────────────────
# Herramienta 1: filtrar_zonas
# ──────────────────────────────────────────────

def filtrar_zonas(
    metrica: str,
    top_n: int = 10,
    semana: str = "L0W",
    pais: str = None,
    tipo_zona: str = None,
    priorizacion: str = None,
    ascendente: bool = False,
) -> dict:
    """
    Retorna las top/bottom N zonas para una métrica dada en una semana específica.

    Args:
        metrica (str): Nombre de la métrica a evaluar (ej: 'Lead Penetration').
        top_n (int): Cantidad de zonas a retornar. Default 10.
        semana (str): Semana a evaluar: L0W (actual), L1W, ..., L8W. Default L0W.
        pais (str): Código de país para filtrar (ej: 'CO', 'MX'). None = todos.
        tipo_zona (str): Filtro por tipo: 'Wealthy' o 'Non Wealthy'. None = todos.
        priorizacion (str): Filtro por priorización: 'High Priority', etc. None = todos.
        ascendente (bool): Si True, retorna las peores N zonas. Default False (mejores).

    Returns:
        dict: Diccionario con metadata y lista de zonas ordenadas.
    """
    df = obtener_df_metricas()
    col_semana = obtener_columna_semana(semana, "metricas")

    # Construir máscara de filtros
    mascara = _buscar_metrica(df, metrica)
    if pais:
        mascara &= df["COUNTRY"].str.upper() == pais.upper()
    if tipo_zona:
        mascara &= df["ZONE_TYPE"].str.lower() == tipo_zona.lower()
    if priorizacion:
        mascara &= df["ZONE_PRIORITIZATION"].str.lower() == priorizacion.lower()

    # Seleccionar columnas relevantes y eliminar NaN en la métrica
    subconjunto = df[mascara][
        ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", col_semana]
    ].dropna(subset=[col_semana])

    if subconjunto.empty:
        return {"error": f"No se encontraron datos para la métrica '{metrica}'."}

    # Renombrar columna de valor, seleccionar top/bottom con nlargest/nsmallest y agregar rank
    subconjunto = subconjunto.rename(columns={col_semana: "value"})
    if ascendente:
        subconjunto = subconjunto.nsmallest(top_n, "value")
    else:
        subconjunto = subconjunto.nlargest(top_n, "value")
    subconjunto["rank"] = range(1, len(subconjunto) + 1)
    subconjunto["semana"] = semana
    subconjunto["metrica"] = metrica

    return {
        "metrica": metrica,
        "semana": semana,
        "orden": "ascendente (peores)" if ascendente else "descendente (mejores)",
        "cantidad": len(subconjunto),
        "data": _df_a_registros(subconjunto),
    }


# ──────────────────────────────────────────────
# Herramienta 2: comparar_metricas
# ──────────────────────────────────────────────

def comparar_metricas(
    metrica: str,
    agrupar_por: str = "ZONE_TYPE",
    pais: str = None,
    semana: str = "L0W",
) -> dict:
    """
    Compara una métrica entre grupos (ZONE_TYPE, COUNTRY, ZONE_PRIORITIZATION, CITY).
    Calcula estadísticas descriptivas (media, mediana, min, max, conteo) por grupo.

    Args:
        metrica (str): Nombre de la métrica a comparar.
        agrupar_por (str): Dimensión de agrupación: ZONE_TYPE, COUNTRY,
                           ZONE_PRIORITIZATION o CITY. Default ZONE_TYPE.
        pais (str): Código de país para filtrar. None = todos los países.
        semana (str): Semana a evaluar: L0W..L8W. Default L0W.

    Returns:
        dict: Diccionario con estadísticas por grupo, ordenadas por media descendente.
    """
    df = obtener_df_metricas()
    col_semana = obtener_columna_semana(semana, "metricas")

    # Validar columna de agrupación
    columnas_validas = ["ZONE_TYPE", "COUNTRY", "ZONE_PRIORITIZATION", "CITY"]
    col_grupo = agrupar_por.upper()
    if col_grupo not in columnas_validas:
        col_grupo = "ZONE_TYPE"

    # Aplicar filtros
    mascara = _buscar_metrica(df, metrica)
    if pais:
        mascara &= df["COUNTRY"].str.upper() == pais.upper()

    subconjunto = df[mascara][[col_grupo, col_semana]].dropna(subset=[col_semana])

    if subconjunto.empty:
        return {"error": f"No se encontraron datos para la métrica '{metrica}'."}

    # Calcular estadísticas descriptivas por grupo
    agrupado = (
        subconjunto.groupby(col_grupo)[col_semana]
        .agg(["mean", "median", "min", "max", "count"])
        .round(4)
        .reset_index()
    )
    agrupado.columns = [col_grupo, "media", "mediana", "minimo", "maximo", "n_zonas"]
    agrupado = agrupado.sort_values("media", ascending=False)

    return {
        "metrica": metrica,
        "semana": semana,
        "agrupado_por": col_grupo,
        "data": _df_a_registros(agrupado, max_filas=100),
    }


# ──────────────────────────────────────────────
# Herramienta 3: obtener_tendencia
# ──────────────────────────────────────────────

def obtener_tendencia(zona: str, metrica: str, semanas: int = 9) -> dict:
    """
    Retorna la tendencia semanal de una métrica para una zona específica.

    Args:
        zona (str): Nombre de la zona (o nombre parcial para búsqueda aproximada).
        metrica (str): Nombre de la métrica a analizar.
        semanas (int): Cuántas semanas de historial incluir (1-9). Default 9.

    Returns:
        dict: Diccionario con la zona, métrica y lista de valores por semana.
    """
    df = obtener_df_metricas()
    semanas = max(1, min(9, semanas))  # Clamp entre 1 y 9
    cols_seleccionadas = COLS_SEMANAS_METRICAS[-semanas:]

    # Búsqueda exacta de zona
    mascara = _buscar_metrica(df, metrica) & (df["ZONE"].str.lower() == zona.lower())
    subconjunto = df[mascara]

    # Fallback: búsqueda parcial si no hay coincidencia exacta
    if subconjunto.empty:
        mascara2 = _buscar_metrica(df, metrica) & df["ZONE"].str.lower().str.contains(
            zona.lower(), regex=False
        )
        subconjunto = df[mascara2]

    if subconjunto.empty:
        return {"error": f"No se encontraron datos para la zona '{zona}' / métrica '{metrica}'."}

    # Construir serie temporal de la primera fila coincidente
    fila = subconjunto.iloc[0]
    etiquetas_semanas = ["L8W", "L7W", "L6W", "L5W", "L4W", "L3W", "L2W", "L1W", "L0W"]
    inicio_idx = 9 - semanas
    tendencia = []
    for i, col in enumerate(cols_seleccionadas):
        val = fila[col]
        tendencia.append({
            "semana": etiquetas_semanas[inicio_idx + i],
            "value": round(float(val), 4) if pd.notna(val) else None,
        })

    return {
        "zona": fila["ZONE"],
        "ciudad": fila["CITY"],
        "pais": fila["COUNTRY"],
        "metrica": metrica,
        "semanas_analizadas": semanas,
        "trend": tendencia,
    }


# ──────────────────────────────────────────────
# Herramienta 4: agregar_por
# ──────────────────────────────────────────────

def agregar_por(
    metrica: str,
    agrupar_por: str = "COUNTRY",
    semana: str = "L0W",
    funcion_agrupacion: str = "mean",
) -> dict:
    """
    Calcula el valor agregado de una métrica agrupado por país, ciudad, tipo de zona,
    o priorización.

    Args:
        metrica (str): Nombre de la métrica a agregar.
        agrupar_por (str): Columna de agrupación: COUNTRY, CITY, ZONE_TYPE,
                           ZONE_PRIORITIZATION. Default COUNTRY.
        semana (str): Semana a evaluar: L0W..L8W. Default L0W.
        funcion_agrupacion (str): Función de agregación: mean, sum o median. Default mean.

    Returns:
        dict: Diccionario con valores agregados por grupo, ordenados descendentemente.
    """
    df = obtener_df_metricas()
    col_semana = obtener_columna_semana(semana, "metricas")

    # Validar columna de agrupación
    columnas_validas = ["COUNTRY", "CITY", "ZONE_TYPE", "ZONE_PRIORITIZATION"]
    col_grupo = agrupar_por.upper()
    if col_grupo not in columnas_validas:
        col_grupo = "COUNTRY"

    mascara = _buscar_metrica(df, metrica)
    subconjunto = df[mascara][[col_grupo, col_semana]].dropna(subset=[col_semana])

    if subconjunto.empty:
        return {"error": f"No se encontraron datos para la métrica '{metrica}'."}

    # Mapear función de agregación permitida
    mapa_funciones = {"mean": "mean", "sum": "sum", "median": "median"}
    fn = mapa_funciones.get(funcion_agrupacion.lower(), "mean")

    agrupado = (
        subconjunto.groupby(col_grupo)[col_semana]
        .agg([fn, "count"])
        .round(4)
        .reset_index()
    )
    agrupado.columns = [col_grupo, "value", "n_zonas"]
    agrupado = agrupado.sort_values("value", ascending=False)

    return {
        "metrica": metrica,
        "semana": semana,
        "agrupado_por": col_grupo,
        "funcion": fn,
        "data": _df_a_registros(agrupado, max_filas=100),
    }


# ──────────────────────────────────────────────
# Herramienta 5: analisis_multivariable
# ──────────────────────────────────────────────

def analisis_multivariable(
    metrica_alta: str,
    metrica_baja: str,
    umbral_alto: float = None,
    umbral_bajo: float = None,
    semana: str = "L0W",
    pais: str = None,
) -> dict:
    """
    Encuentra zonas donde una métrica está ALTA y otra está BAJA simultáneamente.
    Útil para identificar zonas con desbalances operacionales.

    Args:
        metrica_alta (str): Métrica que debe tener valor alto.
        metrica_baja (str): Métrica que debe tener valor bajo.
        umbral_alto (float): Valor mínimo para metrica_alta. None = usa la mediana.
        umbral_bajo (float): Valor máximo para metrica_baja. None = usa la mediana.
        semana (str): Semana a evaluar: L0W..L8W. Default L0W.
        pais (str): Código de país para filtrar. None = todos los países.

    Returns:
        dict: Zonas que satisfacen ambas condiciones con los umbrales aplicados.
    """
    df = obtener_df_metricas()
    col_semana = obtener_columna_semana(semana, "metricas")

    def obtener_datos_metrica(nombre_metrica):
        """Extrae y filtra los datos de una métrica específica."""
        mascara = _buscar_metrica(df, nombre_metrica)
        if pais:
            mascara &= df["COUNTRY"].str.upper() == pais.upper()
        cols = ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", col_semana]
        return df[mascara][cols].dropna(subset=[col_semana]).rename(columns={col_semana: "value"})

    df_alto = obtener_datos_metrica(metrica_alta)
    df_bajo = obtener_datos_metrica(metrica_baja)

    if df_alto.empty or df_bajo.empty:
        return {"error": "Una o ambas métricas no tienen datos disponibles."}

    # Usar mediana como umbral por defecto si no se especifica
    thr_alto = umbral_alto if umbral_alto is not None else float(df_alto["value"].median())
    thr_bajo = umbral_bajo if umbral_bajo is not None else float(df_bajo["value"].median())

    # Filtrar zonas según umbrales
    zonas_altas = df_alto[df_alto["value"] >= thr_alto][["ZONE", "value"]].rename(
        columns={"value": metrica_alta}
    )
    zonas_bajas = df_bajo[df_bajo["value"] <= thr_bajo][["ZONE", "value"]].rename(
        columns={"value": metrica_baja}
    )

    # Cruzar para obtener zonas que cumplen ambas condiciones
    interseccion = zonas_altas.merge(zonas_bajas, on="ZONE")

    if interseccion.empty:
        return {
            "error": "No hay zonas que satisfagan ambas condiciones simultáneamente.",
            "umbral_alto": thr_alto,
            "umbral_bajo": thr_bajo,
        }

    # Enriquecer con metadatos de zona
    metadatos = df_alto[
        ["ZONE", "COUNTRY", "CITY", "ZONE_TYPE", "ZONE_PRIORITIZATION"]
    ].drop_duplicates("ZONE")
    resultado = interseccion.merge(metadatos, on="ZONE", how="left").round(4)

    return {
        "metrica_alta": metrica_alta,
        "metrica_baja": metrica_baja,
        "umbral_alto": round(thr_alto, 4),
        "umbral_bajo": round(thr_bajo, 4),
        "semana": semana,
        "cantidad": len(resultado),
        "data": _df_a_registros(resultado),
    }


# ──────────────────────────────────────────────
# Herramienta 6: obtener_tendencia_ordenes
# ──────────────────────────────────────────────

def obtener_tendencia_ordenes(zona: str, semanas: int = 9) -> dict:
    """
    Retorna la tendencia semanal de órdenes para una zona específica.

    Args:
        zona (str): Nombre de la zona (o nombre parcial para búsqueda aproximada).
        semanas (int): Cuántas semanas de historial incluir (1-9). Default 9.

    Returns:
        dict: Diccionario con la zona y lista de órdenes por semana.
    """
    df = obtener_df_ordenes()
    semanas = max(1, min(9, semanas))  # Clamp entre 1 y 9
    cols_seleccionadas = COLS_SEMANAS_ORDENES[-semanas:]

    # Búsqueda exacta de zona
    mascara = df["ZONE"].str.lower() == zona.lower()
    subconjunto = df[mascara]

    # Fallback: búsqueda parcial
    if subconjunto.empty:
        mascara2 = df["ZONE"].str.lower().str.contains(zona.lower())
        subconjunto = df[mascara2]

    if subconjunto.empty:
        return {"error": f"No se encontraron datos de órdenes para la zona '{zona}'."}

    # Construir serie temporal de órdenes
    fila = subconjunto.iloc[0]
    etiquetas_semanas = ["L8W", "L7W", "L6W", "L5W", "L4W", "L3W", "L2W", "L1W", "L0W"]
    inicio_idx = 9 - semanas
    tendencia = []
    for i, col in enumerate(cols_seleccionadas):
        val = fila[col]
        tendencia.append({
            "semana": etiquetas_semanas[inicio_idx + i],
            "orders": int(val) if pd.notna(val) else None,
        })

    return {
        "zona": fila["ZONE"],
        "ciudad": fila["CITY"],
        "pais": fila["COUNTRY"],
        "semanas_analizadas": semanas,
        "trend": tendencia,
    }


# ──────────────────────────────────────────────
# Definiciones de herramientas para la API de Anthropic
# ──────────────────────────────────────────────

DEFINICIONES_HERRAMIENTAS = [
    {
        "name": "filter_zones",
        "description": (
            "Retorna las top o bottom N zonas para una métrica específica en una semana dada. "
            "Úsalo para responder preguntas como '¿cuáles son las mejores/peores zonas en X métrica?', "
            "'top 5 zonas con mayor Lead Penetration', etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metrica": {
                    "type": "string",
                    "description": "Nombre exacto de la métrica. Ej: 'Lead Penetration', 'Perfect Orders'."
                },
                "top_n": {
                    "type": "integer",
                    "description": "Número de zonas a retornar. Default 10.",
                    "default": 10
                },
                "semana": {
                    "type": "string",
                    "description": "Semana a usar: L0W (actual), L1W, L2W, ..., L8W. Default L0W.",
                    "default": "L0W"
                },
                "pais": {
                    "type": "string",
                    "description": "Código de país de 2 letras para filtrar (ej: CO, MX, BR). Opcional."
                },
                "tipo_zona": {
                    "type": "string",
                    "description": "Opcional: 'Wealthy' o 'Non Wealthy'."
                },
                "priorizacion": {
                    "type": "string",
                    "description": "Opcional: 'High Priority', 'Prioritized', o 'Not Prioritized'."
                },
                "ascendente": {
                    "type": "boolean",
                    "description": "Si true, retorna las peores N (valor más bajo). Default false (mejores).",
                    "default": False
                }
            },
            "required": ["metrica"]
        }
    },
    {
        "name": "compare_metrics",
        "description": (
            "Compara el promedio de una métrica entre grupos: por ZONE_TYPE (Wealthy vs Non Wealthy), "
            "por COUNTRY, por ZONE_PRIORITIZATION, o por CITY. "
            "Úsalo para preguntas como '¿cómo se compara X entre zonas Wealthy y Non Wealthy?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metrica": {"type": "string", "description": "Nombre de la métrica."},
                "agrupar_por": {
                    "type": "string",
                    "description": "Dimensión de agrupación: ZONE_TYPE, COUNTRY, ZONE_PRIORITIZATION, CITY.",
                    "default": "ZONE_TYPE"
                },
                "pais": {"type": "string", "description": "Código de país para filtrar. Opcional."},
                "semana": {"type": "string", "description": "Semana: L0W..L8W. Default L0W.", "default": "L0W"}
            },
            "required": ["metrica"]
        }
    },
    {
        "name": "get_trend",
        "description": (
            "Obtiene la tendencia semanal de una métrica específica para una zona concreta. "
            "Úsalo para preguntas sobre evolución histórica o performance de una zona en el tiempo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "zona": {"type": "string", "description": "Nombre de la zona (o nombre parcial)."},
                "metrica": {"type": "string", "description": "Nombre de la métrica."},
                "semanas": {
                    "type": "integer",
                    "description": "Cuántas semanas de historial (1-9). Default 9.",
                    "default": 9
                }
            },
            "required": ["zona", "metrica"]
        }
    },
    {
        "name": "aggregate_by",
        "description": (
            "Calcula la media/suma/mediana de una métrica agrupada por país, ciudad, tipo de zona "
            "o priorización. Úsalo para preguntas como '¿cuál es el promedio de X por país?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metrica": {"type": "string", "description": "Nombre de la métrica."},
                "agrupar_por": {
                    "type": "string",
                    "description": "Columna de agrupación: COUNTRY, CITY, ZONE_TYPE, ZONE_PRIORITIZATION.",
                    "default": "COUNTRY"
                },
                "semana": {"type": "string", "description": "Semana: L0W..L8W. Default L0W.", "default": "L0W"},
                "funcion_agrupacion": {
                    "type": "string",
                    "description": "Función de agregación: mean, sum o median. Default mean.",
                    "default": "mean"
                }
            },
            "required": ["metrica"]
        }
    },
    {
        "name": "multivariable_analysis",
        "description": (
            "Encuentra zonas donde una métrica es ALTA y otra es BAJA simultáneamente. "
            "Úsalo para preguntas como '¿qué zonas tienen alto Lead Penetration pero bajo Perfect Order?'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metrica_alta": {"type": "string", "description": "Métrica que debe estar alta."},
                "metrica_baja": {"type": "string", "description": "Métrica que debe estar baja."},
                "umbral_alto": {
                    "type": "number",
                    "description": "Valor mínimo para metrica_alta. Si se omite, usa la mediana."
                },
                "umbral_bajo": {
                    "type": "number",
                    "description": "Valor máximo para metrica_baja. Si se omite, usa la mediana."
                },
                "semana": {"type": "string", "description": "Semana: L0W..L8W. Default L0W.", "default": "L0W"},
                "pais": {"type": "string", "description": "Código de país para filtrar. Opcional."}
            },
            "required": ["metrica_alta", "metrica_baja"]
        }
    },
    {
        "name": "get_orders_trend",
        "description": (
            "Obtiene la tendencia semanal de órdenes para una zona específica. "
            "Úsalo para preguntas sobre la evolución del volumen de pedidos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "zona": {"type": "string", "description": "Nombre de la zona."},
                "semanas": {
                    "type": "integer",
                    "description": "Cuántas semanas de historial (1-9). Default 9.",
                    "default": 9
                }
            },
            "required": ["zona"]
        }
    },
]

# Alias para compatibilidad con el nombre original que espera app.py
TOOL_DEFINITIONS = DEFINICIONES_HERRAMIENTAS


# ──────────────────────────────────────────────
# Mapa de herramientas y despachador
# ──────────────────────────────────────────────

# Mapeo de nombre de herramienta (según API de Anthropic) → función Python
MAPA_HERRAMIENTAS = {
    "filter_zones":          filtrar_zonas,
    "compare_metrics":       comparar_metricas,
    "get_trend":             obtener_tendencia,
    "aggregate_by":          agregar_por,
    "multivariable_analysis": analisis_multivariable,
    "get_orders_trend":      obtener_tendencia_ordenes,
}


def despachar_herramienta(nombre_herramienta: str, parametros: dict) -> str:
    """
    Invoca la herramienta correspondiente y retorna el resultado como string JSON.

    Args:
        nombre_herramienta (str): Nombre de la herramienta tal como la llama Claude.
        parametros (dict): Diccionario de parámetros para la herramienta.

    Returns:
        str: Resultado serializado como JSON string.
    """
    if nombre_herramienta not in MAPA_HERRAMIENTAS:
        return json.dumps({"error": f"Herramienta desconocida: {nombre_herramienta}"})
    try:
        resultado = MAPA_HERRAMIENTAS[nombre_herramienta](**parametros)
        return json.dumps(resultado, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# Alias para compatibilidad con el nombre original que espera app.py
dispatch_tool = despachar_herramienta

"""
Cargador de datos para el sistema de análisis Rappi AI.
Lee desde Excel: RAW_INPUT_METRICS (métricas) y RAW_ORDERS (órdenes).

Nombres reales de columnas:
  - Métricas: L8W_ROLL..L0W_ROLL
  - Órdenes:  L8W..L0W
"""

import os
import pandas as pd
import numpy as np
from functools import lru_cache

# Ruta al archivo de datos (relativa al directorio raíz del proyecto)
RUTA_DATOS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data.xlsx")

# Columnas de semana para métricas (de más antigua a más reciente)
COLS_SEMANAS_METRICAS = [
    "L8W_ROLL", "L7W_ROLL", "L6W_ROLL", "L5W_ROLL",
    "L4W_ROLL", "L3W_ROLL", "L2W_ROLL", "L1W_ROLL", "L0W_ROLL"
]

# Columnas de semana para órdenes (de más antigua a más reciente)
COLS_SEMANAS_ORDENES = ["L8W", "L7W", "L6W", "L5W", "L4W", "L3W", "L2W", "L1W", "L0W"]

# Etiquetas amigables de semana (de más antigua a más reciente)
ETIQUETAS_SEMANAS = ["L8W", "L7W", "L6W", "L5W", "L4W", "L3W", "L2W", "L1W", "L0W (actual)"]


def _cargar_crudo() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Carga ambas hojas del Excel y retorna el par (df_metricas, df_ordenes).

    Returns:
        tuple: (DataFrame de métricas, DataFrame de órdenes)
    """
    metricas = pd.read_excel(RUTA_DATOS, sheet_name="RAW_INPUT_METRICS")
    ordenes  = pd.read_excel(RUTA_DATOS, sheet_name="RAW_ORDERS")
    return metricas, ordenes


def _limpiar_metricas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza tipos y maneja valores NaN en el DataFrame de métricas.

    Args:
        df (pd.DataFrame): DataFrame crudo de métricas.

    Returns:
        pd.DataFrame: DataFrame limpio y normalizado.
    """
    # Normalizar columnas de texto: strip de espacios y conversión a string
    cols_texto = ["COUNTRY", "CITY", "ZONE", "ZONE_TYPE", "ZONE_PRIORITIZATION", "METRIC"]
    for col in cols_texto:
        df[col] = df[col].astype(str).str.strip()

    # Convertir columnas de semana a numérico
    for col in COLS_SEMANAS_METRICAS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Eliminar filas sin información clave
    df.dropna(subset=["COUNTRY", "CITY", "ZONE", "METRIC"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def _limpiar_ordenes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza tipos y maneja valores NaN en el DataFrame de órdenes.

    Args:
        df (pd.DataFrame): DataFrame crudo de órdenes.

    Returns:
        pd.DataFrame: DataFrame limpio y normalizado.
    """
    # Normalizar columnas de texto
    cols_texto = ["COUNTRY", "CITY", "ZONE", "METRIC"]
    for col in cols_texto:
        df[col] = df[col].astype(str).str.strip()

    # Convertir columnas de semana a numérico
    for col in COLS_SEMANAS_ORDENES:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Eliminar filas sin información clave de zona
    df.dropna(subset=["COUNTRY", "CITY", "ZONE"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


@lru_cache(maxsize=1)
def obtener_df_metricas() -> pd.DataFrame:
    """
    Retorna el DataFrame de métricas limpio (con caché en memoria).

    Returns:
        pd.DataFrame: DataFrame de métricas listo para consulta.
    """
    crudo, _ = _cargar_crudo()
    return _limpiar_metricas(crudo)


@lru_cache(maxsize=1)
def obtener_df_ordenes() -> pd.DataFrame:
    """
    Retorna el DataFrame de órdenes limpio (con caché en memoria).

    Returns:
        pd.DataFrame: DataFrame de órdenes listo para consulta.
    """
    _, crudo = _cargar_crudo()
    return _limpiar_ordenes(crudo)


def recargar_datos() -> None:
    """
    Limpia el caché y recarga los datos desde disco.
    Útil para refrescar datos sin reiniciar la aplicación.
    """
    obtener_df_metricas.cache_clear()
    obtener_df_ordenes.cache_clear()


def obtener_metricas_disponibles() -> list[str]:
    """
    Retorna la lista ordenada de métricas únicas disponibles en el dataset.

    Returns:
        list[str]: Lista de nombres de métricas.
    """
    return sorted(obtener_df_metricas()["METRIC"].unique().tolist())


def obtener_paises_disponibles() -> list[str]:
    """
    Retorna la lista ordenada de países únicos disponibles en el dataset.

    Returns:
        list[str]: Lista de códigos de país (ej: 'CO', 'MX', 'BR').
    """
    return sorted(obtener_df_metricas()["COUNTRY"].unique().tolist())


def obtener_tipos_zona_disponibles() -> list[str]:
    """
    Retorna la lista ordenada de tipos de zona únicos (ej: 'Wealthy', 'Non Wealthy').

    Returns:
        list[str]: Lista de tipos de zona.
    """
    return sorted(obtener_df_metricas()["ZONE_TYPE"].unique().tolist())


def obtener_columna_semana(etiqueta_semana: str, dataset: str = "metricas") -> str:
    """
    Convierte una etiqueta amigable de semana (ej: 'L0W', 'actual', 'L3W')
    al nombre real de columna en el DataFrame correspondiente.

    Args:
        etiqueta_semana (str): Etiqueta de semana (ej: 'L0W', 'current', 'L3W').
        dataset (str): Tipo de dataset: 'metricas' u 'ordenes'. Default 'metricas'.

    Returns:
        str: Nombre real de la columna en el DataFrame (ej: 'L0W_ROLL' o 'L0W').
    """
    # Normalizar la etiqueta: mayúsculas, sin espacios ni sufijos de 'actual'
    etiqueta = str(etiqueta_semana).strip().upper().replace(" (CURRENT)", "").replace("CURRENT", "L0W")

    if dataset == "ordenes":
        # Para órdenes: L0W → L0W (sin sufijo)
        mapeo = {f"L{i}W": f"L{i}W" for i in range(9)}
        return mapeo.get(etiqueta, "L0W")
    else:
        # Para métricas: L0W → L0W_ROLL
        mapeo = {f"L{i}W": f"L{i}W_ROLL" for i in range(9)}
        return mapeo.get(etiqueta, "L0W_ROLL")


# ──────────────────────────────────────────────
# Aliases de compatibilidad (se conservan por si hubiera referencias externas)
# ──────────────────────────────────────────────
METRIC_WEEK_COLS = COLS_SEMANAS_METRICAS
ORDER_WEEK_COLS  = COLS_SEMANAS_ORDENES
get_metrics_df           = obtener_df_metricas
get_orders_df            = obtener_df_ordenes
get_available_metrics    = obtener_metricas_disponibles
get_available_countries  = obtener_paises_disponibles
get_available_zone_types = obtener_tipos_zona_disponibles
get_week_col             = obtener_columna_semana
reload_data              = recargar_datos

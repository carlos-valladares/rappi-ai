"""
Motor de Insights para Rappi AI.
Detecta automáticamente anomalías, tendencias, benchmarks, correlaciones y oportunidades.
Usa Claude para generar narrativa ejecutiva en texto libre (sin JSON) renderizada en HTML con Jinja2.
"""

import os
import re as _re
import datetime
import numpy as np
import pandas as pd
from scipy import stats
from jinja2 import Environment, FileSystemLoader
import anthropic
from tools.data_loader import (
    obtener_df_metricas, obtener_df_ordenes,
    COLS_SEMANAS_METRICAS, COLS_SEMANAS_ORDENES
)

MODELO = "claude-sonnet-4-5"
DIRECTORIO_REPORTES   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
DIRECTORIO_PLANTILLAS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


# ──────────────────────────────────────────────
# Helper: códigos de semana → texto legible
# ──────────────────────────────────────────────

_MAPA_SEMANAS = {
    "L0W_ROLL": "Semana actual",
    "L1W_ROLL": "Semana anterior",
    "L2W_ROLL": "Hace 2 semanas",
    "L3W_ROLL": "Hace 3 semanas",
    "L4W_ROLL": "Hace 4 semanas",
    "L5W_ROLL": "Hace 5 semanas",
    "L6W_ROLL": "Hace 6 semanas",
    "L7W_ROLL": "Hace 7 semanas",
    "L8W_ROLL": "Hace 8 semanas",
    "L0W": "Semana actual",
    "L1W": "Semana anterior",
    "L2W": "Hace 2 semanas",
    "L3W": "Hace 3 semanas",
    "L4W": "Hace 4 semanas",
    "L5W": "Hace 5 semanas",
    "L6W": "Hace 6 semanas",
    "L7W": "Hace 7 semanas",
    "L8W": "Hace 8 semanas",
}


def semana_a_texto(codigo_semana: str) -> str:
    """
    Convierte un código técnico de semana a descripción legible en español.

    Args:
        codigo_semana (str): Código de columna (ej: 'L0W_ROLL', 'L3W').

    Returns:
        str: Descripción legible (ej: 'Semana actual', 'Hace 3 semanas').
    """
    return _MAPA_SEMANAS.get(codigo_semana, codigo_semana)


# ──────────────────────────────────────────────
# 1. Detección de Anomalías (cambio >10% semana anterior → actual)
# ──────────────────────────────────────────────

def detectar_anomalias(umbral: float = 0.10) -> list[dict]:
    """
    Detecta zonas/métricas con cambio porcentual mayor al umbral en CUALQUIER
    transición semanal (L8W→L7W, L7W→L6W, ..., L1W→L0W).

    Args:
        umbral (float): Cambio mínimo para considerar anomalía. Default 0.10 (10%).

    Returns:
        list[dict]: Anomalías ordenadas por magnitud de cambio, máx 400.
    """
    df = obtener_df_metricas()
    anomalias = []

    for _, fila in df.iterrows():
        # Revisar TODAS las transiciones consecutivas (de más antiguo a más reciente)
        for i in range(len(COLS_SEMANAS_METRICAS) - 1):
            col_prev = COLS_SEMANAS_METRICAS[i]       # semana más antigua
            col_curr = COLS_SEMANAS_METRICAS[i + 1]   # semana más reciente
            val_anterior = fila[col_prev]
            val_actual   = fila[col_curr]
            if pd.isna(val_anterior) or pd.isna(val_actual) or val_anterior == 0:
                continue
            cambio = (val_actual - val_anterior) / abs(val_anterior)
            if abs(cambio) > umbral:
                anomalias.append({
                    "country":               fila["COUNTRY"],
                    "city":                  fila["CITY"],
                    "zone":                  fila["ZONE"],
                    "zone_type":             fila["ZONE_TYPE"],
                    "prioritization":        fila["ZONE_PRIORITIZATION"],
                    "metric":                fila["METRIC"],
                    "valor_semana_anterior": round(val_anterior, 4),
                    "valor_semana_actual":   round(val_actual, 4),
                    "periodo_comparado":     f"{semana_a_texto(col_prev)} → {semana_a_texto(col_curr)}",
                    "pct_change":            round(cambio * 100, 2),
                    "direction":             "incremento" if cambio > 0 else "decremento",
                })

    anomalias.sort(key=lambda x: abs(x["pct_change"]), reverse=True)
    return anomalias[:400]


# ──────────────────────────────────────────────
# 2. Tendencias Preocupantes — análisis semana a semana
# ──────────────────────────────────────────────

def detectar_tendencias_preocupantes(min_semanas: int = 3) -> list[dict]:
    """
    Para cada zona/métrica revisa TODAS las transiciones semanales y detecta la racha
    consecutiva de deterioro más larga. Reporta semana de inicio, semana de fin,
    duración y cambio acumulado.

    Args:
        min_semanas (int): Semanas consecutivas de caída requeridas. Default 3.

    Returns:
        list[dict]: Zonas/métricas con tendencia negativa, ordenadas por racha más larga, máx 30.
    """
    df = obtener_df_metricas()
    preocupantes = []

    for _, fila in df.iterrows():
        # Construir lista de (columna, valor) solo para semanas con datos
        pares = [
            (col, fila[col])
            for col in COLS_SEMANAS_METRICAS
            if pd.notna(fila[col])
        ]
        if len(pares) < min_semanas + 1:
            continue

        # Recorrer todas las transiciones semanales
        racha_max       = 0
        racha_actual    = 0
        idx_inicio_max  = 0   # índice del pico antes de la racha más larga
        idx_fin_max     = 0   # índice del último valor en descenso de la racha más larga

        for i in range(1, len(pares)):
            _, val_prev = pares[i - 1]
            _, val_curr = pares[i]
            if val_curr < val_prev:
                racha_actual += 1
                if racha_actual > racha_max:
                    racha_max      = racha_actual
                    idx_fin_max    = i
                    idx_inicio_max = i - racha_actual  # pico antes del inicio del deterioro
            else:
                racha_actual = 0

        if racha_max >= min_semanas:
            col_inicio, val_inicio = pares[idx_inicio_max]
            col_fin,    val_fin    = pares[idx_fin_max]

            cambio_acumulado = (
                (val_fin - val_inicio) / abs(val_inicio) * 100
                if val_inicio != 0 else 0
            )

            # Valor en semana actual (independiente de dónde terminó la racha)
            val_actual = fila["L0W_ROLL"] if pd.notna(fila.get("L0W_ROLL")) else val_fin

            preocupantes.append({
                "country":            fila["COUNTRY"],
                "city":               fila["CITY"],
                "zone":               fila["ZONE"],
                "zone_type":          fila["ZONE_TYPE"],
                "prioritization":     fila["ZONE_PRIORITIZATION"],
                "metric":             fila["METRIC"],
                "decline_weeks":      racha_max,
                "inicio_deterioro":   semana_a_texto(col_inicio),
                "fin_deterioro":      semana_a_texto(col_fin),
                "total_pct_change":   round(cambio_acumulado, 2),
                "current_value":      round(val_actual, 4),
            })

    # Ordenar: más crónico primero, luego mayor caída acumulada
    preocupantes.sort(key=lambda x: (-x["decline_weeks"], x["total_pct_change"]))
    return preocupantes[:30]


# ──────────────────────────────────────────────
# 3. Brechas de Benchmark — con tendencia de brecha (ampliándose / cerrándose)
# ──────────────────────────────────────────────

def detectar_brechas_benchmark(umbral: float = 0.20) -> list[dict]:
    """
    Identifica zonas más del umbral% por debajo del promedio de sus peers.
    Además determina si la brecha se está ampliando o cerrando respecto a la semana anterior.

    Args:
        umbral (float): Brecha mínima relativa. Default 0.20 (20%).

    Returns:
        list[dict]: Brechas ordenadas por mayor déficit, máx 30.
    """
    df = obtener_df_metricas()
    METRICAS_CLAVE = [
        "Perfect Orders", "Gross Profit UE", "Lead Penetration",
        "Pro Adoption (Last Week Status)", "Non-Pro PTC > OP",
    ]
    brechas = []

    for metrica in METRICAS_CLAVE:
        df_metrica = df[df["METRIC"] == metrica].copy()
        if df_metrica.empty:
            continue

        # Promedio del grupo en semana actual y semana anterior
        promedios_l0 = (
            df_metrica.groupby(["COUNTRY", "ZONE_TYPE"])["L0W_ROLL"]
            .mean().reset_index().rename(columns={"L0W_ROLL": "group_mean_l0"})
        )
        promedios_l1 = (
            df_metrica.groupby(["COUNTRY", "ZONE_TYPE"])["L1W_ROLL"]
            .mean().reset_index().rename(columns={"L1W_ROLL": "group_mean_l1"})
        )

        merged = (
            df_metrica
            .merge(promedios_l0, on=["COUNTRY", "ZONE_TYPE"])
            .merge(promedios_l1, on=["COUNTRY", "ZONE_TYPE"])
            .dropna(subset=["L0W_ROLL", "group_mean_l0"])
        )

        for _, fila in merged.iterrows():
            if fila["group_mean_l0"] == 0:
                continue

            # Brecha en semana actual
            diff_l0 = (fila["L0W_ROLL"] - fila["group_mean_l0"]) / abs(fila["group_mean_l0"])
            if diff_l0 >= -umbral:
                continue

            # Brecha en semana anterior (para determinar tendencia)
            tendencia_brecha = "estable"
            if (pd.notna(fila.get("L1W_ROLL")) and fila["group_mean_l1"] != 0
                    and pd.notna(fila.get("group_mean_l1"))):
                diff_l1 = (fila["L1W_ROLL"] - fila["group_mean_l1"]) / abs(fila["group_mean_l1"])
                if diff_l0 < diff_l1 - 0.01:
                    tendencia_brecha = "ampliándose ↓"
                elif diff_l0 > diff_l1 + 0.01:
                    tendencia_brecha = "cerrándose ↑"

            brechas.append({
                "country":          fila["COUNTRY"],
                "city":             fila["CITY"],
                "zone":             fila["ZONE"],
                "zone_type":        fila["ZONE_TYPE"],
                "prioritization":   fila["ZONE_PRIORITIZATION"],
                "metric":           metrica,
                "valor_actual":     round(fila["L0W_ROLL"], 4),
                "group_mean":       round(fila["group_mean_l0"], 4),
                "pct_below_mean":   round(diff_l0 * 100, 2),
                "tendencia_brecha": tendencia_brecha,
                # Mantener alias para compatibilidad con _resumir_hallazgos
                "zone_value":       round(fila["L0W_ROLL"], 4),
            })

    brechas.sort(key=lambda x: x["pct_below_mean"])
    return brechas[:30]


# ──────────────────────────────────────────────
# 4. Correlaciones Pearson entre métricas
# ──────────────────────────────────────────────

def _describir_correlacion(fuerza: str, direccion: str) -> str:
    if direccion == "positiva":
        if fuerza == "fuerte":
            return "Cuando una sube, la otra también sube con fuerza"
        elif fuerza == "moderada":
            return "Tienden a subir y bajar juntas"
        else:
            return "Leve tendencia a moverse en la misma dirección"
    else:
        if fuerza == "fuerte":
            return "Cuando una sube, la otra baja con fuerza"
        elif fuerza == "moderada":
            return "Tienden a moverse en direcciones opuestas"
        else:
            return "Leve tendencia a moverse en direcciones opuestas"


def _icono_fuerza(fuerza: str, direccion: str) -> str:
    if fuerza == "fuerte" and direccion == "positiva":
        return "🟢 Fuerte"
    elif fuerza == "moderada" and direccion == "positiva":
        return "🟡 Moderada"
    elif fuerza == "fuerte" and direccion == "negativa":
        return "🔴 Fuerte inversa"
    elif fuerza == "moderada" and direccion == "negativa":
        return "🟠 Moderada inversa"
    else:
        return "⚪ Débil"


def calcular_correlaciones() -> list[dict]:
    """
    Calcula correlaciones de Pearson entre pares de métricas usando valores de semana actual.
    Retorna descripción ejecutiva en lugar de valores estadísticos crudos.

    Returns:
        list[dict]: Pares con |r|>0.5 y p<0.05, ordenados por magnitud, máx 20.
    """
    df = obtener_df_metricas()
    pivot = df.pivot_table(
        index=["COUNTRY", "CITY", "ZONE"],
        columns="METRIC",
        values="L0W_ROLL",
        aggfunc="first",
    )
    metricas = [c for c in pivot.columns if pivot[c].notna().sum() > 20]
    correlaciones = []

    for i, m1 in enumerate(metricas):
        for m2 in metricas[i + 1:]:
            combinado = pivot[[m1, m2]].dropna()
            if len(combinado) < 10:
                continue
            corr, pval = stats.pearsonr(combinado[m1], combinado[m2])
            if abs(corr) > 0.5 and pval < 0.05:
                fuerza    = "fuerte" if abs(corr) > 0.7 else "moderada"
                direccion = "positiva" if corr > 0 else "negativa"
                n_zones   = int(len(combinado))
                relacion  = _describir_correlacion(fuerza, direccion)
                correlaciones.append({
                    "metric_1":       m1,
                    "metric_2":       m2,
                    "n_zones":        n_zones,
                    "relacion":       relacion,
                    "interpretacion": (
                        f"En {n_zones} zonas, {m1} y {m2} muestran una correlación "
                        f"{fuerza} {direccion}. {relacion}."
                    ),
                    "icono_fuerza":   _icono_fuerza(fuerza, direccion),
                    # Mantenido internamente para ordenar; no se expone en el reporte
                    "_pearson_r_abs": abs(float(corr)),
                })

    correlaciones.sort(key=lambda x: x["_pearson_r_abs"], reverse=True)
    for c in correlaciones:
        del c["_pearson_r_abs"]
    return correlaciones[:20]


# ──────────────────────────────────────────────
# 5. Oportunidades — con indicador de persistencia (2+ semanas)
# ──────────────────────────────────────────────

def detectar_oportunidades() -> list[dict]:
    """
    Identifica zonas High Priority con métricas por debajo del promedio nacional.
    Marca adicionalmente si llevan 2+ semanas consecutivas bajo la media (oportunidad persistente).

    Returns:
        list[dict]: Oportunidades ordenadas por mayor brecha porcentual, máx 30.
    """
    df = obtener_df_metricas()
    METRICAS_CLAVE = [
        "Lead Penetration", "Perfect Orders", "Pro Adoption (Last Week Status)",
        "Gross Profit UE", "Turbo Adoption",
    ]
    oportunidades = []

    for metrica in METRICAS_CLAVE:
        df_metrica = df[df["METRIC"] == metrica].copy()
        alta_prioridad = df_metrica[
            df_metrica["ZONE_PRIORITIZATION"] == "High Priority"
        ].copy()
        if alta_prioridad.empty:
            continue

        # Medias nacionales para semana actual y semana anterior
        medias_l0 = (
            df_metrica.groupby("COUNTRY")["L0W_ROLL"]
            .mean().reset_index().rename(columns={"L0W_ROLL": "country_mean_l0"})
        )
        medias_l1 = (
            df_metrica.groupby("COUNTRY")["L1W_ROLL"]
            .mean().reset_index().rename(columns={"L1W_ROLL": "country_mean_l1"})
        )

        merged = (
            alta_prioridad
            .merge(medias_l0, on="COUNTRY")
            .merge(medias_l1, on="COUNTRY", how="left")
        )
        por_debajo = merged[
            merged["L0W_ROLL"] < merged["country_mean_l0"]
        ].dropna(subset=["L0W_ROLL"])

        for _, fila in por_debajo.iterrows():
            gap = fila["country_mean_l0"] - fila["L0W_ROLL"]

            # ¿También estaba bajo la media en semana anterior? → oportunidad persistente
            persistente = False
            if pd.notna(fila.get("L1W_ROLL")) and pd.notna(fila.get("country_mean_l1")):
                persistente = fila["L1W_ROLL"] < fila["country_mean_l1"]

            oportunidades.append({
                "country":       fila["COUNTRY"],
                "city":          fila["CITY"],
                "zone":          fila["ZONE"],
                "metric":        metrica,
                "current_value": round(fila["L0W_ROLL"], 4),
                "country_mean":  round(fila["country_mean_l0"], 4),
                "gap":           round(gap, 4),
                "gap_pct":       round(gap / fila["country_mean_l0"] * 100, 2),
                "persistente":   persistente,
                "estado":        "Persistente (2+ sem.)" if persistente else "Nueva",
            })

    oportunidades.sort(key=lambda x: x["gap_pct"], reverse=True)
    return oportunidades[:30]


# ──────────────────────────────────────────────
# 6. Generación de Narrativa con Claude
# ──────────────────────────────────────────────

def _resumir_hallazgos(hallazgos: dict) -> str:
    """
    Construye un resumen compacto de los TOP 5 hallazgos por categoría para enviar
    a Claude. Usa descripciones legibles en lugar de códigos técnicos.

    Args:
        hallazgos (dict): Todos los hallazgos del pipeline analítico.

    Returns:
        str: Texto con los 5 registros más críticos por categoría.
    """
    lineas = []

    # Anomalías: top 5 por magnitud de cambio
    top_anomalias = sorted(
        hallazgos["anomalies"], key=lambda x: abs(x["pct_change"]), reverse=True
    )[:5]
    lineas.append(f"ANOMALÍAS ({len(hallazgos['anomalies'])} total, top 5 más graves):")
    for a in top_anomalias:
        lineas.append(
            f"  - {a['zone']} ({a['country']}): {a['metric']} "
            f"{a['pct_change']:+.1f}% "
            f"({a['valor_semana_anterior']:.3f} → {a['valor_semana_actual']:.3f})"
        )

    # Tendencias: top 5 por semanas de deterioro
    top_tendencias = sorted(
        hallazgos["concerning_trends"],
        key=lambda x: (-x["decline_weeks"], x["total_pct_change"])
    )[:5]
    lineas.append(f"\nTENDENCIAS ({len(hallazgos['concerning_trends'])} total, top 5 más crónicas):")
    for t in top_tendencias:
        lineas.append(
            f"  - {t['zone']} ({t['country']}): {t['metric']} "
            f"cayó {t['total_pct_change']:.1f}% en {t['decline_weeks']} semanas "
            f"({t['inicio_deterioro']} → {t['fin_deterioro']})"
        )

    # Benchmarking: top 5 por brecha
    top_brechas = sorted(
        hallazgos["benchmark_gaps"], key=lambda x: x["pct_below_mean"]
    )[:5]
    lineas.append(f"\nBENCHMARKING ({len(hallazgos['benchmark_gaps'])} total, top 5 mayor brecha):")
    for b in top_brechas:
        lineas.append(
            f"  - {b['zone']} ({b['country']}): {b['metric']} "
            f"{b['pct_below_mean']:.1f}% bajo media del grupo — brecha {b['tendencia_brecha']}"
        )

    # Correlaciones: top 5 (ya ordenadas por magnitud)
    top_corrs = hallazgos["correlations"][:5]
    lineas.append(f"\nCORRELACIONES ({len(hallazgos['correlations'])} total):")
    for c in top_corrs:
        lineas.append(f"  - {c['interpretacion']}")

    # Oportunidades: top 5 por gap
    top_opps = sorted(
        hallazgos["opportunities"], key=lambda x: x["gap_pct"], reverse=True
    )[:5]
    lineas.append(f"\nOPORTUNIDADES HIGH PRIORITY ({len(hallazgos['opportunities'])} total, top 5):")
    for o in top_opps:
        persistencia = " [persistente]" if o["persistente"] else ""
        lineas.append(
            f"  - {o['zone']} ({o['country']}): {o['metric']} "
            f"{o['gap_pct']:.1f}% bajo media nacional{persistencia}"
        )

    return "\n".join(lineas)


def generar_narrativa(hallazgos: dict, cliente: anthropic.Anthropic) -> dict:
    """
    Genera la narrativa ejecutiva con DOS llamadas separadas a Claude en texto libre.

    Args:
        hallazgos (dict): Resultados de los 5 análisis automáticos.
        cliente (anthropic.Anthropic): Cliente de Anthropic autenticado.

    Returns:
        dict: {"resumen_ejecutivo": str, "recomendaciones": str}
    """
    resumen_hallazgos = _resumir_hallazgos(hallazgos)

    # ── Llamada 1: Resumen ejecutivo ─────────────
    prompt_resumen = f"""Eres un analista senior de operaciones de Rappi. Analiza estos hallazgos y escribe un RESUMEN EJECUTIVO conciso para la alta dirección.

Datos analizados:
{resumen_hallazgos}

INSTRUCCIONES:
- Máximo 150 palabras
- Identifica los TOP 3-5 hallazgos más críticos para el negocio
- Prioriza por impacto: primero lo que más afecta órdenes y rentabilidad
- Tono directo, sin tecnicismos
- Formato: párrafo único seguido de lista de 3-5 bullets con los hallazgos críticos
- Cada bullet debe indicar: qué pasó, dónde y qué tan grave es"""

    resp_resumen = cliente.messages.create(
        model=MODELO,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt_resumen}],
    )
    texto_resumen = resp_resumen.content[0].text.strip()

    # ── Llamada 2: Recomendaciones ───────────────
    prompt_recomendaciones = f"""Eres un analista senior de operaciones de Rappi. Basándote en estos hallazgos operacionales, genera recomendaciones accionables.

Datos analizados:
{resumen_hallazgos}

INSTRUCCIONES:
- Máximo 200 palabras en total
- Una recomendación específica por cada categoría con hallazgos (anomalías, tendencias, benchmarking, correlaciones, oportunidades)
- Formato por recomendación:
  **[Categoría]:** Acción concreta + zona/país específico + resultado esperado
- Las acciones deben ser ejecutables esta semana, no estrategias genéricas
- Prioriza por urgencia: primero deterioros, luego oportunidades"""

    resp_recomendaciones = cliente.messages.create(
        model=MODELO,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt_recomendaciones}],
    )
    texto_recomendaciones = resp_recomendaciones.content[0].text.strip()

    return {
        "resumen_ejecutivo": texto_resumen,
        "recomendaciones":   texto_recomendaciones,
    }


# ──────────────────────────────────────────────
# 7. Generación del Reporte HTML Completo
# ──────────────────────────────────────────────

def _md_to_html(texto: str) -> str:
    """
    Normaliza bullets no estándar de Claude (•, –, —) y convierte markdown a HTML.

    Args:
        texto (str): Texto en markdown generado por Claude.

    Returns:
        str: HTML listo para renderizar con | safe en Jinja2.
    """
    import markdown as _md
    texto = _re.sub(r'^[•–—]\s+', '- ', texto, flags=_re.MULTILINE)
    return _md.markdown(texto, extensions=["nl2br"])


def generar_reporte_html(cliente: anthropic.Anthropic, callback_progreso=None) -> str:
    """
    Ejecuta el pipeline completo de insights y genera un reporte HTML descargable.

    Args:
        cliente (anthropic.Anthropic): Cliente de Anthropic autenticado.
        callback_progreso (callable): Función (mensaje: str, porcentaje: int) → None.

    Returns:
        str: Ruta absoluta al archivo HTML generado.
    """
    os.makedirs(DIRECTORIO_REPORTES, exist_ok=True)

    # Métricas de cobertura del análisis
    df_cob = obtener_df_metricas()
    n_zonas    = int(df_cob["ZONE"].nunique())
    n_paises   = int(df_cob["COUNTRY"].nunique())
    n_metricas = int(df_cob["METRIC"].nunique())

    if callback_progreso:
        callback_progreso("Detectando anomalías...", 10)
    anomalias = detectar_anomalias()

    # Orden canónico de períodos: más reciente primero
    _orden_periodos = [
        f"{semana_a_texto(COLS_SEMANAS_METRICAS[i])} → {semana_a_texto(COLS_SEMANAS_METRICAS[i + 1])}"
        for i in range(len(COLS_SEMANAS_METRICAS) - 2, -1, -1)
    ]

    # Separar en deterioro (caídas) y mejora (alzas)
    anomalias_deterioro = [a for a in anomalias if a.get("pct_change", 0) < -10]
    anomalias_mejora    = [a for a in anomalias if a.get("pct_change", 0) > 10]

    # Períodos disponibles en cada sub-lista
    _set_deterioro     = {a["periodo_comparado"] for a in anomalias_deterioro}
    periodos_deterioro = [p for p in _orden_periodos if p in _set_deterioro]

    _set_mejora     = {a["periodo_comparado"] for a in anomalias_mejora}
    periodos_mejora = [p for p in _orden_periodos if p in _set_mejora]

    # Métricas únicas en cada sub-lista (orden alfabético)
    metricas_deterioro = sorted({a["metric"] for a in anomalias_deterioro})
    metricas_mejora    = sorted({a["metric"] for a in anomalias_mejora})

    if callback_progreso:
        callback_progreso("Analizando tendencias semana a semana...", 25)
    tendencias = detectar_tendencias_preocupantes()

    if callback_progreso:
        callback_progreso("Calculando brechas de benchmark...", 40)
    benchmarks = detectar_brechas_benchmark()

    if callback_progreso:
        callback_progreso("Calculando correlaciones entre métricas...", 55)
    correlaciones = calcular_correlaciones()

    if callback_progreso:
        callback_progreso("Identificando oportunidades estratégicas...", 70)
    oportunidades = detectar_oportunidades()

    hallazgos = {
        "anomalies":                   anomalias,
        "anomalies_top5":              anomalias[:5],
        "anomalies_deterioro":         anomalias_deterioro,
        "anomalies_deterioro_top5":    anomalias_deterioro[:5],
        "anomalies_mejora":            anomalias_mejora,
        "anomalies_mejora_top5":       anomalias_mejora[:5],
        "concerning_trends":           tendencias,
        "concerning_trends_top5": tendencias[:5],
        "benchmark_gaps":         benchmarks,
        "benchmark_gaps_top5":    benchmarks[:5],
        "correlations":           correlaciones,
        "correlations_top5":      correlaciones[:5],
        "opportunities":          oportunidades,
        "opportunities_top5":     oportunidades[:5],
        "metadata": {
            "generated_at":          datetime.datetime.now().isoformat(),
            "n_anomalies":           len(anomalias),
            "n_anomalias_deterioro": sum(1 for a in anomalias if a.get("pct_change", 0) < -10),
            "n_anomalias_mejora":    sum(1 for a in anomalias if a.get("pct_change", 0) > 10),
            "n_trends":              len(tendencias),
            "n_benchmarks":          len(benchmarks),
            "n_correlations":        len(correlaciones),
            "n_opportunities":       len(oportunidades),
            # Cobertura del análisis
            "n_zonas":               n_zonas,
            "n_paises":              n_paises,
            "n_metricas":            n_metricas,
        },
    }

    if callback_progreso:
        callback_progreso("Generando resumen ejecutivo con IA...", 80)

    if callback_progreso:
        callback_progreso("Generando recomendaciones con IA...", 88)

    narrativa = generar_narrativa(hallazgos, cliente)

    # Convertir markdown → HTML real (negritas, bullets, títulos)
    narrativa["resumen_ejecutivo"] = _md_to_html(narrativa["resumen_ejecutivo"])
    narrativa["recomendaciones"]   = _md_to_html(narrativa["recomendaciones"])

    if callback_progreso:
        callback_progreso("Renderizando reporte HTML...", 95)

    env = Environment(loader=FileSystemLoader(DIRECTORIO_PLANTILLAS))
    plantilla = env.get_template("report_template.html")

    html = plantilla.render(
        narrative=narrativa,
        findings=hallazgos,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        model=MODELO,
        periodos_deterioro=periodos_deterioro,
        periodos_mejora=periodos_mejora,
        metricas_deterioro=metricas_deterioro,
        metricas_mejora=metricas_mejora,
    )

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"rappi_insights_{timestamp}.html"
    ruta_archivo = os.path.join(DIRECTORIO_REPORTES, nombre_archivo)

    with open(ruta_archivo, "w", encoding="utf-8") as f:
        f.write(html)

    if callback_progreso:
        callback_progreso("¡Reporte generado exitosamente!", 100)

    return ruta_archivo


# Alias de compatibilidad
generate_html_report = generar_reporte_html

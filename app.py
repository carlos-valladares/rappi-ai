"""
Rappi AI — Aplicación principal Streamlit.
Tab 1: Chatbot conversacional con herramientas Claude (tool use).
Tab 2: Generación automática de reporte ejecutivo de insights.
"""

import os
import json
import sys
import random

# Agregar raíz del proyecto al path para que los imports funcionen correctamente
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import anthropic
from dotenv import load_dotenv

from tools.data_loader import (
    obtener_df_metricas, obtener_df_ordenes,
    obtener_metricas_disponibles, obtener_paises_disponibles, obtener_tipos_zona_disponibles,
    COLS_SEMANAS_METRICAS, COLS_SEMANAS_ORDENES
)
from tools.query_tools import DEFINICIONES_HERRAMIENTAS, despachar_herramienta
from tools.insights_engine import generar_reporte_html
from prompts.system_prompt import SYSTEM_PROMPT

load_dotenv()

# ──────────────────────────────────────────────
# Configuración de página
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="Rappi Analytics",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ──────────────────────────────────────────────
# Estilos CSS personalizados
# ──────────────────────────────────────────────
st.markdown("""
<style>
  /* Ocultar elementos de UI de Streamlit — display + visibility para cubrir carga inicial */
  .stDeployButton                    { display: none !important; visibility: hidden !important; opacity: 0 !important; }
  [data-testid="stDeployButton"]     { display: none !important; visibility: hidden !important; opacity: 0 !important; }
  .stAppDeployButton                 { display: none !important; visibility: hidden !important; opacity: 0 !important; }
  button[kind="deployButton"]        { display: none !important; visibility: hidden !important; opacity: 0 !important; }
  #MainMenu                          { display: none !important; visibility: hidden !important; opacity: 0 !important; }
  footer                             { display: none !important; }

  /* Fondo principal */
  .stApp { background-color: #f8f9fa; }

  /* Header con identidad Rappi */
  .rappi-header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    color: white;
    padding: 1.2rem 1.5rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    border-left: 5px solid #FF441F;
  }
  .rappi-header h1 { font-size: 1.4rem; font-weight: 700; margin: 0; }
  .rappi-header p  { font-size: 0.85rem; opacity: 0.7; margin: 0.2rem 0 0; }

  /* Burbujas de chat — usuario */
  .chat-user {
    background: #FF441F;
    color: white;
    border-radius: 12px 12px 2px 12px;
    padding: 0.8rem 1.1rem;
    margin: 0.5rem 0;
    max-width: 80%;
    margin-left: auto;
    font-size: 0.92rem;
  }

  /* Burbujas de chat — asistente */
  .chat-assistant {
    background: white;
    border: 1px solid #e8e8e8;
    border-radius: 12px 12px 12px 2px;
    padding: 0.8rem 1.1rem;
    margin: 0.5rem 0;
    max-width: 85%;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    font-size: 0.92rem;
  }

  /* Chips / botones de sugerencia */
  .stButton > button {
    background: #fff5f5;
    color: #FF441F;
    border: 1px solid #FF441F;
    border-radius: 20px;
    font-size: 0.82rem;
    padding: 0.3rem 0.9rem;
    transition: all 0.2s;
  }
  .stButton > button:hover {
    background: #FF441F;
    color: white;
  }

  /* Chip de métrica disponible */
  .metric-chip {
    display: inline-block;
    background: #e8f4fd;
    color: #2980b9;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.75rem;
    margin: 2px;
  }

  /* Estilo de pestañas */
  .stTabs [data-baseweb="tab"] { font-size: 1rem; }
  .stTabs [data-baseweb="tab-highlight"] { background-color: #FF441F !important; }

  /* Badge de herramienta en uso */
  .tool-badge {
    background: #fff3cd;
    border: 1px solid #ffc107;
    border-radius: 6px;
    padding: 0.3rem 0.6rem;
    font-size: 0.78rem;
    color: #856404;
    margin-bottom: 0.5rem;
  }

  /* Contador de mensajes */
  .contador-mensajes {
    font-size: 0.75rem;
    color: #999;
    text-align: right;
    margin-bottom: 0.5rem;
  }

  /* Mensaje de bienvenida */
  .bienvenida {
    background: linear-gradient(135deg, #fff5f5 0%, #fff 100%);
    border: 1px solid #FFD5CC;
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 1rem;
    font-size: 0.95rem;
  }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
# Cliente de Anthropic (singleton cacheado)
# ──────────────────────────────────────────────

@st.cache_resource
def obtener_cliente() -> anthropic.Anthropic:
    """
    Crea y cachea el cliente de Anthropic reutilizable entre sesiones.

    Returns:
        anthropic.Anthropic: Cliente autenticado con la API key del .env.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("❌ ANTHROPIC_API_KEY no encontrada en el archivo .env")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


MODELO = "claude-sonnet-4-5"


# ──────────────────────────────────────────────
# Inicialización del estado de sesión
# ──────────────────────────────────────────────

def inicializar_sesion() -> None:
    """
    Inicializa todas las variables de estado de sesión necesarias
    si aún no existen en st.session_state.
    """
    if "mensajes" not in st.session_state:
        st.session_state.mensajes = []
    if "sugerencias" not in st.session_state:
        st.session_state.sugerencias = []
    if "entrada_pendiente" not in st.session_state:
        st.session_state.entrada_pendiente = None
    if "filtro_pais" not in st.session_state:
        st.session_state.filtro_pais = "Todos los países"
    if "filtro_tipo_zona" not in st.session_state:
        st.session_state.filtro_tipo_zona = "Todos los tipos"
    if "filtro_priorizacion" not in st.session_state:
        st.session_state.filtro_priorizacion = "Todas las prioridades"
    if "historial_herramientas" not in st.session_state:
        # Mapea interaction_id (índice de mensaje de usuario) → {"pregunta": str, "resultados": list}
        st.session_state.historial_herramientas = {}


# ──────────────────────────────────────────────
# Constantes de visualización
# ──────────────────────────────────────────────

_SEMANAS_LEGIBLES = {
    "L8W_ROLL": "Hace 8 sem", "L7W_ROLL": "Hace 7 sem", "L6W_ROLL": "Hace 6 sem",
    "L5W_ROLL": "Hace 5 sem", "L4W_ROLL": "Hace 4 sem", "L3W_ROLL": "Hace 3 sem",
    "L2W_ROLL": "Hace 2 sem", "L1W_ROLL": "Sem. anterior", "L0W_ROLL": "Sem. actual",
    "L8W": "Hace 8 sem", "L7W": "Hace 7 sem", "L6W": "Hace 6 sem",
    "L5W": "Hace 5 sem", "L4W": "Hace 4 sem", "L3W": "Hace 3 sem",
    "L2W": "Hace 2 sem", "L1W": "Sem. anterior", "L0W": "Sem. actual",
}

# Columnas que identifican un DataFrame de series temporales (formato largo)
_COLS_SEMANA_CLAVES = {"L0W", "L1W", "L2W", "L3W", "L4W", "L5W", "L6W", "L7W", "L8W",
                       "L0W_ROLL", "L1W_ROLL", "L2W_ROLL", "L3W_ROLL", "L4W_ROLL",
                       "L5W_ROLL", "L6W_ROLL", "L7W_ROLL", "L8W_ROLL"}


# ──────────────────────────────────────────────
# Funciones de visualización (simples y directas)
# ──────────────────────────────────────────────

def _es_df_temporal(df: pd.DataFrame) -> bool:
    """True si el DataFrame contiene una columna 'semana' con datos temporales."""
    return "semana" in df.columns and len(df) >= 2


def graficar_tendencia(df: pd.DataFrame, titulo: str) -> None:
    """Gráfico de líneas para datos de serie temporal (columna 'semana' + valor)."""
    df = df.copy()
    df["semana"] = df["semana"].map(lambda v: _SEMANAS_LEGIBLES.get(v, v))

    col_y = "value" if "value" in df.columns else ("orders" if "orders" in df.columns else None)
    if col_y is None:
        return

    fig = px.line(
        df, x="semana", y=col_y,
        markers=True,
        title=titulo,
        template="plotly_white",
        color_discrete_sequence=["#FF441A"],
    )
    fig.update_traces(line_width=2.5, marker_size=8)
    fig.update_layout(height=400, margin=dict(t=50, b=40, l=50, r=20))
    st.plotly_chart(fig, use_container_width=True)


def graficar_comparacion(df: pd.DataFrame, titulo: str) -> None:
    """Gráfico de barras horizontales para comparar categorías."""
    # Primera columna de texto = etiqueta; primera numérica = valor
    col_label = next((c for c in df.columns if df[c].dtype == object), None)
    col_valor  = next((c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])), None)
    if col_label is None or col_valor is None:
        return

    df_plot = df[[col_label, col_valor]].dropna().sort_values(col_valor, ascending=True)
    if len(df_plot) < 2:
        return

    fig = px.bar(
        df_plot, x=col_valor, y=col_label,
        orientation="h",
        title=titulo,
        template="plotly_white",
        color_discrete_sequence=["#FF441A"],
    )
    fig.update_layout(height=400, margin=dict(t=50, b=40, l=50, r=20))
    st.plotly_chart(fig, use_container_width=True)


def renderizar_grafico(df: pd.DataFrame, titulo: str) -> None:
    """
    Decide y renderiza UN solo gráfico basándose únicamente en la estructura del DataFrame.
    - Tiene columna 'semana' → líneas
    - No tiene → barras horizontales
    Requiere mínimo 2 filas; no renderiza nada si no se cumple.
    """
    if df is None or df.empty or len(df) < 2:
        return
    if _es_df_temporal(df):
        graficar_tendencia(df, titulo)
    else:
        graficar_comparacion(df, titulo)


def renderizar_tabla_con_exportacion(
    datos: list[dict],
    nombre_herramienta: str,
    key_prefix: str,
) -> pd.DataFrame | None:
    """
    Renderiza una tabla formateada con botones de exportación CSV y HTML/PDF.

    Args:
        datos (list[dict]): Lista de registros a mostrar.
        nombre_herramienta (str): Nombre de la herramienta (usado en el nombre de archivo).
        key_prefix (str): Prefijo único para las keys de los botones Streamlit.

    Returns:
        pd.DataFrame | None: El DataFrame renderizado, o None si datos vacíos.
    """
    if not datos or not isinstance(datos, list):
        return None
    try:
        df = pd.DataFrame(datos)
        cols_float = df.select_dtypes(include="float").columns
        formato = {c: "{:.4f}" for c in cols_float}
        st.dataframe(df.style.format(formato, na_rep="—"), use_container_width=True)

        # Keys únicas: combinan el prefijo estable con hash del contenido
        data_hash = abs(hash(str(datos[:3]))) % 100000
        k_csv = f"csv_{key_prefix}_{data_hash}"
        k_pdf = f"pdf_{key_prefix}_{data_hash}"

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="⬇️ Exportar CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"rappi_{nombre_herramienta}.csv",
                mime="text/csv",
                key=k_csv,
            )
        with col2:
            html_tabla = (
                "<html><head><style>"
                "body{font-family:Arial,sans-serif;padding:20px;}"
                "table{border-collapse:collapse;width:100%;}"
                "th{background:#FF441A;color:white;padding:8px 12px;}"
                "td{border:1px solid #ddd;padding:8px 12px;}"
                "tr:nth-child(even){background:#f9f9f9;}"
                "</style></head><body>"
                "<h3>Rappi Analytics — Resultado</h3>"
                f"{df.to_html(index=False)}"
                "</body></html>"
            )
            st.download_button(
                label="⬇️ Exportar HTML/PDF",
                data=html_tabla.encode("utf-8"),
                file_name=f"rappi_{nombre_herramienta}.html",
                mime="text/html",
                help="Descarga como HTML. Ábrelo en el navegador y usa Ctrl+P para guardar como PDF.",
                key=k_pdf,
            )
        return df
    except Exception as e:
        st.error(f"❌ Error al renderizar tabla: {e}")
        return None


# ──────────────────────────────────────────────
# Banco de sugerencias contextuales
# ──────────────────────────────────────────────

BANCO_SUGERENCIAS = [
    "¿Cuáles son las 5 zonas con mayor Lead Penetration esta semana?",
    "Compara el Perfect Orders entre zonas Wealthy y Non Wealthy",
    "¿Cuál es el promedio de Lead Penetration por país?",
    "Muestra la evolución de Gross Profit UE en las últimas 8 semanas para Valle Real",
    "¿Qué zonas tienen alto Lead Penetration pero bajo Perfect Orders?",
    "¿Cuáles son las zonas con mayor caída en Pro Adoption esta semana?",
    "¿Cuál es el promedio de Perfect Orders por tipo de zona?",
    "Muestra las 10 zonas con menor Gross Profit UE",
    "¿Qué países tienen mejor Turbo Adoption?",
    "¿Cuáles son las oportunidades de mejora en zonas High Priority de Colombia?",
    "Compara Non-Pro PTC > OP entre países",
    "¿Qué zonas de Brasil tienen mayor Restaurants SS > ATC CVR?",
    "Muestra la evolución de órdenes en Chapinero",
    "¿Cuáles son las zonas con mejor MLTV Top Verticals Adoption en México?",
]

# Sugerencias contextuales según la última herramienta usada
SUGERENCIAS_CONTEXTUALES = {
    "filter_zones": [
        "¿Cuál es la tendencia de esta métrica en la semana anterior?",
        "Compara esta métrica entre zonas Wealthy y Non Wealthy",
        "¿Cuáles son las zonas con menor valor en esta misma métrica?",
    ],
    "compare_metrics": [
        "¿Qué zonas específicas están jalando el promedio hacia abajo?",
        "Muestra las top 5 zonas en esta métrica",
        "¿Cómo ha evolucionado este indicador en las últimas 8 semanas?",
    ],
    "get_trend": [
        "¿Cómo se compara esto con el promedio de su país?",
        "¿Qué otras métricas muestran tendencia similar en esta zona?",
        "Muestra también la evolución de órdenes en esta zona",
    ],
    "aggregate_by": [
        "¿Qué países están por debajo del promedio general?",
        "Desglosa esto por tipo de zona (Wealthy/Non Wealthy)",
        "¿Cuál es el top 5 de zonas en esta métrica?",
    ],
    "multivariable_analysis": [
        "¿Cuántas zonas críticas están en High Priority?",
        "Muestra la tendencia de estas zonas en las últimas semanas",
        "¿Qué porcentaje representa esto del total de zonas?",
    ],
    "get_orders_trend": [
        "¿Cómo se compara el volumen con otras zonas de la ciudad?",
        "¿Cuál es la tendencia de Perfect Orders en esta zona?",
        "Muestra el top de zonas por volumen de órdenes en este país",
    ],
}


def obtener_sugerencias(ultima_herramienta: str = None) -> list[str]:
    """
    Retorna 3 preguntas de seguimiento contextuales o aleatorias del banco.

    Args:
        ultima_herramienta (str): Nombre de la última herramienta invocada.
                                   Si hay sugerencias contextuales, se priorizan.

    Returns:
        list[str]: Lista de 3 preguntas sugeridas.
    """
    if ultima_herramienta and ultima_herramienta in SUGERENCIAS_CONTEXTUALES:
        # Combinar sugerencias contextuales con 2 del banco general
        grupo = SUGERENCIAS_CONTEXTUALES[ultima_herramienta] + random.sample(BANCO_SUGERENCIAS, 2)
        return grupo[:3]
    return random.sample(BANCO_SUGERENCIAS, 3)


# ──────────────────────────────────────────────
# Motor de chat con Claude
# ──────────────────────────────────────────────

def chatear_con_claude(
    mensaje_usuario: str,
    filtro_pais: str = None,
    filtro_zona: str = None,
) -> None:
    """
    Envía el mensaje del usuario a Claude con streaming, ejecuta el bucle de herramientas
    y actualiza el estado de sesión con la respuesta y visualizaciones.

    Args:
        mensaje_usuario (str): Pregunta o instrucción del usuario.
        filtro_pais (str): País seleccionado en el sidebar (opcional).
        filtro_zona (str): Tipo de zona seleccionado en el sidebar (opcional).
    """
    cliente = obtener_cliente()

    # Construir historial de mensajes para la API
    api_mensajes = []
    for msg in st.session_state.mensajes:
        api_mensajes.append({"role": msg["role"], "content": msg["content"]})
    api_mensajes.append({"role": "user", "content": mensaje_usuario})

    # Agregar mensaje del usuario al historial de sesión
    st.session_state.mensajes.append({"role": "user", "content": mensaje_usuario})

    # Enriquecer el system prompt con contexto de filtros activos
    system = SYSTEM_PROMPT
    if filtro_pais and filtro_pais not in ("Todos los países", "Todos"):
        system += f"\n\nFiltro activo: el usuario está interesado principalmente en el país {filtro_pais}."
    if filtro_zona and filtro_zona not in ("Todos los tipos", "Todos"):
        system += f"\nFiltro activo: el usuario quiere ver principalmente zonas de tipo '{filtro_zona}'."

    with st.chat_message("assistant", avatar="🛵"):
        resultados_herramientas_display = []
        ultima_herramienta = None

        # Bucle agéntico: continúa hasta que Claude deje de llamar herramientas
        while True:
            placeholder = st.empty()
            placeholder.markdown("_Analizando datos..._")
            texto_iteracion = ""

            # Streaming: muestra el texto progresivamente
            with cliente.messages.stream(
                model=MODELO,
                max_tokens=2048,
                system=system,
                tools=DEFINICIONES_HERRAMIENTAS,
                messages=api_mensajes,
            ) as stream:
                for texto in stream.text_stream:
                    texto_iteracion += texto
                    placeholder.markdown(texto_iteracion + "▌")

                if texto_iteracion:
                    placeholder.markdown(texto_iteracion)
                else:
                    placeholder.empty()

                respuesta = stream.get_final_message()

            # Separar bloques de herramienta de la respuesta final
            bloques_herramienta = [
                b for b in respuesta.content if b.type == "tool_use"
            ]

            # Sin más herramientas → respuesta final, salir del bucle
            if respuesta.stop_reason == "end_turn" or not bloques_herramienta:
                st.session_state.mensajes.append({
                    "role": "assistant",
                    "content": respuesta.content,
                })
                break

            # Procesar cada herramienta invocada
            resultados_herramientas = []
            for bloque in bloques_herramienta:
                ultima_herramienta = bloque.name

                st.markdown(
                    f'<div class="tool-badge">🔧 Consultando: <code>{bloque.name}</code></div>',
                    unsafe_allow_html=True,
                )

                with st.spinner(f"Ejecutando {bloque.name}..."):
                    resultado_str = despachar_herramienta(bloque.name, bloque.input)

                resultado_datos = json.loads(resultado_str)
                resultados_herramientas_display.append((bloque.name, resultado_datos))

                resultados_herramientas.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": resultado_str,
                })

            # Actualizar historial de la API para la siguiente iteración
            api_mensajes.append({"role": "assistant", "content": respuesta.content})
            api_mensajes.append({"role": "user", "content": resultados_herramientas})

        # Mostrar errores inline durante la generación activa
        for _, datos_resultado in resultados_herramientas_display:
            if "error" in datos_resultado:
                st.warning(f"⚠️ No encontré datos para esa consulta. {datos_resultado['error']}")

        # Persistir resultados de herramientas con ID estable (índice del mensaje de usuario)
        interaction_id = sum(1 for m in st.session_state.mensajes if m["role"] == "user") - 1
        st.session_state.historial_herramientas[interaction_id] = {
            "pregunta": mensaje_usuario,
            "resultados": resultados_herramientas_display,
        }

        # Generar sugerencias de seguimiento contextuales
        st.session_state.sugerencias = obtener_sugerencias(ultima_herramienta)


# ──────────────────────────────────────────────
# TAB 1: ASISTENTE DE DATOS (CHATBOT)
# ──────────────────────────────────────────────

def renderizar_tab_chatbot() -> None:
    """
    Renderiza el tab de chatbot conversacional con:
    - Sidebar con filtros, ejemplos y métricas disponibles
    - Header principal
    - Historial de conversación con avatares
    - Chips de preguntas sugeridas
    - Input de texto para el usuario
    """
    # ── Sidebar ──────────────────────────────────
    with st.sidebar:
        st.markdown("## ⚙️ Filtros")

        # Filtro de país
        paises = ["Todos los países"] + obtener_paises_disponibles()
        st.session_state.filtro_pais = st.selectbox(
            "País", paises, key="sb_pais"
        )

        # Filtro de tipo de zona
        tipos_zona = ["Todos los tipos"] + obtener_tipos_zona_disponibles()
        st.session_state.filtro_tipo_zona = st.selectbox(
            "Tipo de zona", tipos_zona, key="sb_tipo_zona"
        )

        # Filtro de priorización (valores fijos del negocio)
        opciones_prioridad = [
            "Todas las prioridades", "High Priority", "Prioritized", "Not Prioritized"
        ]
        st.session_state.filtro_priorizacion = st.selectbox(
            "Priorización", opciones_prioridad, key="sb_priorizacion"
        )

        st.markdown("---")

        # Sección de ejemplos de preguntas clicables
        st.markdown("## 💡 Ejemplos de preguntas")
        preguntas_ejemplo = [
            "¿Cuáles son las 5 zonas con mayor Lead Penetration?",
            "Compara Perfect Orders entre Wealthy y Non Wealthy",
            "¿Cuál es el promedio de Gross Profit UE por país?",
            "¿Qué zonas High Priority están bajo la media nacional?",
            "Muestra la evolución de órdenes en Chapinero",
        ]
        for pregunta in preguntas_ejemplo:
            if st.button(pregunta, key=f"ej_{hash(pregunta)}", use_container_width=True):
                st.session_state.entrada_pendiente = pregunta
                st.rerun()

        st.markdown("---")

        # Métricas disponibles
        st.markdown("### 📈 Métricas disponibles")
        for m in obtener_metricas_disponibles():
            st.markdown(f'<span class="metric-chip">{m}</span>', unsafe_allow_html=True)

        st.markdown("---")

        # Botón para limpiar conversación
        if st.button("🗑️ Nueva conversación", use_container_width=True):
            st.session_state.mensajes = []
            st.session_state.sugerencias = []
            st.rerun()

    # ── Header principal ─────────────────────────
    st.markdown("""
    <div class="rappi-header">
      <h1>🛵 Rappi — Análisis Inteligente de Operaciones</h1>
      <p>Consulta métricas operacionales en lenguaje natural</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Contador de mensajes ─────────────────────
    n_mensajes = len(st.session_state.mensajes)
    if n_mensajes > 0:
        st.markdown(
            f'<div class="contador-mensajes">{n_mensajes} mensaje{"s" if n_mensajes != 1 else ""} en esta conversación</div>',
            unsafe_allow_html=True
        )

    # ── Historial del chat ───────────────────────
    contenedor_chat = st.container()
    with contenedor_chat:
        # Mensaje de bienvenida cuando no hay conversación
        if not st.session_state.mensajes:
            st.markdown("""
            <div class="bienvenida">
              👋 Hola, soy tu asistente de análisis operacional de Rappi. Puedo ayudarte a explorar métricas
              por zona, país y período de tiempo. <strong>¿Qué quieres analizar hoy?</strong>
            </div>
            """, unsafe_allow_html=True)

        # Renderizar historial de mensajes con avatares diferenciados
        user_idx = -1
        for msg in st.session_state.mensajes:
            if msg["role"] == "user":
                user_idx += 1
                with st.chat_message("user", avatar="👤"):
                    st.markdown(msg["content"])
            else:
                # Avatar del asistente (Rappi)
                with st.chat_message("assistant", avatar="🛵"):
                    contenido = msg["content"]
                    if isinstance(contenido, list):
                        for bloque in contenido:
                            if hasattr(bloque, "type") and bloque.type == "text":
                                st.markdown(bloque.text)
                            elif isinstance(bloque, dict) and bloque.get("type") == "text":
                                st.markdown(bloque["text"])
                    elif isinstance(contenido, str):
                        st.markdown(contenido)

                    # Renderizar todas las tablas de la interacción en UN SOLO expander,
                    # luego graficar UN SOLO resultado al final.
                    entrada = st.session_state.historial_herramientas.get(user_idx)
                    if entrada:
                        pregunta_hist = entrada["pregunta"]
                        candidatos = []  # (df, es_temporal)

                        # Recolectar solo resultados válidos con datos
                        resultados_validos = []
                        for h_idx, (h_tool, h_data) in enumerate(entrada["resultados"]):
                            if "error" in h_data:
                                continue
                            h_clave = (
                                "data" if "data" in h_data
                                else ("trend" if "trend" in h_data else None)
                            )
                            if h_clave and isinstance(h_data.get(h_clave), list) and h_data[h_clave]:
                                resultados_validos.append(
                                    (h_idx, h_tool, h_data[h_clave])
                                )

                        # Un solo expander para todos los resultados de esta interacción
                        if resultados_validos:
                            with st.expander("📊 Ver datos de la consulta", expanded=True):
                                for h_idx, h_tool, h_filas in resultados_validos:
                                    if len(resultados_validos) > 1:
                                        st.caption(f"🔧 {h_tool}")
                                    h_key = f"h{user_idx}_{h_idx}"
                                    df_h  = renderizar_tabla_con_exportacion(
                                        h_filas, h_tool, h_key
                                    )
                                    if df_h is not None:
                                        candidatos.append((df_h, _es_df_temporal(df_h)))
                                    if h_idx < len(resultados_validos) - 1:
                                        st.divider()

                        # Un solo gráfico: preferir temporal, sino el df más grande
                        if candidatos:
                            temporales = [(d, t) for d, t in candidatos if t]
                            elegido_df = (
                                temporales[0][0]
                                if temporales
                                else max(candidatos, key=lambda x: len(x[0]))[0]
                            )
                            renderizar_grafico(elegido_df, pregunta_hist[:80])

    # ── Chips de sugerencias de seguimiento ──────
    if st.session_state.sugerencias:
        st.markdown("**💡 Preguntas sugeridas:**")
        cols = st.columns(len(st.session_state.sugerencias))
        for i, sugerencia in enumerate(st.session_state.sugerencias):
            with cols[i]:
                if st.button(sugerencia, key=f"sug_{i}_{hash(sugerencia)}"):
                    st.session_state.entrada_pendiente = sugerencia
                    st.rerun()

    elif not st.session_state.mensajes:
        # Preguntas iniciales cuando no hay conversación
        st.markdown("**💡 Empieza con una de estas preguntas:**")
        preguntas_inicio = [
            "¿Cuáles son las 5 zonas con mayor Lead Penetration esta semana?",
            "Compara el Perfect Orders entre zonas Wealthy y Non Wealthy",
            "¿Cuál es el promedio de Lead Penetration por país?",
        ]
        cols = st.columns(3)
        for i, q in enumerate(preguntas_inicio):
            with cols[i]:
                if st.button(q, key=f"inicio_{i}"):
                    st.session_state.entrada_pendiente = q
                    st.rerun()

    # ── Input del usuario ────────────────────────
    entrada_usuario = st.chat_input(
        "Escribe tu pregunta sobre las métricas operacionales..."
    )

    # Procesar entrada pendiente (desde chips de sugerencia)
    if st.session_state.entrada_pendiente:
        entrada_usuario = st.session_state.entrada_pendiente
        st.session_state.entrada_pendiente = None

    if entrada_usuario:
        chatear_con_claude(
            entrada_usuario,
            filtro_pais=st.session_state.get("filtro_pais"),
            filtro_zona=st.session_state.get("filtro_tipo_zona"),
        )
        st.rerun()


# ──────────────────────────────────────────────
# TAB 2: REPORTE DE INSIGHTS
# ──────────────────────────────────────────────

def renderizar_tab_insights() -> None:
    """
    Renderiza el tab de generación automática de reportes ejecutivos.
    Incluye descripción del análisis, botón de generación, barra de progreso
    y visualización del reporte generado.
    """
    st.markdown("""
    <div class="rappi-header">
      <h1>📊 Reporte de Insights</h1>
      <p>Análisis automático completo impulsado por inteligencia artificial</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("""
        Genera un reporte ejecutivo automático analizando todas las zonas y métricas operacionales. El motor detecta:

        - ⚡ **Anomalías**: zonas con cambios drásticos (>10%) en cualquier métrica, semana a semana, tanto deterioros como mejoras inesperadas
        - 📉 **Tendencias preocupantes**: métricas en deterioro continuo durante 3 o más semanas consecutivas
        - 📊 **Benchmarking**: zonas que rinden más de un 20% por debajo de zonas similares en el mismo país y segmento
        - 🔗 **Correlaciones**: pares de métricas que se mueven juntas — útil para identificar causas raíz (ej: zonas con bajo Lead Penetration también tienden a tener bajo Perfect Order)
        - 🚀 **Oportunidades**: zonas de alta prioridad que están por debajo del promedio nacional y tienen mayor potencial de mejora inmediata
        """)

    with col2:
        generar_btn = st.button(
            "⚡ Generar Reporte Ejecutivo",
            type="primary",
            use_container_width=True
        )

    st.markdown("---")

    if generar_btn:
        cliente = obtener_cliente()
        barra_progreso = st.progress(0)
        texto_estado = st.empty()

        def callback_progreso(mensaje: str, porcentaje: int) -> None:
            """Actualiza la barra de progreso y el mensaje de estado."""
            barra_progreso.progress(porcentaje)
            texto_estado.text(f"⏳ {mensaje}")

        try:
            with st.spinner("Analizando datos y generando reporte con IA..."):
                ruta_archivo = generar_reporte_html(cliente, callback_progreso=callback_progreso)

            barra_progreso.progress(100)
            texto_estado.text("✅ Reporte generado exitosamente")
            st.success("✅ Reporte generado exitosamente")

            # Leer el HTML generado para descarga y previsualización
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                contenido_html = f.read()

            # Botón de descarga HTML
            st.download_button(
                label="⬇️ Descargar como HTML",
                data=contenido_html.encode("utf-8"),
                file_name=os.path.basename(ruta_archivo),
                mime="text/html",
                use_container_width=True,
            )

            # Vista previa del reporte
            st.markdown("### 👁️ Vista previa del reporte")
            with open(ruta_archivo, "r", encoding="utf-8") as f:
                html_preview = f.read()
            st.components.v1.html(html_preview, height=800, scrolling=True)

        except Exception as e:
            st.error(f"❌ Error al generar el reporte: {e}")
            import traceback
            st.code(traceback.format_exc())

    else:
        st.info("Haz clic en '⚡ Generar Reporte Ejecutivo' para crear un reporte.")


# ──────────────────────────────────────────────
# PUNTO DE ENTRADA PRINCIPAL
# ──────────────────────────────────────────────

def main() -> None:
    """
    Función principal de la aplicación. Inicializa el estado de sesión
    y renderiza las dos pestañas de la interfaz.
    """
    inicializar_sesion()

    pestaña1, pestaña2 = st.tabs([
        "💬 Asistente de Datos",
        "📊 Reporte de Insights"
    ])

    with pestaña1:
        renderizar_tab_chatbot()

    with pestaña2:
        renderizar_tab_insights()


if __name__ == "__main__":
    main()

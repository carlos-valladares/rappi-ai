# Documentación Técnica — Rappi AI: Sistema de Análisis Inteligente de Operaciones

> **Formato de entrega:** Este documento está en Markdown para visualización en Git.
> Para exportar a `.docx`, ejecutar: `pandoc docs/documentacion_tecnica.md -o docs/documentacion_tecnica.docx`

---

## 1. Descripción General del Sistema

**Rappi AI** es una aplicación web interactiva que permite analizar métricas operacionales de Rappi en lenguaje natural, sin necesidad de conocimientos técnicos de SQL o análisis de datos.

El sistema ofrece dos capacidades principales:

| Módulo | Descripción |
|--------|-------------|
| **Asistente de Datos** | Chatbot conversacional que responde preguntas en español sobre métricas por zona, país y período usando IA generativa |
| **Reporte de Insights** | Motor de análisis automático que detecta anomalías, tendencias, benchmarks y oportunidades, y genera un reporte ejecutivo HTML |

**Audiencia objetivo:** Equipos de operaciones y estrategia de Rappi que necesitan insights accionables sobre el desempeño de zonas en 9 países de América Latina.

---

## 2. Arquitectura del Sistema

> Ver diagrama de arquitectura: `docs/diagrama_arquitectura.graphml`

El sistema sigue una arquitectura de capas:

```
┌──────────────────────────────────────────────────────┐
│                  FRONTEND (Streamlit)                │
│   Tab 1: Asistente de Datos │ Tab 2: Reporte Insights│
└──────────────────┬──────────────────┬────────────────┘
                   │                  │
        ┌──────────▼──────┐  ┌────────▼────────────┐
        │  Claude API      │  │  Motor de Insights  │
        │ (claude-sonnet-  │  │  (insights_engine)  │
        │    4-5, tool use)│  │                     │
        └──────────┬──────┘  └────────┬────────────┘
                   │                  │
        ┌──────────▼──────────────────▼────────────┐
        │           Herramientas de Consulta        │
        │  filter_zones │ compare_metrics │ get_trend│
        │  aggregate_by │ multivariable   │ orders   │
        └──────────────────────┬───────────────────┘
                               │
        ┌──────────────────────▼───────────────────┐
        │              Capa de Datos                │
        │   data_loader.py + lru_cache              │
        │   data/data.xlsx (RAW_INPUT_METRICS,      │
        │                   RAW_ORDERS)             │
        └──────────────────────────────────────────┘
```

**Patrones arquitectónicos:**
- **Agentic loop:** Claude itera sobre llamadas a herramientas hasta completar la respuesta (tool use + streaming)
- **Cache de datos:** `lru_cache` en Python asegura que el Excel se lee una sola vez por sesión
- **Separación de responsabilidades:** cada módulo tiene una única función bien definida

---

## 3. Tecnologías Utilizadas

| Tecnología | Versión mínima | Justificación |
|-----------|----------------|---------------|
| **Python** | 3.10+ | Ecosistema de datos maduro, compatible con todas las librerías requeridas |
| **Streamlit** | 1.40+ | Framework de apps de datos en Python sin necesidad de frontend separado |
| **Anthropic SDK** | 0.40+ | Acceso a Claude con soporte nativo de tool use y streaming |
| **Pandas** | 2.0+ | Manipulación eficiente de DataFrames para análisis de métricas |
| **Plotly** | 5.18+ | Gráficos interactivos embebibles en Streamlit |
| **Jinja2** | 3.1+ | Renderizado de plantillas HTML para el reporte ejecutivo |
| **SciPy** | 1.11+ | Cálculo de correlaciones de Pearson con prueba de significancia estadística |
| **NumPy** | 1.24+ | Operaciones numéricas de soporte para análisis |
| **OpenPyXL** | 3.1+ | Lectura del archivo Excel con múltiples hojas |
| **python-dotenv** | 1.0+ | Gestión de variables de entorno segura (API keys) |

**Modelo de IA:** `claude-sonnet-4-5` — elegido por su balance entre capacidad de razonamiento, velocidad de respuesta y coste por token.

---

## 4. Flujo de Funcionamiento del Sistema

> Ver diagrama de flujo: `docs/diagrama_flujo.graphml`

### Tab 1 — Asistente de Datos

```
Usuario escribe pregunta
        │
        ▼
Construir historial de mensajes de la sesión
        │
        ▼
Llamar Claude API (modo streaming)
        │
        ├─► ¿Claude invoca herramienta?
        │         │
        │         ▼
        │   Ejecutar herramienta (query_tools.py)
        │   → data_loader.py → data.xlsx
        │         │
        │         ▼
        │   Devolver resultado a Claude
        │         │
        │         └─► Repetir hasta que Claude no llame más herramientas
        │
        ▼
Respuesta final en streaming (texto progresivo)
        │
        ▼
Guardar en session_state (historial_herramientas)
        │
        ▼
Renderizar: 1 expander con tablas + botones de exportación
            1 gráfico automático (si aplica)
            3 sugerencias contextuales
```

### Tab 2 — Reporte de Insights

```
Clic en "Generar Reporte Ejecutivo"
        │
        ▼
detectar_anomalias()  →  cambios >10% en cualquier par de semanas
detectar_tendencias() →  deterioro en 3+ semanas consecutivas
detectar_benchmarks() →  zonas >20% debajo de sus peers
calcular_correlaciones() → Pearson entre pares (|r|>0.5, p<0.05)
detectar_oportunidades() → High Priority bajo media nacional
        │
        ▼
_resumir_hallazgos()  →  texto compacto de hallazgos para Claude
        │
        ▼
generar_narrativa()   →  Claude genera narrativa ejecutiva en español
        │
        ▼
Renderizar plantilla Jinja2 (report_template.html)
        │
        ▼
Guardar HTML en reports/ + mostrar vista previa + botón descarga
```

---

## 5. Instrucciones para Ejecutar el Proyecto

### Prerrequisitos
- Python 3.10 o superior
- Cuenta en Anthropic con API key activa
- Git (opcional, para clonar)

### Paso 1 — Clonar o descargar el proyecto

```bash
git clone <url-del-repositorio>
cd rappi-ai
```

### Paso 2 — Crear entorno virtual e instalar dependencias

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Paso 3 — Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` y reemplazar el valor:

```
ANTHROPIC_API_KEY=sk-ant-...tu-key-real...
```

### Paso 4 — Verificar que el archivo de datos existe

El archivo `data/data.xlsx` debe contener dos hojas:
- `RAW_INPUT_METRICS` — métricas por zona con columnas `L8W_ROLL` a `L0W_ROLL`
- `RAW_ORDERS` — órdenes por zona con columnas `L8W` a `L0W`

### Paso 5 — Ejecutar la aplicación

```bash
streamlit run app.py
```

La aplicación abrirá automáticamente en `http://localhost:8501`.

### Paso 6 — Uso básico

**Asistente de Datos:**
- Escribe preguntas en lenguaje natural en el chat (ej: *"Top 5 zonas con mayor Lead Penetration en Colombia"*)
- Usa los filtros del sidebar para acotar país, tipo de zona y priorización
- Los resultados incluyen tabla de datos con exportación CSV/HTML y gráfico automático

**Reporte de Insights:**
- Haz clic en "⚡ Generar Reporte Ejecutivo"
- Espera el análisis completo (~30-90 segundos según datos)
- Descarga el reporte HTML o visualízalo directamente en la app

---

## 6. Estructura del Proyecto

```
rappi-ai/
│
├── app.py                      # Aplicación principal Streamlit (2 tabs)
│                               # Contiene: chatbot, renderizado, exportación
│
├── data/
│   └── data.xlsx               # Datos operacionales (Excel, 2 hojas)
│
├── tools/
│   ├── __init__.py
│   ├── data_loader.py          # Lectura y caché del Excel (lru_cache)
│   ├── query_tools.py          # 6 herramientas de consulta + definiciones API
│   └── insights_engine.py     # Motor de análisis automático + render HTML
│
├── prompts/
│   └── system_prompt.py       # Prompt del sistema con diccionario de métricas
│
├── templates/
│   └── report_template.html   # Plantilla Jinja2 del reporte ejecutivo
│
├── reports/                    # Reportes HTML generados (auto-creado)
│
├── docs/                       # Documentación técnica y diagramas
│   ├── documentacion_tecnica.md
│   ├── diagrama_arquitectura.graphml
│   └── diagrama_flujo.graphml
│
├── .streamlit/
│   └── config.toml            # Configuración de UI de Streamlit
│
├── .env                        # Variables de entorno (no incluir en Git)
├── .env.example                # Plantilla de variables de entorno
├── requirements.txt            # Dependencias Python
└── README.md                   # Documentación rápida del proyecto
```

---

## 7. Limitaciones Actuales del Sistema

| Limitación | Impacto | Severidad |
|-----------|---------|-----------|
| **Datos estáticos en Excel** | Requiere actualización manual del archivo cada semana | Alta |
| **Sin autenticación de usuarios** | Cualquier persona con acceso a la URL puede usar la app y la API key | Alta |
| **Sin persistencia de sesión** | El historial del chat se pierde al recargar la página | Media |
| **Coste por token no controlado** | Consultas complejas consumen muchos tokens; no hay presupuesto o límite por usuario | Media |
| **Limite de 400 anomalías** | El motor trunca resultados para evitar lentitud; pueden perderse casos relevantes | Media |
| **Sin validación de calidad de datos** | Si el Excel tiene columnas vacías o errores de formato, los análisis pueden ser incorrectos | Media |
| **Modelo de IA fijo** | Siempre usa `claude-sonnet-4-5`; sin fallback ni comparación de modelos | Baja |
| **Sin tests automáticos** | No hay suite de pruebas; cambios en el código no se validan automáticamente | Baja |
| **Gráficos simples** | Solo líneas y barras horizontales; no hay mapas, heatmaps ni visualizaciones avanzadas | Baja |

---

## 8. Mejoras Futuras Planificadas

Ordenadas por prioridad e impacto:

### Alta prioridad
1. **Integración con base de datos en tiempo real** — Reemplazar el Excel por una conexión a BigQuery, Snowflake o PostgreSQL para que los datos se actualicen automáticamente sin intervención manual.
2. **Autenticación de usuarios** — Implementar login con OAuth (Google, Rappi SSO) para controlar el acceso y asociar costes de API por usuario.

### Prioridad media
3. **Caché de respuestas frecuentes** — Guardar respuestas a preguntas comunes para reducir llamadas a la API y mejorar el tiempo de respuesta.
4. **Alertas automáticas** — Enviar notificaciones por email o Slack cuando el motor detecte anomalías críticas o zonas en deterioro sostenido.
5. **Persistencia de sesión** — Guardar el historial del chat en base de datos para que el usuario pueda retomarlo en una sesión nueva.
6. **Tests unitarios e integración** — Implementar suite de pruebas con `pytest` para validar las herramientas de consulta y el motor de análisis.

### Prioridad baja
7. **Exportación PDF nativa** — Usar WeasyPrint o Puppeteer para generar PDF directamente sin requerir el navegador.
8. **Dashboard histórico extendido** — Permitir análisis de más de 8 semanas y comparativas entre períodos (MoM, YoY).
9. **Soporte multi-idioma** — Generar narrativas del reporte en inglés y portugués además de español.
10. **Visualizaciones avanzadas** — Agregar mapas de calor geográficos y gráficos de dispersión para correlaciones.

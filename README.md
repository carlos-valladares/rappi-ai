# 🛵 Rappi AI — Sistema de Análisis Inteligente de Operaciones

Aplicación web interactiva que permite consultar métricas operacionales de Rappi en **lenguaje natural**, sin necesidad de SQL ni conocimientos técnicos. Dos módulos: un chatbot conversacional impulsado por Claude y un motor de análisis automático que genera reportes ejecutivos HTML.

---

## Tecnologías

| Tecnología | Rol |
|---|---|
| **Python 3.10+** | Lenguaje base |
| **Streamlit 1.40+** | Framework de la aplicación web |
| **Anthropic SDK 0.40+** | Acceso a Claude con tool use y streaming |
| **Claude `claude-sonnet-4-5`** | Motor de IA (razonamiento + narrativa) |
| **Pandas 2.0+** | Manipulación de DataFrames |
| **Plotly 5.18+** | Gráficos interactivos |
| **Jinja2 3.1+** | Renderizado de plantilla HTML del reporte |
| **SciPy 1.11+** | Correlaciones de Pearson con significancia estadística |
| **OpenPyXL 3.1+** | Lectura del Excel con múltiples hojas |
| **python-dotenv 1.0+** | Gestión segura de la API key |

---

## Configuración rápida

### 1. Clonar el repositorio
```bash
git clone https://github.com/carlos-valladares/rappi-ai.git
cd rappi-ai
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Obtener tu API key de Anthropic (2 minutos)
1. Crea una cuenta gratuita en https://console.anthropic.com
2. Ve a **API Keys** → **Create Key** y copia tu key
3. Ve a **Plans & Billing** → agrega mínimo **$5 USD** de créditos

### 4. Configurar la API key
Crea un archivo `.env` en la raíz del proyecto:

```
ANTHROPIC_API_KEY=sk-ant-tu-api-key-aqui
```

O copia el archivo de ejemplo:
```bash
cp .env.example .env
# Edita .env y reemplaza el valor de ANTHROPIC_API_KEY
```

### 5. Ejecutar
```bash
streamlit run app.py
```
Abre http://localhost:8501 en tu navegador.

---

## Costo estimado de uso
| Acción | Costo aproximado |
|---|---|
| Pregunta simple al chatbot | ~$0.01 USD |
| Pregunta compleja con análisis | ~$0.03 USD |
| Generación de reporte de insights | ~$0.10 USD |
| Sesión completa de 10 preguntas | ~$0.20 USD |

> Con $5 USD de créditos tienes suficiente para pruebas extensas (~25 reportes o ~500 preguntas).

---

## Estructura del proyecto

```
rappi-ai/
├── app.py                         # Aplicación principal Streamlit (2 tabs)
├── data/
│   └── data.xlsx                  # Datos operacionales (RAW_INPUT_METRICS + RAW_ORDERS)
├── tools/
│   ├── __init__.py
│   ├── data_loader.py             # Cargador de datos con caché (lru_cache)
│   ├── query_tools.py             # 6 herramientas de consulta + definiciones para Anthropic
│   └── insights_engine.py        # Motor de análisis automático + generación HTML
├── prompts/
│   └── system_prompt.py          # Prompt del sistema con contexto de negocio Rappi
├── templates/
│   └── report_template.html      # Plantilla Jinja2 para el reporte ejecutivo
├── reports/                       # Reportes HTML generados (creado automáticamente)
├── docs/
│   ├── documentacion_tecnica.md  # Documentación técnica completa
│   ├── diagrama_arquitectura.graphml
│   └── diagrama_flujo.graphml
├── .env                           # Variables de entorno (ANTHROPIC_API_KEY)
└── requirements.txt
```

---

## Funcionalidades

### Tab 1 — 💬 Asistente de Datos
- Responde preguntas en lenguaje natural sobre métricas operacionales
- Claude usa 6 herramientas especializadas (tool use) en bucle agéntico
- Respuesta en streaming progresivo con tablas interactivas y gráficos automáticos
- Exportación de resultados a CSV y HTML/PDF
- Sidebar con filtros de país, tipo de zona y priorización
- Sugerencias contextuales de preguntas de seguimiento

### Tab 2 — 📊 Reporte de Insights
- Detección de anomalías (cambios >10% entre semanas)
- Tendencias preocupantes (deterioro en 3+ semanas consecutivas)
- Benchmarking entre peers del mismo país/tipo de zona (brecha >20%)
- Correlaciones Pearson entre métricas (|r|>0.5, p<0.05)
- Oportunidades en zonas High Priority bajo la media nacional
- Narrativa ejecutiva generada por Claude
- Reporte HTML descargable con filtros interactivos

---

## Datos
- **9 países:** AR, BR, CL, CO, CR, EC, MX, PE, UY
- **13 métricas:** Lead Penetration, Perfect Orders, Gross Profit UE, Pro Adoption, Turbo Adoption, y más
- **9 semanas:** L8W (hace 8 semanas) → L0W (semana actual)

---

## Funciones principales por módulo

### `tools/data_loader.py`
| Función | Descripción |
|---|---|
| `obtener_df_metricas()` | DataFrame de métricas con caché (hoja RAW_INPUT_METRICS) |
| `obtener_df_ordenes()` | DataFrame de órdenes con caché (hoja RAW_ORDERS) |
| `obtener_columna_semana(etiqueta, dataset)` | Convierte `'L0W'` → `'L0W_ROLL'` o `'L0W'` según dataset |
| `recargar_datos()` | Limpia caché y recarga desde disco |

### `tools/query_tools.py`
| Función Python | Herramienta Claude | Descripción |
|---|---|---|
| `filtrar_zonas()` | `filter_zones` | Top/bottom N zonas por métrica y semana |
| `comparar_metricas()` | `compare_metrics` | Estadísticas agrupadas por ZONE_TYPE, COUNTRY, etc. |
| `obtener_tendencia()` | `get_trend` | Serie temporal de una métrica para una zona |
| `agregar_por()` | `aggregate_by` | Media/suma/mediana agrupada por dimensión |
| `analisis_multivariable()` | `multivariable_analysis` | Zonas con métrica A alta y métrica B baja |
| `obtener_tendencia_ordenes()` | `get_orders_trend` | Serie temporal de órdenes para una zona |

### `tools/insights_engine.py`
| Función | Descripción |
|---|---|
| `detectar_anomalias(umbral)` | Cambios >10% en cualquier par de semanas |
| `detectar_tendencias_preocupantes(min_semanas)` | Deterioro en 3+ semanas consecutivas |
| `detectar_brechas_benchmark(umbral)` | Zonas >20% debajo de sus peers |
| `calcular_correlaciones()` | Pearson entre pares de métricas (p<0.05) |
| `detectar_oportunidades()` | Zonas High Priority bajo media nacional |
| `generar_narrativa(hallazgos, cliente)` | Narrativa ejecutiva con Claude |
| `generar_reporte_html(cliente, callback)` | Pipeline completo → HTML en `/reports` |

### `app.py`
| Función | Descripción |
|---|---|
| `inicializar_sesion()` | Inicializa variables de estado de Streamlit |
| `obtener_cliente()` | Singleton cacheado del cliente Anthropic |
| `chatear_con_claude(mensaje, filtros)` | Bucle agéntico completo con tool use y streaming |
| `renderizar_tabla_con_exportacion(datos, titulo, key)` | Tabla formateada con botones CSV/HTML-PDF |
| `graficar_tendencia(df, titulo)` | Gráfico de líneas para datos temporales (px.line) |
| `graficar_comparacion(df, titulo)` | Gráfico de barras horizontales comparativo (px.bar) |
| `renderizar_grafico(df, titulo)` | Dispatcher: elige tendencia o comparación automáticamente |
| `renderizar_tab_chatbot()` | Tab 1: interfaz completa del chatbot |
| `renderizar_tab_insights()` | Tab 2: generación del reporte ejecutivo |

---

## Limitaciones actuales

| Limitación | Severidad |
|---|---|
| Datos estáticos en Excel — requiere actualización manual semanal | Alta |
| Sin autenticación de usuarios — cualquier persona con la URL puede acceder | Alta |
| Sin persistencia de sesión — el historial se pierde al recargar | Media |
| Sin control de coste por usuario — consultas complejas consumen muchos tokens | Media |
| Análisis truncado a 400 anomalías para evitar lentitud | Media |
| Sin validación de calidad de datos del Excel | Media |
| Sin suite de tests automáticos | Baja |
| Gráficos simples (solo líneas y barras) | Baja |

---

## Mejoras futuras

**Alta prioridad**
1. Integración con base de datos en tiempo real (BigQuery / Snowflake / PostgreSQL)
2. Autenticación con OAuth (Google / Rappi SSO) y control de acceso por usuario

**Prioridad media**
3. Caché de respuestas frecuentes para reducir llamadas a la API
4. Alertas automáticas por email/Slack ante anomalías críticas
5. Persistencia de sesión del chat en base de datos
6. Suite de tests con `pytest` para herramientas y motor de análisis

**Prioridad baja**
7. Exportación PDF nativa (WeasyPrint / Puppeteer)
8. Análisis histórico extendido más allá de 8 semanas
9. Soporte multi-idioma (inglés y portugués)
10. Visualizaciones avanzadas: mapas de calor geográficos, gráficos de dispersión

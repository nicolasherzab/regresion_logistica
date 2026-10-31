"""
Frontend UI/UX Application - Plataforma Analítica de Regresión Logística & Business Intelligence
Construido en Streamlit consumiendo exclusivamente el contrato de `backend_engine.py`.
Soporte completo para Modo Claro / Modo Oscuro, Diseño Responsive y Flujo Guiado de 5 Fases.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from backend_engine import (
    SECTORES_ECONOMICOS,
    analyze_nulls,
    evaluate_with_threshold,
    generate_business_recommendations,
    generate_sample_dataset,
    generate_simulation_scenarios,
    get_dataframe_head,
    handle_nulls,
    identify_variable_types,
    load_dataset,
    train_logistic_model,
    validate_and_prepare_features,
)

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y GESTIÓN DE ESTADO
# ==============================================================================
st.set_page_config(
    page_title="LogitBI | Plataforma de Regresión Logística & Decisiones",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state() -> None:
    """Inicializa las variables de estado de la sesión para mantener fluidez entre las 5 fases."""
    defaults = {
        "theme_mode": "auto",  # 'auto', 'light', 'dark'
        "selected_sector": SECTORES_ECONOMICOS[0] if SECTORES_ECONOMICOS else "Financiero / Banca",
        "raw_df": None,
        "clean_df": None,
        "dataset_name": None,
        "null_report_info": None,
        "prep_metadata": None,
        "X_prepared": None,
        "y_prepared": None,
        "target_col": None,
        "feature_cols": [],
        "dummy_cols": [],
        "model_bundle": None,
        "threshold": 0.50,
        "slider_f3_thresh": 0.50,
        "slider_f4_sync": 0.50,
        "scenarios_df": None,
        "custom_scenarios_input": None,
        "custom_scenarios_df": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()


def _on_change_f3_thresh() -> None:
    """Sincroniza el umbral cuando cambia el slider de la Fase 3."""
    val = float(st.session_state["slider_f3_thresh"])
    st.session_state["threshold"] = val
    st.session_state["slider_f4_sync"] = val
    if st.session_state.get("model_bundle") is not None:
        st.session_state["scenarios_df"] = generate_simulation_scenarios(
            st.session_state["model_bundle"],
            n_scenarios=10,
            custom_scenarios_df=st.session_state.get("custom_scenarios_input"),
            threshold=val,
        )


def _on_change_f4_thresh() -> None:
    """Sincroniza el umbral cuando cambia el slider de la Fase 4."""
    val = float(st.session_state["slider_f4_sync"])
    st.session_state["threshold"] = val
    st.session_state["slider_f3_thresh"] = val
    if st.session_state.get("model_bundle") is not None:
        st.session_state["scenarios_df"] = generate_simulation_scenarios(
            st.session_state["model_bundle"],
            n_scenarios=10,
            custom_scenarios_df=st.session_state.get("custom_scenarios_input"),
            threshold=val,
        )


# ==============================================================================
# 2. SISTEMA DE ESTILOS CSS (RESPONSIVE + LIGHT/DARK MODE ADAPTIVO)
# ==============================================================================
def inject_custom_css(theme_mode: str = "auto") -> None:
    """
    Inyecta variables CSS semánticas con soporte adaptativo para Modo Claro y Modo Oscuro
    (tanto automático vía prefers-color-scheme / variables de Streamlit como manual).
    """
    theme_override_css = ""
    if theme_mode == "light":
        theme_override_css = """
        :root {
            --ui-bg-surface: rgba(255, 255, 255, 0.92);
            --ui-bg-elevated: rgba(248, 250, 252, 0.96);
            --ui-text-primary: #0f172a;
            --ui-text-secondary: #475569;
            --ui-border: rgba(15, 23, 42, 0.12);
            --ui-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.06);
        }
        """
    elif theme_mode == "dark":
        theme_override_css = """
        :root {
            --ui-bg-surface: rgba(30, 41, 59, 0.75);
            --ui-bg-elevated: rgba(15, 23, 42, 0.85);
            --ui-text-primary: #f8fafc;
            --ui-text-secondary: #94a3b8;
            --ui-border: rgba(248, 250, 252, 0.14);
            --ui-shadow: 0 4px 24px -2px rgba(0, 0, 0, 0.35);
        }
        """

    st.markdown(
        f"""
        <style>
        :root {{
            --ui-primary: #2563eb;
            --ui-primary-soft: rgba(37, 99, 235, 0.12);
            --ui-accent: #0ea5e9;
            --ui-success: #10b981;
            --ui-success-soft: rgba(16, 185, 129, 0.14);
            --ui-warning: #f59e0b;
            --ui-warning-soft: rgba(245, 158, 11, 0.15);
            --ui-danger: #ef4444;
            --ui-danger-soft: rgba(239, 68, 68, 0.15);
            --ui-bg-surface: rgba(128, 128, 128, 0.06);
            --ui-bg-elevated: rgba(128, 128, 128, 0.10);
            --ui-border: rgba(128, 128, 128, 0.22);
            --ui-radius-lg: 14px;
            --ui-radius-md: 10px;
            --ui-radius-sm: 6px;
            --ui-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --ui-primary: #3b82f6;
                --ui-primary-soft: rgba(59, 130, 246, 0.18);
                --ui-bg-surface: rgba(30, 41, 59, 0.55);
                --ui-bg-elevated: rgba(30, 41, 59, 0.80);
                --ui-border: rgba(148, 163, 184, 0.22);
            }}
        }}

        {theme_override_css}

        /* Encabezado Principal Hero */
        .hero-banner {{
            background: linear-gradient(135deg, rgba(37, 99, 235, 0.14) 0%, rgba(14, 165, 233, 0.08) 100%);
            border: 1px solid var(--ui-border);
            border-left: 5px solid var(--ui-primary);
            border-radius: var(--ui-radius-lg);
            padding: 1.35rem 1.6rem;
            margin-bottom: 1.5rem;
            box-shadow: var(--ui-shadow);
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }}
        .hero-title {{
            font-size: clamp(1.35rem, 2.2vw, 1.85rem);
            font-weight: 800;
            margin: 0 0 0.25rem 0;
            letter-spacing: -0.02em;
        }}
        .hero-subtitle {{
            font-size: 0.95rem;
            opacity: 0.85;
            margin: 0;
        }}

        /* Tarjetas KPI y Contenedores Semánticos */
        .ui-card {{
            background: var(--ui-bg-surface);
            border: 1px solid var(--ui-border);
            border-radius: var(--ui-radius-md);
            padding: 1.15rem 1.25rem;
            margin-bottom: 1rem;
            box-shadow: var(--ui-shadow);
            transition: transform 0.15s ease, border-color 0.15s ease;
        }}
        .ui-card:hover {{
            border-color: var(--ui-primary);
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
            gap: 0.9rem;
            margin-bottom: 1.2rem;
        }}
        .kpi-box {{
            background: var(--ui-bg-surface);
            border: 1px solid var(--ui-border);
            border-radius: var(--ui-radius-md);
            padding: 1rem 1.15rem;
            box-shadow: var(--ui-shadow);
        }}
        .kpi-label {{
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            opacity: 0.75;
            font-weight: 600;
            margin-bottom: 0.35rem;
        }}
        .kpi-value {{
            font-size: 1.55rem;
            font-weight: 800;
            line-height: 1.2;
        }}
        .kpi-sub {{
            font-size: 0.78rem;
            opacity: 0.75;
            margin-top: 0.25rem;
        }}

        /* Badges & Etiquetas */
        .ui-badge {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.25rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            border: 1px solid var(--ui-border);
            background: var(--ui-bg-elevated);
            margin: 0.18rem;
        }}
        .badge-continuous {{
            background: rgba(37, 99, 235, 0.13);
            border-color: rgba(37, 99, 235, 0.35);
            color: #3b82f6;
        }}
        .badge-categorical {{
            background: rgba(16, 185, 129, 0.13);
            border-color: rgba(16, 185, 129, 0.35);
            color: #10b981;
        }}
        .badge-binary {{
            background: rgba(245, 158, 11, 0.15);
            border-color: rgba(245, 158, 11, 0.4);
            color: #f59e0b;
        }}

        /* Matriz de Confusión Visual 2x2 */
        .cm-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.85rem;
            margin: 0.75rem 0;
        }}
        .cm-cell {{
            border-radius: var(--ui-radius-md);
            padding: 1.1rem;
            text-align: center;
            border: 1px solid var(--ui-border);
        }}
        .cm-tp {{
            background: rgba(16, 185, 129, 0.16);
            border-color: rgba(16, 185, 129, 0.45);
        }}
        .cm-tn {{
            background: rgba(37, 99, 235, 0.15);
            border-color: rgba(37, 99, 235, 0.42);
        }}
        .cm-fp {{
            background: rgba(245, 158, 11, 0.16);
            border-color: rgba(245, 158, 11, 0.45);
        }}
        .cm-fn {{
            background: rgba(239, 68, 68, 0.16);
            border-color: rgba(239, 68, 68, 0.45);
        }}
        .cm-count {{
            font-size: 1.8rem;
            font-weight: 800;
            margin: 0.2rem 0;
        }}
        .cm-title {{
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}
        .cm-desc {{
            font-size: 0.76rem;
            opacity: 0.8;
        }}

        /* Stepper Progreso en Sidebar */
        .phase-step {{
            display: flex;
            align-items: center;
            gap: 0.65rem;
            padding: 0.5rem 0.75rem;
            border-radius: var(--ui-radius-sm);
            margin-bottom: 0.35rem;
            font-size: 0.85rem;
            border: 1px solid transparent;
        }}
        .phase-done {{
            background: var(--ui-success-soft);
            border-color: rgba(16, 185, 129, 0.3);
            font-weight: 600;
        }}
        .phase-pending {{
            background: var(--ui-bg-surface);
            border-color: var(--ui-border);
            opacity: 0.75;
        }}

        /* Adaptabilidad Móvil / Tablet */
        @media (max-width: 768px) {{
            .hero-banner {{
                padding: 1rem;
            }}
            .cm-grid {{
                grid-template-columns: 1fr;
            }}
            .kpi-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ==============================================================================
# 3. FUNCIONES AUXILIARES DE VISUALIZACIÓN (CHARTS & COMPONENTES)
# ==============================================================================
def render_Variable_badges(columns: list[str], badge_class: str, icon: str) -> None:
    """Renderiza una colección de píldoras/badges HTML accesibles para listas de variables."""
    if not columns:
        st.caption("No se detectaron variables en esta categoría.")
        return
    badges_html = "".join(
        [f'<span class="ui-badge {badge_class}">{icon} {col}</span>' for col in columns]
    )
    st.markdown(f'<div style="line-height: 2.0;">{badges_html}</div>', unsafe_allow_html=True)


def render_confusion_matrix_cards(eval_res: dict) -> None:
    """Renderiza la Matriz de Confusión como tarjetas 2x2 estilizadas con porcentajes y semántica."""
    tn = int(eval_res.get("tn", 0))
    fp = int(eval_res.get("fp", 0))
    fn = int(eval_res.get("fn", 0))
    tp = int(eval_res.get("tp", 0))
    total = max(tn + fp + fn + tp, 1)

    st.markdown(
        f"""
        <div class="cm-grid" role="region" aria-label="Matriz de Confusión 2x2">
            <div class="cm-cell cm-tn">
                <div class="cm-title">Verdaderos Negativos (TN)</div>
                <div class="cm-count">{tn}</div>
                <div class="cm-desc">{(tn / total) * 100:.1f}% del total | Real: 0 → Pred: 0</div>
            </div>
            <div class="cm-cell cm-fp">
                <div class="cm-title">Falsos Positivos (FP - Alarma)</div>
                <div class="cm-count">{fp}</div>
                <div class="cm-desc">{(fp / total) * 100:.1f}% del total | Real: 0 → Pred: 1</div>
            </div>
            <div class="cm-cell cm-fn">
                <div class="cm-title">Falsos Negativos (FN - Fuga)</div>
                <div class="cm-count">{fn}</div>
                <div class="cm-desc">{(fn / total) * 100:.1f}% del total | Real: 1 → Pred: 0</div>
            </div>
            <div class="cm-cell cm-tp">
                <div class="cm-title">Verdaderos Positivos (TP)</div>
                <div class="cm-count">{tp}</div>
                <div class="cm-desc">{(tp / total) * 100:.1f}% del total | Real: 1 → Pred: 1</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==============================================================================
# 4. BARRA LATERAL (SIDEBAR): CONFIGURACIÓN GLOBAL, CARGA Y ESTADO DE FASES
# ==============================================================================
with st.sidebar:
    st.markdown("## ⚙️ Panel de Control")

    # Selector de Apariencia (Modo Claro / Oscuro / Automático)
    theme_choice = st.segmented_control(
        "Apariencia Visual",
        options=["auto", "light", "dark"],
        format_func=lambda x: {"auto": "🌗 Auto", "light": "☀️ Claro", "dark": "🌙 Oscuro"}[x],
        default=st.session_state["theme_mode"],
        help="Adapta las superficies y contrastes para modo claro u oscuro.",
    )
    if theme_choice and theme_choice != st.session_state["theme_mode"]:
        st.session_state["theme_mode"] = theme_choice

    inject_custom_css(st.session_state["theme_mode"])

    st.divider()

    # 1. Selector de Sector Económico
    st.markdown("### 🏢 1. Contexto de Negocio")
    selected_sector = st.selectbox(
        "Sector Económico:",
        options=SECTORES_ECONOMICOS,
        index=SECTORES_ECONOMICOS.index(st.session_state["selected_sector"])
        if st.session_state["selected_sector"] in SECTORES_ECONOMICOS
        else 0,
        help="Define el contexto empresarial para los datasets sintéticos y las recomendaciones del Analista de Negocios.",
    )
    st.session_state["selected_sector"] = selected_sector

    # 2. Fuente de Datos (Uploader + Generador Sintético)
    st.markdown("### 📂 2. Ingesta de Datos")
    uploaded_file = st.file_uploader(
        "Cargar archivo (.csv, .xlsx, .xls, .pdf)",
        type=["csv", "xlsx", "xls", "pdf"],
        help="Sube tu base de datos tabular o tablas en PDF para iniciar el flujo.",
    )

    if uploaded_file is not None:
        file_id = f"{uploaded_file.name}_{uploaded_file.size}"
        if st.session_state.get("dataset_name") != file_id:
            with st.spinner(f"Procesando archivo {uploaded_file.name}..."):
                df_loaded, err_msg = load_dataset(uploaded_file, uploaded_file.name)
                if err_msg or df_loaded is None:
                    st.error(f"Error al cargar archivo: {err_msg}")
                else:
                    st.session_state["raw_df"] = df_loaded
                    st.session_state["clean_df"] = df_loaded.copy()
                    st.session_state["dataset_name"] = file_id
                    st.session_state["null_report_info"] = None
                    st.session_state["X_prepared"] = None
                    st.session_state["y_prepared"] = None
                    st.session_state["prep_metadata"] = None
                    st.session_state["model_bundle"] = None
                    st.session_state["scenarios_df"] = None
                    st.session_state["custom_scenarios_input"] = None
                    st.session_state["custom_scenarios_df"] = None
                    st.toast(f"✅ Archivo '{uploaded_file.name}' cargado con éxito.")

    st.caption("¿Deseas realizar una prueba rápida guiada?")
    if st.button(
        f"✨ Cargar Dataset de Ejemplo ({selected_sector})",
        use_container_width=True,
        type="primary" if st.session_state["raw_df"] is None else "secondary",
    ):
        with st.spinner(f"Generando dataset para {selected_sector}..."):
            sample_df = generate_sample_dataset(selected_sector)
            st.session_state["raw_df"] = sample_df
            st.session_state["clean_df"] = sample_df.copy()
            st.session_state["dataset_name"] = f"Dataset Sintético ({selected_sector})"
            st.session_state["null_report_info"] = None
            st.session_state["X_prepared"] = None
            st.session_state["y_prepared"] = None
            st.session_state["prep_metadata"] = None
            st.session_state["model_bundle"] = None
            st.session_state["scenarios_df"] = None
            st.session_state["custom_scenarios_input"] = None
            st.session_state["custom_scenarios_df"] = None
            st.rerun()

    st.divider()

    # 3. Indicador Visual del Progreso de las 5 Fases
    st.markdown("### 🧭 Progreso del Flujo (5 Fases)")
    p1_ok = st.session_state["raw_df"] is not None
    p2_ok = st.session_state["X_prepared"] is not None and st.session_state["y_prepared"] is not None
    p3_ok = st.session_state["model_bundle"] is not None
    p4_ok = p3_ok and st.session_state["scenarios_df"] is not None
    p5_ok = p3_ok

    phases_status = [
        ("Fase 1: Ingesta y Exploración", p1_ok),
        ("Fase 2: Preprocesamiento & Dummies", p2_ok),
        ("Fase 3: Modelado Logístico (70/30)", p3_ok),
        ("Fase 4: Evaluación & 10+ Escenarios", p4_ok),
        ("Fase 5: Valor de Negocio (BI)", p5_ok),
    ]
    completed_count = sum(1 for _, ok in phases_status if ok)
    st.progress(completed_count / 5.0, text=f"{completed_count} de 5 fases activas")

    for label, is_done in phases_status:
        icon = "✅" if is_done else "⏳"
        cls = "phase-done" if is_done else "phase-pending"
        st.markdown(
            f'<div class="phase-step {cls}"><span>{icon}</span><span>{label}</span></div>',
            unsafe_allow_html=True,
        )


# ==============================================================================
# 5. ENCABEZADO PRINCIPAL (HERO BANNER)
# ==============================================================================
st.markdown(
    f"""
    <div class="hero-banner" role="banner">
        <div>
            <h1 class="hero-title">📊 Plataforma de Regresión Logística & Simulación Estratégica</h1>
            <p class="hero-subtitle">
                Flujo integral extremo a extremo: desde la ingesta y codificación Dummy hasta simulación de escenarios y estrategia ejecutiva.
            </p>
        </div>
        <div>
            <span class="ui-badge badge-continuous">🏢 Sector: {st.session_state["selected_sector"]}</span>
            <span class="ui-badge badge-categorical">🎯 Umbral Activo: {st.session_state["threshold"]:.2f}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Estado vacío si aún no hay dataset cargado
if st.session_state["raw_df"] is None:
    st.markdown(
        """
        <div class="ui-card" style="text-align: center; padding: 2.5rem 1.5rem;">
            <h2 style="margin-top: 0;">👋 ¡Bienvenido al Sistema Analítico Predictivo!</h2>
            <p style="max-width: 680px; margin: 0.5rem auto 1.5rem auto; opacity: 0.85;">
                Para comenzar las <strong>5 Fases Operativas</strong>, selecciona tu <strong>Sector Económico</strong> en la barra lateral izquierda y sube un archivo (<code>.csv</code>, <code>.xlsx</code>, <code>.pdf</code>) o genera un dataset sectorial de prueba con un solo clic.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_cta1, col_cta2, col_cta3 = st.columns([1, 2, 1])
    with col_cta2:
        if st.button(
            f"🚀 Iniciar Ahora con Dataset de {st.session_state['selected_sector']}",
            type="primary",
            use_container_width=True,
        ):
            sample_df = generate_sample_dataset(st.session_state["selected_sector"])
            st.session_state["raw_df"] = sample_df
            st.session_state["clean_df"] = sample_df.copy()
            st.session_state["dataset_name"] = f"Dataset Sintético ({st.session_state['selected_sector']})"
            st.session_state["null_report_info"] = None
            st.session_state["X_prepared"] = None
            st.session_state["y_prepared"] = None
            st.session_state["prep_metadata"] = None
            st.session_state["model_bundle"] = None
            st.session_state["scenarios_df"] = None
            st.session_state["custom_scenarios_input"] = None
            st.session_state["custom_scenarios_df"] = None
            st.rerun()
    st.stop()


# ==============================================================================
# NAVEGACIÓN PRINCIPAL POR LAS 5 FASES
# ==============================================================================
active_df: pd.DataFrame = st.session_state["clean_df"]
nulls_df_summary = analyze_nulls(active_df)
total_nulls_count = int(nulls_df_summary["Nulos"].sum()) if not nulls_df_summary.empty else 0

tab_f1, tab_f2, tab_f3, tab_f4, tab_f5 = st.tabs(
    [
        "📥 Fase 1: Ingesta y Configuración",
        "🧹 Fase 2: Preprocesamiento & Dummies",
        "⚙️ Fase 3: Modelado Machine Learning",
        "🎯 Fase 4: Evaluación y Simulación (10+)",
        "💼 Fase 5: Valor de Negocio (BI)",
    ]
)


# ==============================================================================
# FASE 1: INGESTA Y CONFIGURACIÓN
# ==============================================================================
with tab_f1:
    st.subheader("📥 Fase 1: Ingesta, Contexto Sectorial y Vista Previa")
    st.write(
        "Inspección inicial de la estructura de datos cargada, verificación de dimensiones y validación obligatoria de los primeros registros."
    )

    # Tarjetas KPI rápidas del Dataset
    st.markdown(
        f"""
        <div class="kpi-grid" role="region" aria-label="Métricas del Dataset">
            <div class="kpi-box">
                <div class="kpi-label">Fuente de Datos</div>
                <div class="kpi-value" style="font-size: 1.05rem;">{st.session_state["dataset_name"]}</div>
                <div class="kpi-sub">Archivo activo en memoria</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Sector Económico</div>
                <div class="kpi-value" style="font-size: 1.15rem;">{st.session_state["selected_sector"]}</div>
                <div class="kpi-sub">Contexto analítico aplicado</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Total Registros (Filas)</div>
                <div class="kpi-value">{active_df.shape[0]:,}</div>
                <div class="kpi-sub">Observaciones disponibles</div>
            </div>
            <div class="kpi-box">
                <div class="kpi-label">Total Variables (Columnas)</div>
                <div class="kpi-value">{active_df.shape[1]}</div>
                <div class="kpi-sub">Celdas nulas actuales: {total_nulls_count}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Requisito obligatorio: Mostrar de forma destacada las 2 primeras filas del dataset
    st.markdown(
        """
        <div class="ui-card">
            <h4 style="margin-top: 0; margin-bottom: 0.35rem;">🔎 Muestra Obligatoria: Primeras 2 Filas del Dataset (<code>head(2)</code>)</h4>
            <p style="font-size: 0.88rem; opacity: 0.8; margin-bottom: 0.5rem;">
                Verificación inmediata del esquema de columnas y formato de valores de entrada mediante <code>get_dataframe_head(df, 2)</code>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    head_2_df = get_dataframe_head(active_df, 2)
    st.dataframe(head_2_df, use_container_width=True)

    # Opción de expandir para ver más filas o resumen estadístico
    with st.expander("📖 Expandir para explorar más filas del dataset y resumen estadístico"):
        n_preview = st.slider(
            "Cantidad de filas a visualizar:",
            min_value=5,
            max_value=min(100, len(active_df)),
            value=min(10, len(active_df)),
            step=5,
        )
        st.dataframe(get_dataframe_head(active_df, n_preview), use_container_width=True)
        st.markdown("##### 📊 Resumen Estadístico Descriptivo")
        st.dataframe(active_df.describe(include="all").T, use_container_width=True)


# ==============================================================================
# FASE 2: PREPROCESAMIENTO Y CODIFICACIÓN DUMMY
# ==============================================================================
with tab_f2:
    st.subheader("🧹 Fase 2: Diagnóstico de Nulos, Tipología de Variables y Codificación Dummy")

    # --- Bloque 2.1: Análisis y Tratamiento de Nulos ---
    st.markdown("#### 1️⃣ Diagnóstico y Tratamiento de Valores Faltantes (Nulos)")
    col_null_table, col_null_action = st.columns([1.4, 1], gap="large")

    with col_null_table:
        st.dataframe(
            nulls_df_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Porcentaje_Nulos": st.column_config.ProgressColumn(
                    "% Nulos",
                    help="Porcentaje de valores faltantes en la columna",
                    format="%.2f%%",
                    min_value=0,
                    max_value=100,
                )
            },
        )

    with col_null_action:
        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        st.markdown("##### 🛠️ Estrategia de Limpieza de Nulos")
        strategy_labels = {
            "impute_median_mode": "Imputar Mediana (Numéricas) y Moda (Categóricas) [Recomendado]",
            "impute_mean_mode": "Imputar Media (Numéricas) y Moda (Categóricas)",
            "drop_rows": "Eliminar filas con valores nulos (Drop Rows)",
            "zero_or_unknown": "Rellenar con 0 (Numéricas) o 'Desconocido' (Categóricas)",
        }
        selected_strategy = st.selectbox(
            "Selecciona el método de tratamiento:",
            options=list(strategy_labels.keys()),
            format_func=lambda k: strategy_labels[k],
        )

        col_btn_apply, col_btn_reset = st.columns(2)
        with col_btn_apply:
            if st.button("✨ Aplicar Tratamiento", type="primary", use_container_width=True):
                cleaned_df, report_info = handle_nulls(active_df, strategy=selected_strategy)
                st.session_state["clean_df"] = cleaned_df
                st.session_state["null_report_info"] = report_info
                st.session_state["X_prepared"] = None
                st.session_state["y_prepared"] = None
                st.session_state["prep_metadata"] = None
                st.session_state["model_bundle"] = None
                st.session_state["scenarios_df"] = None
                st.session_state["custom_scenarios_input"] = None
                st.session_state["custom_scenarios_df"] = None
                st.rerun()
        with col_btn_reset:
            if st.button("↩️ Restaurar Original", use_container_width=True):
                st.session_state["clean_df"] = st.session_state["raw_df"].copy()
                st.session_state["null_report_info"] = None
                st.session_state["X_prepared"] = None
                st.session_state["y_prepared"] = None
                st.session_state["prep_metadata"] = None
                st.session_state["model_bundle"] = None
                st.session_state["scenarios_df"] = None
                st.session_state["custom_scenarios_input"] = None
                st.session_state["custom_scenarios_df"] = None
                st.rerun()

        if st.session_state["null_report_info"] is not None:
            rep = st.session_state["null_report_info"]
            strat_used = rep.get("strategy_applied", rep.get("strategy_requested", ""))
            st.success(
                f"Tratamiento aplicado (`{strat_used}`): "
                f"Nulos antes: **{rep.get('nulls_before', 0)}** → Nulos después: **{rep.get('nulls_after', 0)}** "
                f"(Filas: {rep.get('rows_after', len(active_df))})."
            )
        elif total_nulls_count == 0:
            st.info("✅ El dataset activo no presenta valores nulos pendientes.")
        else:
            st.warning(f"⚠️ Se detectaron **{total_nulls_count}** celdas vacías. Aplica una estrategia o se imputarán automáticamente al preparar el modelo.")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # --- Bloque 2.2: Identificación Automática de Tipos de Variables ---
    st.markdown("#### 2️⃣ Clasificación Automática de Variables del Dataset")
    var_types = identify_variable_types(active_df)
    continuous_cols = var_types.get("continuous", [])
    discrete_cat_cols = var_types.get("discrete_categorical", [])
    binary_candidates = var_types.get("binary_candidates", [])

    col_v_cont, col_v_cat, col_v_bin = st.columns(3, gap="medium")
    with col_v_cont:
        st.markdown(
            f"""
            <div class="ui-card">
                <h5 style="margin:0 0 0.4rem 0;">📈 Variables Continuas ({len(continuous_cols)})</h5>
                <p style="font-size:0.8rem; opacity:0.75; margin-bottom:0.6rem;">Variables numéricas de alta cardinalidad o punto flotante.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_Variable_badges(continuous_cols, "badge-continuous", "🔢")

    with col_v_cat:
        st.markdown(
            f"""
            <div class="ui-card">
                <h5 style="margin:0 0 0.4rem 0;">🏷️ Discretas / Categóricas ({len(discrete_cat_cols)})</h5>
                <p style="font-size:0.8rem; opacity:0.75; margin-bottom:0.6rem;">Candidatas para codificación en Variables Dummy (One-Hot).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_Variable_badges(discrete_cat_cols, "badge-categorical", "🏷️")

    with col_v_bin:
        st.markdown(
            f"""
            <div class="ui-card">
                <h5 style="margin:0 0 0.4rem 0;">🎯 Candidatas Binarias ({len(binary_candidates)})</h5>
                <p style="font-size:0.8rem; opacity:0.75; margin-bottom:0.6rem;">Columnas con exactamente 2 categorías únicas (ideales para Target <i>Y</i>).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_Variable_badges(binary_candidates, "badge-binary", "🎯")

    st.divider()

    # --- Bloque 2.3: Selección de Target, Features y Variables Dummy ---
    st.markdown("#### 3️⃣ Configuración de Variables del Modelo y Codificación Dummy (One-Hot Encoding)")

    all_cols = list(active_df.columns)
    default_target = (
        binary_candidates[-1]
        if binary_candidates
        else (all_cols[-1] if all_cols else None)
    )

    col_sel_target, col_sel_features = st.columns([1, 2], gap="large")
    with col_sel_target:
        target_col = st.selectbox(
            "🎯 Selecciona la Variable Dependiente (Target Binario Y):",
            options=all_cols,
            index=all_cols.index(default_target) if default_target in all_cols else 0,
            help="La Regresión Logística predice la probabilidad de ocurrencia de un evento binario (0 o 1).",
        )
        if target_col not in binary_candidates:
            st.warning(
                f"⚠️ La columna `{target_col}` tiene {active_df[target_col].nunique(dropna=True)} valores únicos. "
                "Para Regresión Logística binaria debe tener exactamente 2 clases."
            )

    available_features = [c for c in all_cols if c != target_col]
    with col_sel_features:
        feature_cols = st.multiselect(
            "🧩 Selecciona las Variables Independientes (Features X):",
            options=available_features,
            default=available_features,
            help="Variables predictoras que entrarán en la ecuación logística.",
        )

    # Pregunta explícita al usuario sobre cuáles variables discretas/categóricas convertir en Dummy
    selected_discrete_in_features = [
        c for c in feature_cols if c in discrete_cat_cols or active_df[c].dtype == "object" or str(active_df[c].dtype) == "category"
    ]
    non_Numeric_forced = [
        c for c in feature_cols if not pd.api.types.is_numeric_dtype(active_df[c])
    ]

    st.markdown(
        """
        <div class="ui-card" style="border-left: 4px solid var(--ui-accent);">
            <h5 style="margin: 0 0 0.3rem 0;">🔀 Pregunta de Diseño: Conversión a Variables Dummy (One-Hot Encoding)</h5>
            <p style="font-size: 0.88rem; opacity: 0.85; margin: 0;">
                Indica explícitamente cuáles de las variables discretas o categóricas seleccionadas deseas transformar en <strong>Variables Dummy (0/1)</strong> eliminando la primera categoría de referencia (<code>drop_first=True</code>) para evitar multicolinealidad.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    dummy_options = [c for c in feature_cols if c in discrete_cat_cols or c in non_Numeric_forced]
    if not dummy_options:
        dummy_options = feature_cols

    dummy_cols = st.multiselect(
        "📌 ¿Cuáles variables discretas/categóricas deseas convertir en Variables Dummy?",
        options=dummy_options,
        default=selected_discrete_in_features,
        help="Las variables de texto se codificarán automáticamente. También puedes incluir variables discretas numéricas.",
    )

    if st.button("✅ Validar y Preparar Matriz de Características (X, y)", type="primary", use_container_width=True):
        X_prep, y_prep, prep_meta, prep_err = validate_and_prepare_features(
            active_df,
            target_col=target_col,
            feature_cols=feature_cols,
            dummy_cols=dummy_cols,
        )
        if prep_err or X_prep is None or y_prep is None:
            st.error(f"❌ Error de validación: {prep_err}")
        else:
            st.session_state["X_prepared"] = X_prep
            st.session_state["y_prepared"] = y_prep
            st.session_state["prep_metadata"] = prep_meta
            st.session_state["target_col"] = target_col
            st.session_state["feature_cols"] = feature_cols
            st.session_state["dummy_cols"] = dummy_cols
            st.toast("✅ Variables preparadas y codificadas correctamente.")

    if st.session_state["X_prepared"] is not None and st.session_state["prep_metadata"] is not None:
        meta = st.session_state["prep_metadata"]
        X_p = st.session_state["X_prepared"]
        st.success(
            f"✅ **Matriz lista para Modelado**: {X_p.shape[0]} registros × {X_p.shape[1]} columnas finales "
            f"(Target: `{meta.get('target_col')}` | Clases: `{meta.get('target_mapping')}`)."
        )
        with st.expander("🔍 Ver vista previa de la matriz X codificada (con Variables Dummy)"):
            st.dataframe(get_dataframe_head(X_p, 5), use_container_width=True)


# ==============================================================================
# FASE 3: MODELADO MACHINE LEARNING (REGRESIÓN LOGÍSTICA 70/30 + ECUACIÓN)
# ==============================================================================
with tab_f3:
    st.subheader("⚙️ Fase 3: Entrenamiento de Regresión Logística, Ecuación Matemática y Pesos")

    # Si el usuario entra directo a Fase 3 sin haber pulsado el botón de Fase 2, preparamos automáticamente con valores por defecto
    if st.session_state["X_prepared"] is None:
        st.info(
            "💡 Aún no has confirmado la matriz en la Fase 2. Puedes entrenarla directamente con la detección automática de variables o personalizarla en la pestaña anterior."
        )

    col_train_cfg, col_thresh_cfg = st.columns([1.2, 1], gap="large")

    with col_train_cfg:
        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        st.markdown("##### 🧪 Configuración de Entrenamiento (Partición 70% / 30%)")
        st.caption(
            "El conjunto de datos se divide estratificadamente en **70% Entrenamiento (Train)** y **30% Prueba (Test)** para garantizar una evaluación imparcial."
        )
        c_opt1, c_opt2 = st.columns(2)
        with c_opt1:
            scale_cont = st.checkbox(
                "Estandarizar continuas (StandardScaler)",
                value=False,
                help="Opcional: escala las variables numéricas continuas a media 0 y varianza 1.",
            )
        with c_opt2:
            rand_seed = st.number_input(
                "Semilla Aleatoria (Seed):",
                min_value=1,
                max_value=9999,
                value=42,
                step=1,
            )

        if st.button("🚀 Entrenar Modelo de Regresión Logística (70/30)", type="primary", use_container_width=True):
            # Si no se ha preparado X_prepared, ejecutar preparación automática
            if st.session_state["X_prepared"] is None:
                v_types = identify_variable_types(active_df)
                bin_cands = v_types.get("binary_candidates", [])
                t_col = bin_cands[-1] if bin_cands else active_df.columns[-1]
                f_cols = [c for c in active_df.columns if c != t_col]
                d_cols = [c for c in f_cols if c in v_types.get("discrete_categorical", [])]
                X_p, y_p, p_meta, p_err = validate_and_prepare_features(active_df, t_col, f_cols, d_cols)
                if p_err or X_p is None or y_p is None:
                    st.error(f"No fue posible preparar automáticamente las variables: {p_err}")
                    st.stop()
                st.session_state["X_prepared"] = X_p
                st.session_state["y_prepared"] = y_p
                st.session_state["prep_metadata"] = p_meta

            with st.spinner("Ajustando modelo de Regresión Logística (70% Train / 30% Test)..."):
                bundle, train_err = train_logistic_model(
                    st.session_state["X_prepared"],
                    st.session_state["y_prepared"],
                    test_size=0.30,
                    random_state=int(rand_seed),
                    scale_continuous=scale_cont,
                    target_metadata=st.session_state["prep_metadata"],
                )
                if train_err or bundle is None:
                    st.error(f"❌ Error al entrenar el modelo: {train_err}")
                else:
                    if st.session_state["prep_metadata"]:
                        bundle["target_mapping"] = st.session_state["prep_metadata"].get("target_mapping", {0: "0", 1: "1"})
                    st.session_state["model_bundle"] = bundle
                    st.session_state["custom_scenarios_input"] = None
                    st.session_state["custom_scenarios_df"] = None
                    st.session_state["scenarios_df"] = generate_simulation_scenarios(
                        bundle,
                        n_scenarios=10,
                        custom_scenarios_df=None,
                        threshold=st.session_state["threshold"],
                    )
                    st.toast("🎯 Modelo entrenado y 10 escenarios iniciales simulados.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_thresh_cfg:
        st.markdown('<div class="ui-card">', unsafe_allow_html=True)
        st.markdown("##### 🎚️ Hiperparámetro Dinámico: Umbral de Clasificación (Threshold)")
        st.caption(
            "Inicializado en **0.50**. Al ajustarlo, se recalculan en tiempo real la Matriz de Confusión, las métricas y las predicciones de los escenarios."
        )
        st.slider(
            "Umbral de Probabilidad P(Y=1) ≥ τ:",
            min_value=0.05,
            max_value=0.95,
            step=0.01,
            format="%.2f",
            key="slider_f3_thresh",
            on_change=_on_change_f3_thresh,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    # Mostrar resultados del modelo si ya fue entrenado
    if st.session_state["model_bundle"] is not None:
        bundle = st.session_state["model_bundle"]
        eval_now = evaluate_with_threshold(bundle, threshold=st.session_state["threshold"])

        # Resumen de partición y métricas clave
        st.markdown(
            f"""
            <div class="kpi-grid">
                <div class="kpi-box">
                    <div class="kpi-label">Muestra Entrenamiento (70%)</div>
                    <div class="kpi-value">{bundle.get("train_size", 0):,}</div>
                    <div class="kpi-sub">Observaciones de ajuste</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">Muestra Prueba (30%)</div>
                    <div class="kpi-value">{bundle.get("test_size", 0):,}</div>
                    <div class="kpi-sub">Validación Out-of-Sample</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">Intercepto (β₀)</div>
                    <div class="kpi-value">{bundle.get("intercept", 0.0):+.4f}</div>
                    <div class="kpi-sub">Log-odds base</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">ROC-AUC Score</div>
                    <div class="kpi-value">{eval_now.get("roc_auc", 0.0):.4f}</div>
                    <div class="kpi-sub">Poder discriminante global</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Ecuación Matemática explícita
        st.markdown("#### 📐 Ecuación Matemática de la Regresión Logística Ajustada")
        st.markdown(
            """
            <div class="ui-card">
                <p style="font-size: 0.9rem; margin-bottom: 0.5rem;">
                    La función sigmoide transforma la combinación lineal de pesos <span style="font-family: monospace;">Z = β₀ + Σ βᵢXᵢ</span> en una probabilidad acotada entre <strong>0 y 1</strong>:
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        eqs = bundle.get("equations", {})
        if eqs.get("latex_symbolic"):
            st.caption("1. Forma Simbólica General:")
            st.latex(eqs["latex_symbolic"])
        if eqs.get("latex_logit"):
            st.caption("2. Combinación Lineal Ajustada (Logit Z):")
            st.latex(eqs["latex_logit"])
        if eqs.get("latex_prob_numeric"):
            st.caption("3. Función de Probabilidad Sustituida P(Y=1):")
            st.latex(eqs["latex_prob_numeric"])

        with st.expander("📄 Ver Ecuación Lineal en Formato Texto Copiable", expanded=True):
            st.code(eqs.get("text_equation", ""), language="text")

        # Tabla de Coeficientes, Odds Ratios y Gráfico de Impacto
        st.markdown("#### 📊 Coeficientes ($\beta_i$), Odds Ratios ($e^{\beta_i}$) e Impacto Direccional")
        coef_df: pd.DataFrame = bundle.get("coef_df", pd.DataFrame())

        col_coef_tbl, col_coef_chart = st.columns([1.25, 1], gap="large")
        with col_coef_tbl:
            st.dataframe(
                coef_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Coeficiente_Beta": st.column_config.NumberColumn("Peso (βᵢ)", format="%+.4f"),
                    "Odds_Ratio": st.column_config.NumberColumn("Odds Ratio (e^βᵢ)", format="%.4f"),
                    "Cambio_Porcentual_Odds": st.column_config.NumberColumn("Cambio % Odds", format="%+.2f%%"),
                    "Impacto_Direccion": st.column_config.TextColumn("Impacto Direccional"),
                    "Importancia_Absoluta": st.column_config.NumberColumn("|βᵢ|", format="%.4f"),
                },
            )
        with col_coef_chart:
            st.markdown("##### 📈 Magnitud y Dirección de los Coeficientes (βᵢ)")
            if not coef_df.empty and "Coeficiente_Beta" in coef_df.columns:
                chart_df = coef_df.set_index("Variable")[["Coeficiente_Beta"]]
                st.bar_chart(chart_df, horizontal=True)
    else:
        st.warning("👆 Haz clic en **'Entrenar Modelo de Regresión Logística (70/30)'** para generar la ecuación y los coeficientes.")


# ==============================================================================
# FASE 4: EVALUACIÓN Y SIMULACIÓN (10+ ESCENARIOS)
# ==============================================================================
with tab_f4:
    st.subheader("🎯 Fase 4: Evaluación Dinámica y Simulador Interactivo de 10+ Escenarios")

    if st.session_state["model_bundle"] is None:
        st.info("🔒 Primero debes entrenar el modelo en la **Fase 3** para habilitar la evaluación y el simulador de escenarios.")
    else:
        bundle = st.session_state["model_bundle"]

        # Control sincronizado de Threshold también accesible en Fase 4
        col_f4_slider, col_f4_info = st.columns([1.3, 1], gap="large")
        with col_f4_slider:
            st.slider(
                "🎚️ Ajustar Umbral de Clasificación (Threshold τ) en Tiempo Real:",
                min_value=0.05,
                max_value=0.95,
                step=0.01,
                format="%.2f",
                key="slider_f4_sync",
                on_change=_on_change_f4_thresh,
            )

        eval_results = evaluate_with_threshold(bundle, threshold=st.session_state["threshold"])

        with col_f4_info:
            st.markdown(
                f"""
                <div class="ui-card" style="margin-bottom:0;">
                    <strong>Umbral Activo: <code>τ = {st.session_state["threshold"]:.2f}</code></strong><br/>
                    <span style="font-size:0.86rem; opacity:0.85;">
                        Si <code>P(Y=1) ≥ {st.session_state["threshold"]:.2f}</code> → Clase Positiva (1). En caso contrario → Clase Negativa (0).
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Tarjetas de métricas dinámicas con el Threshold actual
        st.markdown(
            f"""
            <div class="kpi-grid">
                <div class="kpi-box">
                    <div class="kpi-label">Accuracy (Exactitud Test)</div>
                    <div class="kpi-value">{eval_results.get("accuracy_test", 0.0) * 100:.1f}%</div>
                    <div class="kpi-sub">Train: {eval_results.get("accuracy_train", 0.0) * 100:.1f}%</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">Precision (Valor Pred. +)</div>
                    <div class="kpi-value">{eval_results.get("precision", 0.0) * 100:.1f}%</div>
                    <div class="kpi-sub">Pureza de alertas positivas</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">Recall (Sensibilidad)</div>
                    <div class="kpi-value">{eval_results.get("recall", 0.0) * 100:.1f}%</div>
                    <div class="kpi-sub">Cobertura de casos reales 1</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">F1-Score (Balance)</div>
                    <div class="kpi-value">{eval_results.get("f1_score", 0.0) * 100:.1f}%</div>
                    <div class="kpi-sub">Media armónica Prec/Recall</div>
                </div>
                <div class="kpi-box">
                    <div class="kpi-label">Specificity (Especificidad)</div>
                    <div class="kpi-value">{eval_results.get("specificity", 0.0) * 100:.1f}%</div>
                    <div class="kpi-sub">Detección correcta de clase 0</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Matriz de Confusión y Reporte de Clasificación
        col_cm, col_cr = st.columns([1.05, 1.15], gap="large")
        with col_cm:
            st.markdown("#### 🧱 Matriz de Confusión Dinámica (Set de Prueba 30%)")
            render_confusion_matrix_cards(eval_results)

        with col_cr:
            st.markdown("#### 📋 Reporte de Clasificación (Classification Report)")
            cr_df = eval_results.get("classification_report_df", pd.DataFrame())
            st.dataframe(
                cr_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Precisión (Precision)": st.column_config.NumberColumn("Precisión (Precision)", format="%.4f"),
                    "Sensibilidad (Recall)": st.column_config.NumberColumn("Sensibilidad (Recall)", format="%.4f"),
                    "F1-Score": st.column_config.NumberColumn("F1-Score", format="%.4f"),
                    "Soporte (Casos)": st.column_config.NumberColumn("Soporte (Casos)", format="%d"),
                },
            )

        st.divider()

        # --- Módulo Interactivo de Simulación de 10+ Escenarios ---
        st.markdown("### 🧪 Laboratorio de Simulación Interactiva (Mínimo 10 Escenarios)")
        st.write(
            "Edita directamente cualquier celda de las variables de entrada en la tabla inferior o agrega filas adicionales (`+`) para simular **10 o más escenarios estratégicos** y comparar su probabilidad frente al umbral activo."
        )

        feature_names: list[str] = bundle.get("feature_names", [])

        if st.session_state["scenarios_df"] is None:
            st.session_state["scenarios_df"] = generate_simulation_scenarios(
                bundle,
                n_scenarios=10,
                custom_scenarios_df=None,
                threshold=st.session_state["threshold"],
            )

        current_scenarios = st.session_state["scenarios_df"]

        col_sim_ctrl1, col_sim_ctrl2 = st.columns([1, 3])
        with col_sim_ctrl1:
            n_gen = st.number_input(
                "N.º de escenarios base:",
                min_value=10,
                max_value=50,
                value=max(10, len(current_scenarios)),
                step=1,
            )
            if st.button("🔄 Regenerar Escenarios Base", use_container_width=True):
                st.session_state["custom_scenarios_input"] = None
                st.session_state["custom_scenarios_df"] = None
                st.session_state["scenarios_df"] = generate_simulation_scenarios(
                    bundle,
                    n_scenarios=int(n_gen),
                    custom_scenarios_df=None,
                    threshold=st.session_state["threshold"],
                )
                st.rerun()

        # Editor interactivo para los valores de entrada de los escenarios
        editable_cols = ["Escenario"] + [c for c in feature_names if c in current_scenarios.columns]
        input_editor_df = current_scenarios[editable_cols].copy()

        st.markdown("##### ✏️ 1. Configura o Edita los Valores de Entrada de los Escenarios (10+ Filas)")
        edited_inputs_df = st.data_editor(
            input_editor_df,
            num_rows="dynamic",
            use_container_width=True,
            key="scenarios_data_editor",
        )

        if st.button("⚡ Recalcular Simulación con Valores Editados", type="primary"):
            st.session_state["custom_scenarios_input"] = edited_inputs_df
            st.session_state["custom_scenarios_df"] = edited_inputs_df
            st.session_state["scenarios_df"] = generate_simulation_scenarios(
                bundle,
                n_scenarios=max(10, len(edited_inputs_df)),
                custom_scenarios_df=edited_inputs_df,
                threshold=st.session_state["threshold"],
            )
            st.rerun()

        sim_results_df = st.session_state["scenarios_df"]

        # Mostrar tabla completa de resultados de simulación
        st.markdown(
            f"##### 📊 2. Resultados Predictivos de los {len(sim_results_df)} Escenarios (Umbral τ = {st.session_state['threshold']:.2f})"
        )
        result_cols_order = [
            "Escenario",
            "Probabilidad_Y1",
            "Porcentaje_Probabilidad",
            "Umbral_Aplicado",
            "Prediccion_Binaria",
            "Clasificacion_Etiqueta",
            "Nivel_Riesgo",
            "Logit_Z",
        ] + [c for c in feature_names if c in sim_results_df.columns]
        display_sim_cols = [c for c in result_cols_order if c in sim_results_df.columns]

        st.dataframe(
            sim_results_df[display_sim_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Probabilidad_Y1": st.column_config.ProgressColumn(
                    "Probabilidad P(Y=1)",
                    help="Probabilidad estimada por el modelo logístico",
                    format="%.4f",
                    min_value=0.0,
                    max_value=1.0,
                ),
                "Porcentaje_Probabilidad": st.column_config.NumberColumn("% Probabilidad", format="%.2f%%"),
                "Umbral_Aplicado": st.column_config.NumberColumn("Umbral τ", format="%.2f"),
                "Prediccion_Binaria": st.column_config.NumberColumn("Clase (0/1)", format="%d"),
                "Clasificacion_Etiqueta": st.column_config.TextColumn("Etiqueta Predicha"),
                "Nivel_Riesgo": st.column_config.TextColumn("Nivel de Riesgo"),
                "Logit_Z": st.column_config.NumberColumn("Logit (Z)", format="%+.4f"),
            },
        )

        # Gráfico comparativo de probabilidades frente al umbral
        st.markdown("##### 📈 Comparativa Visual: Probabilidad por Escenario vs. Umbral Activo")
        chart_sim_df = sim_results_df[["Escenario", "Probabilidad_Y1", "Umbral_Aplicado"]].copy()
        chart_sim_df = chart_sim_df.set_index("Escenario")
        st.bar_chart(chart_sim_df[["Probabilidad_Y1"]])
        st.caption(
            f"💡 **Línea de Corte Operativa**: Todos los escenarios con barra igual o superior a **{st.session_state['threshold']:.2f}** son clasificados como **Clase Positiva (1)**."
        )


# ==============================================================================
# FASE 5: VALOR DE NEGOCIO (ANALISTA DE NEGOCIOS)
# ==============================================================================
with tab_f5:
    st.subheader(f"💼 Fase 5: Traducción en Valor de Negocio — Sector {st.session_state['selected_sector']}")
    st.write(
        "Informe ejecutivo automatizado que traduce los coeficientes matemáticos ($\beta_i$), Odds Ratios y métricas predictivas en planes de acción para cada área corporativa."
    )

    if st.session_state["model_bundle"] is None:
        st.info("🔒 Entrena el modelo en la **Fase 3** para generar las recomendaciones ejecutivas personalizadas.")
    else:
        bundle = st.session_state["model_bundle"]
        eval_res = evaluate_with_threshold(bundle, threshold=st.session_state["threshold"])
        biz_rec = generate_business_recommendations(
            bundle,
            eval_res,
            sector=st.session_state["selected_sector"],
        )

        # Resumen Ejecutivo, Postura del Umbral y Drivers Clave
        st.markdown(
            f"""
            <div class="ui-card" style="border-left: 5px solid var(--ui-success);">
                <h4 style="margin-top: 0;">🧭 Resumen Ejecutivo ({biz_rec.get("sector", st.session_state["selected_sector"])})</h4>
                <p style="font-size: 0.95rem; margin-bottom: 0.5rem;">
                    {biz_rec.get("resumen_ejecutivo", "")}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        top_pos_driver = biz_rec.get("top_positive_driver", {})
        top_neg_driver = biz_rec.get("top_negative_driver", {})

        col_drv1, col_drv2, col_drv3 = st.columns(3, gap="medium")
        with col_drv1:
            st.markdown('<div class="ui-card">', unsafe_allow_html=True)
            st.markdown("##### 🎯 Postura Operativa del Umbral")
            st.markdown(f"**{biz_rec.get('postura_umbral', '')}**")
            st.caption(biz_rec.get("impacto_umbral", ""))
            st.markdown("</div>", unsafe_allow_html=True)

        with col_drv2:
            st.markdown('<div class="ui-card">', unsafe_allow_html=True)
            st.markdown("##### 📈 Principal Factor Acelerador (Y=1)")
            st.markdown(top_pos_driver.get("descripcion", "N/A"))
            st.caption("Incrementa con mayor fuerza las probabilidades relativas del evento objetivo.")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_drv3:
            st.markdown('<div class="ui-card">', unsafe_allow_html=True)
            st.markdown("##### 🛡️ Principal Factor Amortiguador (Y=0)")
            st.markdown(top_neg_driver.get("descripcion", "N/A"))
            st.caption("Actúa como ancla protectora reduciendo la probabilidad del evento.")
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("#### 🏛️ Planes de Acción Estratégicos por Dirección Corporativa")
        tab_mkt, tab_fin, tab_vta, tab_ceo = st.tabs(
            [
                "📣 Marketing",
                "💰 Finanzas",
                "🤝 Ventas / Comercial",
                "🏛️ Alta Dirección (C-Level)",
            ]
        )

        areas_config = [
            (tab_mkt, "Marketing", "#3b82f6"),
            (tab_fin, "Finanzas", "#10b981"),
            (tab_vta, "Ventas", "#f59e0b"),
            (tab_ceo, "Alta Dirección", "#8b5cf6"),
        ]

        for area_tab, area_key, accent_color in areas_config:
            with area_tab:
                area_data = biz_rec.get(area_key, {})
                area_icon = area_data.get("icono", "📌")
                area_title = area_data.get("titulo", area_key)
                enfoque_sec = area_data.get("enfoque_sector", "")
                diag_mod = area_data.get("diagnostico_modelo", "")
                estrategias = area_data.get("estrategias_accionables", [])
                kpis = area_data.get("kpis_sugeridos", [])
                impacto_esp = area_data.get("impacto_esperado", "")

                st.markdown(
                    f"""
                    <div class="ui-card" style="border-top: 4px solid {accent_color};">
                        <h4 style="margin-top: 0; margin-bottom: 0.35rem;">{area_icon} {area_title}</h4>
                        <p style="font-size: 0.88rem; opacity: 0.85; margin-bottom: 0.4rem;">
                            <strong>Foco Sectorial:</strong> {enfoque_sec}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.info(f"🩺 **Diagnóstico Cuantitativo del Modelo:** {diag_mod}")

                st.markdown("##### 🚀 Estrategias Accionables Recomendadas")
                for idx, est_text in enumerate(estrategias, start=1):
                    st.markdown(
                        f"""
                        <div class="ui-card" style="padding: 0.9rem 1.15rem; margin-bottom: 0.65rem;">
                            <strong>Plan de Acción #{idx}:</strong> {est_text}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                col_kpi_area, col_imp_area = st.columns([1.3, 1], gap="medium")
                with col_kpi_area:
                    st.markdown("##### 📊 KPIs de Seguimiento Sugeridos")
                    for kpi_item in kpis:
                        st.markdown(f"- 🎯 {kpi_item}")
                with col_imp_area:
                    st.markdown("##### 💡 Impacto de Negocio Esperado")
                    st.success(impacto_esp)


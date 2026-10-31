"""
backend_engine.py
=================
Motor de Lógica de Negocio, Procesamiento de Datos, Machine Learning (Regresión Logística)
y Simulación Estratégica para Toma de Decisiones Empresariales.

Responsabilidad:
- Ingesta multiformato (.csv, .xlsx/.xls, .pdf con extracción inteligente de tablas).
- Generación de datasets sintéticos realistas por sector económico.
- Diagnóstico y tratamiento de valores nulos sin pérdida de integridad.
- Identificación automática de tipos de variables (continuas, discretas/categóricas, binarias).
- Codificación de variables Dummy (One-Hot Encoding con drop_first=True) y validación estricta de Target binario.
- Entrenamiento de Regresión Logística respetando ML Best Practices (split 70/30 estratificado libre de data leakage).
- Extracción de ecuación matemática explícita (Logit Z, Probabilidad P(Y=1), Odds Ratios).
- Evaluación dinámica por umbral de decisión (Threshold) con Matriz de Confusión y Classification Report.
- Simulación de 10+ escenarios dinámicos y personalizados.
- Generación de recomendaciones estratégicas cuantitativas para Marketing, Finanzas, Ventas y Alta Dirección.
"""

from __future__ import annotations

import io
import re
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


# ==============================================================================
# FASE 1: INGESTA Y CONFIGURACIÓN
# ==============================================================================

SECTORES_ECONOMICOS: list[str] = [
    "Finanzas y Banca",
    "Retail y E-commerce",
    "Salud y Farmacéutica",
    "Telecomunicaciones",
    "Manufactura e Industria",
    "Tecnología y SaaS",
    "Educación",
    "Energía y Servicios Públicos",
]


def _clean_extracted_table_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia un DataFrame extraído desde PDF o archivo crudo:
    - Elimina saltos de línea en nombres de columnas y celdas.
    - Reemplaza textos vacíos ('', 'None', 'null', 'N/A', 'nan', '-') por np.nan.
    - Convierte automáticamente a numérico las columnas que contengan números (>80% valores convertibles).
    """
    df = raw_df.copy()

    # Limpiar nombres de columnas
    clean_cols: list[str] = []
    seen_cols: dict[str, int] = {}
    for idx, col in enumerate(df.columns):
        col_str = str(col if col is not None else "").replace("\n", " ").replace("\r", " ").strip()
        col_str = re.sub(r"\s+", "_", col_str)
        if not col_str or col_str.lower() in ("none", "nan", "unnamed"):
            col_str = f"Columna_{idx + 1}"
        if col_str in seen_cols:
            seen_cols[col_str] += 1
            col_str = f"{col_str}_{seen_cols[col_str]}"
        else:
            seen_cols[col_str] = 1
        clean_cols.append(col_str)
    df.columns = clean_cols

    # Limpiar celdas de texto y estandarizar nulos
    null_tokens = {"", "none", "null", "n/a", "na", "nan", "-", "--", "nil", "s/d"}
    for col in df.columns:
        if df[col].dtype == object:
            s = df[col].astype(str).str.replace("\n", " ", regex=False).str.replace("\r", " ", regex=False).str.strip()
            s = s.apply(lambda x: np.nan if x.lower() in null_tokens else x)
            df[col] = s

    # Eliminar filas y columnas completamente vacías
    df = df.dropna(how="all").reset_index(drop=True)
    df = df.dropna(axis=1, how="all")

    # Intentar conversión numérica inteligente columna por columna
    for col in df.columns:
        if df[col].dtype == object:
            non_null = df[col].dropna()
            if len(non_null) == 0:
                continue
            cleaned_num = (
                non_null.astype(str)
                .str.replace("$", "", regex=False)
                .str.replace("%", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
            if cleaned_num.str.contains(",", regex=False).all() and not cleaned_num.str.contains(".", regex=False).any():
                cleaned_num = cleaned_num.str.replace(",", ".", regex=False)
            else:
                cleaned_num = cleaned_num.str.replace(",", "", regex=False)

            converted = pd.to_numeric(cleaned_num, errors="coerce")
            valid_ratio = converted.notna().mean()
            if valid_ratio >= 0.80:
                full_cleaned = (
                    df[col]
                    .astype(str)
                    .str.replace("$", "", regex=False)
                    .str.replace("%", "", regex=False)
                    .str.replace(" ", "", regex=False)
                )
                if cleaned_num.str.contains(".", regex=False).any():
                    full_cleaned = full_cleaned.str.replace(",", "", regex=False)
                df[col] = pd.to_numeric(full_cleaned, errors="coerce")

    return df


def _rewind_file(file_obj: Any) -> None:
    """Rebobina un objeto de archivo si soporta seek(0)."""
    if hasattr(file_obj, "seek"):
        try:
            file_obj.seek(0)
        except Exception:
            pass


def load_dataset(file_obj: Any, filename: str) -> tuple[pd.DataFrame | None, str | None]:
    """
    Carga un dataset desde un archivo .csv, .xlsx/.xls o .pdf (extracción de tablas).

    Parámetros:
        file_obj: Objeto archivo (UploadedFile de Streamlit, BytesIO, o ruta en string).
        filename: Nombre del archivo con su extensión para determinar el parser adecuado.

    Retorna:
        tuple[pd.DataFrame | None, str | None]:
            - DataFrame cargado y pre-limpiado (o None si ocurrió un error).
            - Mensaje de error detallado y amigable (o None si la carga fue exitosa).
    """
    if file_obj is None or not filename:
        return None, "No se proporcionó ningún archivo válido para cargar."

    ext = filename.strip().lower().split(".")[-1] if "." in filename else ""
    if ext not in ("csv", "xlsx", "xls", "pdf"):
        return (
            None,
            f"Formato de archivo '.{ext}' no soportado. Por favor sube un archivo .csv, .xlsx o .pdf con tablas de datos.",
        )

    try:
        df: pd.DataFrame | None = None

        # 1. Carga de archivos CSV
        if ext == "csv":
            encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
            separators = [",", ";", "\t", "|"]
            last_err = ""
            for enc in encodings:
                for sep in separators:
                    try:
                        _rewind_file(file_obj)
                        candidate = pd.read_csv(file_obj, encoding=enc, sep=sep)
                        if candidate is not None and candidate.shape[1] >= 2 and candidate.shape[0] >= 1:
                            df = candidate
                            break
                    except Exception as e:
                        last_err = str(e)
                if df is not None:
                    break

            # Fallback con sep=None (detección automática de motor python)
            if df is None:
                for enc in encodings:
                    try:
                        _rewind_file(file_obj)
                        candidate = pd.read_csv(file_obj, encoding=enc, sep=None, engine="python")
                        if candidate is not None and candidate.shape[1] >= 2:
                            df = candidate
                            break
                    except Exception as e:
                        last_err = str(e)

            if df is None:
                return (
                    None,
                    f"No fue posible leer el archivo CSV '{filename}'. Verifica que tenga al menos 2 columnas separadas por coma o punto y coma. Detalle: {last_err}",
                )

        # 2. Carga de archivos Excel (.xlsx / .xls)
        elif ext in ("xlsx", "xls"):
            _rewind_file(file_obj)
            try:
                if ext == "xlsx":
                    df = pd.read_excel(file_obj, engine="openpyxl")
                else:
                    df = pd.read_excel(file_obj)
            except Exception as e:
                return (
                    None,
                    f"Error al abrir el archivo Excel '{filename}'. Asegúrate de que no esté protegido con contraseña ni corrupto. Detalle: {e}",
                )

        # 3. Carga de archivos PDF con extracción de tablas
        elif ext == "pdf":
            if pdfplumber is None:
                return (
                    None,
                    "La librería 'pdfplumber' no está instalada en el entorno para procesar archivos PDF.",
                )
            _rewind_file(file_obj)
            extracted_dfs: list[pd.DataFrame] = []
            header_reference: list[str] | None = None

            try:
                with pdfplumber.open(file_obj) as pdf:
                    if len(pdf.pages) == 0:
                        return None, f"El archivo PDF '{filename}' no contiene páginas."

                    for page in pdf.pages:
                        tables = page.extract_tables()
                        if not tables:
                            continue
                        for table in tables:
                            valid_rows = [
                                row
                                for row in table
                                if row and any(cell is not None and str(cell).strip() != "" for cell in row)
                            ]
                            if len(valid_rows) < 2:
                                continue

                            first_row_clean = [
                                str(c if c is not None else "").replace("\n", " ").strip() for c in valid_rows[0]
                            ]
                            if header_reference is None:
                                header_reference = first_row_clean
                                data_rows = valid_rows[1:]
                                page_df = pd.DataFrame(data_rows, columns=header_reference)
                                extracted_dfs.append(page_df)
                            elif len(first_row_clean) == len(header_reference):
                                if first_row_clean == header_reference:
                                    data_rows = valid_rows[1:]
                                else:
                                    data_rows = valid_rows
                                if data_rows:
                                    page_df = pd.DataFrame(data_rows, columns=header_reference)
                                    extracted_dfs.append(page_df)
                            else:
                                page_df = pd.DataFrame(valid_rows[1:], columns=first_row_clean)
                                extracted_dfs.append(page_df)
            except Exception as e:
                return (
                    None,
                    f"No se pudo procesar el documento PDF '{filename}'. Verifica que sea un PDF válido y no esté encriptado. Detalle: {e}",
                )

            if not extracted_dfs:
                return (
                    None,
                    f"No se detectaron tablas estructuradas en el archivo PDF '{filename}'. Asegúrate de que el PDF contenga tablas con texto seleccionable (no imágenes escaneadas).",
                )

            col_counts = [d.shape[1] for d in extracted_dfs]
            target_col_count = max(set(col_counts), key=col_counts.count)
            compatible_dfs = [d for d in extracted_dfs if d.shape[1] == target_col_count]
            base_cols = list(compatible_dfs[0].columns)
            normalized_dfs = []
            for d in compatible_dfs:
                d_copy = d.copy()
                d_copy.columns = base_cols
                normalized_dfs.append(d_copy)
            df = pd.concat(normalized_dfs, ignore_index=True)

        # Validaciones posteriores a la lectura
        if df is None or df.empty:
            return None, f"El archivo '{filename}' está vacío o no contiene registros válidos."

        df = _clean_extracted_table_df(df)

        if df.shape[1] < 2:
            return (
                None,
                f"El dataset cargado tiene solo {df.shape[1]} columna(s). Se requieren al menos 2 columnas (1 variable predictora y 1 variable objetivo).",
            )
        if df.shape[0] < 10:
            return (
                None,
                f"El dataset contiene muy pocas filas ({df.shape[0]}). Se requieren al menos 10 observaciones para entrenar un modelo de Regresión Logística.",
            )

        return df, None

    except Exception as exc:
        return None, f"Error inesperado al procesar el archivo '{filename}': {exc}"


def generate_sample_dataset(sector: str, n_rows: int = 250, random_state: int = 42) -> pd.DataFrame:
    """
    Genera un dataset sintético realista de al menos 200 filas adaptado al sector económico elegido.
    Incluye variables numéricas continuas, discretas/categóricas, ~4% de valores nulos intencionales
    en algunas columnas predictoras, y una variable objetivo binaria realista para Regresión Logística.

    Parámetros:
        sector: Nombre del sector económico (de SECTORES_ECONOMICOS).
        n_rows: Cantidad de filas a generar (mínimo 200, por defecto 250).
        random_state: Semilla aleatoria para reproducibilidad.

    Retorna:
        pd.DataFrame: Dataset sintético listo para usar o descargar.
    """
    n = max(int(n_rows), 200)
    rng = np.random.default_rng(random_state)

    def _inject_nulls(arr: np.ndarray | list[Any], rate: float = 0.04) -> list[Any]:
        out = list(arr)
        n_null = max(1, int(len(out) * rate))
        idx = rng.choice(len(out), size=n_null, replace=False)
        for i in idx:
            out[i] = np.nan
        return out

    if sector == "Finanzas y Banca":
        ingreso = np.round(rng.normal(4200, 1400, n).clip(900, 12000), 2)
        ratio_deuda = np.round(rng.uniform(0.10, 0.85, n), 3)
        score_crediticio = rng.integers(350, 850, n).astype(float)
        antiguedad_anios = np.round(rng.exponential(4.5, n).clip(0.2, 25.0), 1)
        productos_activos = rng.integers(1, 6, n)
        segmento = rng.choice(["Banca Personal", "PyME", "Preferente"], size=n, p=[0.60, 0.25, 0.15])
        canal_origen = rng.choice(["App Móvil", "Sucursal", "Web"], size=n, p=[0.50, 0.30, 0.20])
        historial_mora_previa = rng.choice(["Sí", "No"], size=n, p=[0.28, 0.72])

        logit = (
            -1.2
            - 0.00045 * (ingreso - 4000)
            + 4.2 * (ratio_deuda - 0.45)
            - 0.009 * (score_crediticio - 600)
            + 1.35 * (historial_mora_previa == "Sí").astype(float)
            - 0.12 * antiguedad_anios
            + 0.45 * (segmento == "PyME").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Ingreso_Mensual_USD": _inject_nulls(ingreso, 0.04),
                "Ratio_Deuda_Ingreso": _inject_nulls(ratio_deuda, 0.03),
                "Score_Crediticio": _inject_nulls(score_crediticio, 0.04),
                "Antiguedad_Anios": antiguedad_anios,
                "Productos_Activos": productos_activos,
                "Segmento_Cliente": _inject_nulls(segmento, 0.03),
                "Canal_Captacion": canal_origen,
                "Mora_Previa": historial_mora_previa,
                "Default_Pago": target,
            }
        )

    elif sector == "Retail y E-commerce":
        gasto_mensual = np.round(rng.normal(280, 110, n).clip(20, 900), 2)
        dias_ultima_compra = np.round(rng.exponential(28, n).clip(1, 180), 0)
        tasa_devolucion = np.round(rng.uniform(0.0, 0.45, n), 3)
        sesiones_mes = rng.integers(1, 35, n).astype(float)
        categoria_fav = rng.choice(["Electrónica", "Moda", "Hogar", "Supermercado"], size=n)
        miembro_vip = rng.choice(["Sí", "No"], size=n, p=[0.35, 0.65])
        uso_cupones = rng.choice(["Frecuente", "Ocasional", "Nunca"], size=n, p=[0.40, 0.40, 0.20])

        logit = (
            -0.9
            - 0.007 * (gasto_mensual - 250)
            + 0.038 * (dias_ultima_compra - 30)
            + 3.1 * (tasa_devolucion - 0.15)
            - 0.08 * (sesiones_mes - 12)
            - 1.15 * (miembro_vip == "Sí").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Gasto_Promedio_Mensual_USD": _inject_nulls(gasto_mensual, 0.04),
                "Dias_Desde_Ultima_Compra": _inject_nulls(dias_ultima_compra, 0.03),
                "Tasa_Devoluciones": tasa_devolucion,
                "Sesiones_App_Mes": _inject_nulls(sesiones_mes, 0.04),
                "Categoria_Principal": _inject_nulls(categoria_fav, 0.03),
                "Membresia_VIP": miembro_vip,
                "Frecuencia_Cupones": uso_cupones,
                "Churn_Cliente": target,
            }
        )

    elif sector == "Salud y Farmacéutica":
        edad = rng.integers(22, 88, n).astype(float)
        dias_estancia = np.round(rng.exponential(5.5, n).clip(1, 30), 1)
        indice_comorbilidad = np.round(rng.uniform(0.5, 9.5, n), 2)
        adherencia_tratamiento = np.round(rng.uniform(35.0, 99.0, n), 1)
        visitas_urgencias_anio = rng.integers(0, 7, n)
        tipo_seguro = rng.choice(["Privado", "Público", "Mixto"], size=n, p=[0.35, 0.45, 0.20])
        seguimiento_domiciliario = rng.choice(["Sí", "No"], size=n, p=[0.42, 0.58])

        logit = (
            -1.1
            + 0.025 * (edad - 55)
            + 0.14 * (dias_estancia - 5)
            + 0.35 * (indice_comorbilidad - 4.0)
            - 0.045 * (adherencia_tratamiento - 70)
            + 0.30 * visitas_urgencias_anio
            - 0.95 * (seguimiento_domiciliario == "Sí").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Edad_Paciente": _inject_nulls(edad, 0.03),
                "Dias_Estancia_Hospitalaria": dias_estancia,
                "Indice_Severidad_Comorbilidad": _inject_nulls(indice_comorbilidad, 0.04),
                "Porcentaje_Adherencia_Medica": _inject_nulls(adherencia_tratamiento, 0.04),
                "Visitas_Urgencias_Previas": visitas_urgencias_anio,
                "Tipo_Cobertura": _inject_nulls(tipo_seguro, 0.03),
                "Programa_Seguimiento": seguimiento_domiciliario,
                "Reingreso_30d": target,
            }
        )

    elif sector == "Telecomunicaciones":
        cargo_mensual = np.round(rng.normal(65, 22, n).clip(18, 150), 2)
        antiguedad_meses = rng.integers(1, 72, n).astype(float)
        consumo_datos_gb = np.round(rng.normal(45, 25, n).clip(2, 180), 1)
        tickets_soporte = rng.integers(0, 8, n).astype(float)
        tipo_contrato = rng.choice(["Mes a Mes", "Anual", "Bianual"], size=n, p=[0.50, 0.30, 0.20])
        fibra_optica = rng.choice(["Sí", "No"], size=n, p=[0.60, 0.40])
        pago_automatico = rng.choice(["Sí", "No"], size=n, p=[0.52, 0.48])

        logit = (
            -0.8
            + 0.028 * (cargo_mensual - 65)
            - 0.042 * (antiguedad_meses - 24)
            + 0.42 * (tickets_soporte - 2)
            + 1.25 * (tipo_contrato == "Mes a Mes").astype(float)
            - 0.75 * (pago_automatico == "Sí").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Cargo_Mensual_USD": _inject_nulls(cargo_mensual, 0.04),
                "Antiguedad_Meses": _inject_nulls(antiguedad_meses, 0.03),
                "Consumo_Datos_GB": consumo_datos_gb,
                "Tickets_Soporte_Trimestre": _inject_nulls(tickets_soporte, 0.04),
                "Tipo_Contrato": _inject_nulls(tipo_contrato, 0.03),
                "Red_Fibra_Optica": fibra_optica,
                "Pago_Automatico": pago_automatico,
                "Fuga_Suscriptor": target,
            }
        )

    elif sector == "Manufactura e Industria":
        horas_operacion = np.round(rng.normal(1450, 420, n).clip(200, 3200), 1)
        temperatura_c = np.round(rng.normal(78, 12, n).clip(45, 125), 2)
        vibracion_mm_s = np.round(rng.uniform(1.2, 11.5, n), 2)
        dias_desde_mantenimiento = rng.integers(5, 180, n).astype(float)
        turno_operacion = rng.choice(["Matutino", "Vespertino", "Nocturno"], size=n, p=[0.40, 0.35, 0.25])
        proveedor_repuestos = rng.choice(["OEM Certificado", "Alternativo"], size=n, p=[0.65, 0.35])

        logit = (
            -1.3
            + 0.0018 * (horas_operacion - 1400)
            + 0.075 * (temperatura_c - 78)
            + 0.38 * (vibracion_mm_s - 5.5)
            + 0.018 * (dias_desde_mantenimiento - 60)
            + 0.85 * (proveedor_repuestos == "Alternativo").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Horas_Operacion_Continua": _inject_nulls(horas_operacion, 0.04),
                "Temperatura_Promedio_C": _inject_nulls(temperatura_c, 0.03),
                "Indice_Vibracion_MMS": vibracion_mm_s,
                "Dias_Desde_Mantenimiento": _inject_nulls(dias_desde_mantenimiento, 0.04),
                "Turno_Planta": _inject_nulls(turno_operacion, 0.03),
                "Tipo_Repuestos": proveedor_repuestos,
                "Falla_Critica_Equipo": target,
            }
        )

    elif sector == "Tecnología y SaaS":
        mrr_usd = np.round(rng.normal(450, 210, n).clip(49, 1800), 2)
        usuarios_activos_pct = np.round(rng.uniform(15.0, 98.0, n), 1)
        tickets_bugs = rng.integers(0, 10, n).astype(float)
        integraciones_api = rng.integers(0, 8, n)
        plan_suscripcion = rng.choice(["Starter", "Professional", "Enterprise"], size=n, p=[0.45, 0.38, 0.17])
        onboarding_completo = rng.choice(["Sí", "No"], size=n, p=[0.62, 0.38])

        logit = (
            -0.7
            - 0.0022 * (mrr_usd - 450)
            - 0.048 * (usuarios_activos_pct - 55)
            + 0.35 * (tickets_bugs - 3)
            - 0.28 * (integraciones_api - 3)
            - 1.10 * (onboarding_completo == "Sí").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "MRR_Mensual_USD": _inject_nulls(mrr_usd, 0.04),
                "Porcentaje_Usuarios_Activos": _inject_nulls(usuarios_activos_pct, 0.04),
                "Tickets_Soporte_Mes": tickets_bugs,
                "Integraciones_API_Activas": _inject_nulls(integraciones_api, 0.03),
                "Plan_SaaS": _inject_nulls(plan_suscripcion, 0.03),
                "Onboarding_Completado": onboarding_completo,
                "Churn_Suscripcion": target,
            }
        )

    elif sector == "Educación":
        promedio_notas = np.round(rng.normal(3.4, 0.65, n).clip(1.5, 5.0), 2)
        asistencia_pct = np.round(rng.uniform(45.0, 100.0, n), 1)
        horas_plataforma_sem = np.round(rng.normal(11, 5, n).clip(0.5, 32), 1)
        materias_reprobadas = rng.integers(0, 5, n)
        modalidad = rng.choice(["Presencial", "Virtual", "Híbrida"], size=n, p=[0.45, 0.35, 0.20])
        beca_financiera = rng.choice(["Sí", "No"], size=n, p=[0.38, 0.62])

        logit = (
            -0.6
            - 1.45 * (promedio_notas - 3.3)
            - 0.055 * (asistencia_pct - 75)
            - 0.11 * (horas_plataforma_sem - 10)
            + 0.65 * (materias_reprobadas - 1)
            - 0.80 * (beca_financiera == "Sí").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Promedio_Academico_GPA": _inject_nulls(promedio_notas, 0.04),
                "Porcentaje_Asistencia": _inject_nulls(asistencia_pct, 0.03),
                "Horas_Plataforma_Semanal": _inject_nulls(horas_plataforma_sem, 0.04),
                "Materias_Reprobadas": materias_reprobadas,
                "Modalidad_Estudio": _inject_nulls(modalidad, 0.03),
                "Beca_Activa": beca_financiera,
                "Desercion_Estudiantil": target,
            }
        )

    else:  # "Energía y Servicios Públicos" o fallback general
        consumo_kwh = np.round(rng.normal(380, 145, n).clip(60, 1100), 1)
        factura_mensual_usd = np.round(consumo_kwh * rng.uniform(0.18, 0.28, n), 2)
        retrasos_12m = rng.integers(0, 6, n).astype(float)
        antiguedad_servicio_anios = np.round(rng.exponential(5.0, n).clip(0.3, 25.0), 1)
        estrato_tarifa = rng.choice(["Residencial", "Comercial", "Industrial"], size=n, p=[0.65, 0.25, 0.10])
        medidor_inteligente = rng.choice(["Sí", "No"], size=n, p=[0.48, 0.52])

        logit = (
            -1.0
            + 0.012 * (factura_mensual_usd - 85)
            + 0.72 * (retrasos_12m - 1.5)
            - 0.10 * (antiguedad_servicio_anios - 4.5)
            - 0.65 * (medidor_inteligente == "Sí").astype(float)
        )
        prob = 1.0 / (1.0 + np.exp(-logit))
        target = (rng.uniform(0, 1, n) < prob).astype(int)

        df = pd.DataFrame(
            {
                "Consumo_Mensual_kWh": _inject_nulls(consumo_kwh, 0.04),
                "Monto_Factura_USD": _inject_nulls(factura_mensual_usd, 0.03),
                "Retrasos_Pago_Anio": _inject_nulls(retrasos_12m, 0.04),
                "Antiguedad_Contrato_Anios": antiguedad_servicio_anios,
                "Tipo_Tarifa": _inject_nulls(estrato_tarifa, 0.03),
                "Medidor_Inteligente": medidor_inteligente,
                "Riesgo_Suspension_Mora": target,
            }
        )

    return df


def get_dataframe_head(df: pd.DataFrame, n: int = 2) -> pd.DataFrame:
    """
    Devuelve exactamente las primeras `n` filas del DataFrame (por defecto 2 filas, según requerimiento).
    """
    if df is None or df.empty:
        return pd.DataFrame()
    return df.head(max(1, int(n))).copy()


# ==============================================================================
# FASE 2: PREPROCESAMIENTO Y PREPARACIÓN DE VARIABLES
# ==============================================================================


def analyze_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """
    Analiza la cantidad y porcentaje de valores nulos por columna.

    Retorna:
        pd.DataFrame con columnas ['Columna', 'Tipo', 'Nulos', 'Porcentaje_Nulos'].
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["Columna", "Tipo", "Nulos", "Porcentaje_Nulos"])

    total_rows = len(df)
    null_counts = df.isna().sum()
    null_pcts = (null_counts / total_rows * 100.0).round(2) if total_rows > 0 else null_counts * 0.0

    summary_df = pd.DataFrame(
        {
            "Columna": df.columns.astype(str),
            "Tipo": [str(df[col].dtype) for col in df.columns],
            "Nulos": null_counts.values.astype(int),
            "Porcentaje_Nulos": null_pcts.values.astype(float),
        }
    )
    return summary_df.reset_index(drop=True)


def handle_nulls(
    df: pd.DataFrame,
    strategy: str = "impute_median_mode",
    fill_numeric: str = "median",
    fill_categorical: str = "mode",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Aplica la estrategia seleccionada de limpieza o imputación de valores nulos.

    Estrategias soportadas en `strategy`:
        - 'drop_rows': Elimina las filas que contengan al menos un valor nulo.
        - 'impute_median_mode': Imputa mediana en variables numéricas y moda en categóricas.
        - 'impute_mean_mode': Imputa media en variables numéricas y moda en categóricas.
        - 'zero_or_unknown': Imputa 0 en numéricas y 'Desconocido' en categóricas.
        - 'impute': Estrategia configurable usando `fill_numeric` ('median'|'mean'|'zero')
                    y `fill_categorical` ('mode'|'unknown').

    Verifica que tras la limpieza queden al menos 10 filas válidas. Si 'drop_rows' dejara menos
    de 10 filas, aplica imputación por mediana/moda automáticamente e informa en el diccionario de estado.

    Retorna:
        tuple[pd.DataFrame, dict]: (df_clean, stats_dict)
    """
    if df is None or df.empty:
        return pd.DataFrame(), {
            "rows_before": 0,
            "rows_after": 0,
            "nulls_before": 0,
            "nulls_after": 0,
            "strategy_requested": strategy,
            "strategy_applied": "none",
            "fallback_triggered": False,
            "message": "El DataFrame de entrada está vacío.",
        }

    df_work = df.copy()
    rows_before = len(df_work)
    nulls_before = int(df_work.isna().sum().sum())
    fallback_triggered = False
    warning_msg = ""

    effective_strategy = strategy
    if strategy == "impute":
        if fill_numeric == "mean":
            effective_strategy = "impute_mean_mode"
        elif fill_numeric == "zero":
            effective_strategy = "zero_or_unknown"
        else:
            effective_strategy = "impute_median_mode"

    if effective_strategy == "drop_rows":
        candidate_df = df_work.dropna().reset_index(drop=True)
        if len(candidate_df) < 10:
            fallback_triggered = True
            effective_strategy = "impute_median_mode"
            warning_msg = (
                f"Eliminar filas con nulos dejaría solo {len(candidate_df)} filas (<10 requeridas). "
                "Se aplicó imputación automática (Mediana/Moda) para preservar la viabilidad del modelo."
            )
        else:
            df_work = candidate_df

    if effective_strategy in ("impute_median_mode", "impute_mean_mode", "zero_or_unknown"):
        for col in df_work.columns:
            if df_work[col].isna().sum() == 0:
                continue

            if pd.api.types.is_numeric_dtype(df_work[col]) and not pd.api.types.is_bool_dtype(df_work[col]):
                non_null_vals = df_work[col].dropna()
                if len(non_null_vals) == 0:
                    df_work[col] = df_work[col].fillna(0.0)
                elif effective_strategy == "impute_median_mode":
                    df_work[col] = df_work[col].fillna(float(non_null_vals.median()))
                elif effective_strategy == "impute_mean_mode":
                    df_work[col] = df_work[col].fillna(float(non_null_vals.mean()))
                else:  # zero_or_unknown
                    df_work[col] = df_work[col].fillna(0.0)
            else:
                non_null_vals = df_work[col].dropna()
                if len(non_null_vals) == 0:
                    df_work[col] = df_work[col].fillna("Desconocido")
                elif effective_strategy in ("impute_median_mode", "impute_mean_mode"):
                    mode_series = non_null_vals.mode()
                    fill_val = mode_series.iloc[0] if not mode_series.empty else "Desconocido"
                    df_work[col] = df_work[col].fillna(fill_val)
                else:  # zero_or_unknown
                    df_work[col] = df_work[col].fillna("Desconocido")

    rows_after = len(df_work)
    nulls_after = int(df_work.isna().sum().sum())

    if not warning_msg:
        warning_msg = (
            f"Preprocesamiento completado exitosamente mediante '{effective_strategy}'. "
            f"Nulos reducidos de {nulls_before} a {nulls_after} ({rows_after} filas conservadas)."
        )

    stats_dict = {
        "rows_before": rows_before,
        "rows_after": rows_after,
        "rows_dropped": rows_before - rows_after,
        "nulls_before": nulls_before,
        "nulls_after": nulls_after,
        "strategy_requested": strategy,
        "strategy_applied": effective_strategy,
        "fallback_triggered": fallback_triggered,
        "is_valid": rows_after >= 10 and nulls_after == 0,
        "message": warning_msg,
    }
    return df_work, stats_dict


def identify_variable_types(df: pd.DataFrame) -> dict[str, Any]:
    """
    Identifica automáticamente las variables continuas, discretas/categóricas y candidatas binarias.

    Reglas:
        - 'continuous': Columnas numéricas (float o int) con cardinalidad > 10 valores únicos no nulos.
        - 'discrete_categorical': Columnas categóricas (object, category, bool) o numéricas discretas
                                  con <= 10 valores únicos no nulos.
        - 'binary_candidates': Columnas con exactamente 2 valores únicos (excluyendo nulos),
                               aptas para ser la variable dependiente (Target Y) en Regresión Logística.

    Retorna:
        dict con llaves: 'continuous', 'discrete_categorical', 'binary_candidates', 'all_columns', 'details'.
    """
    if df is None or df.empty:
        return {
            "continuous": [],
            "discrete_categorical": [],
            "binary_candidates": [],
            "all_columns": [],
            "details": {},
        }

    continuous_cols: list[str] = []
    discrete_categorical_cols: list[str] = []
    binary_candidates: list[str] = []
    details: dict[str, dict[str, Any]] = {}

    for col in df.columns:
        series = df[col].dropna()
        n_unique = int(series.nunique())
        is_num = pd.api.types.is_numeric_dtype(df[col]) and not pd.api.types.is_bool_dtype(df[col])

        if n_unique == 2:
            binary_candidates.append(col)

        if is_num and n_unique > 10:
            continuous_cols.append(col)
            var_category = "Continua"
        else:
            discrete_categorical_cols.append(col)
            var_category = "Discreta / Categórica"

        sample_vals = [str(v) for v in series.unique()[:5]]
        details[col] = {
            "dtype": str(df[col].dtype),
            "unique_count": n_unique,
            "is_numeric": is_num,
            "is_binary": n_unique == 2,
            "classification": var_category,
            "sample_values": sample_vals,
        }

    return {
        "continuous": continuous_cols,
        "discrete_categorical": discrete_categorical_cols,
        "binary_candidates": binary_candidates,
        "all_columns": list(df.columns),
        "details": details,
    }


def _map_binary_target(series: pd.Series) -> tuple[pd.Series, dict[int, str], dict[str, int]]:
    """
    Mapea una serie de exactamente 2 clases únicas a valores enteros {0, 1} de forma semántica.
    Prioriza que etiquetas positivas comunes ('1', 'sí', 'si', 'yes', 'true', 'positivo', 'alto', 'churn', 'default')
    reciban el valor 1.
    """
    clean_s = series.dropna()
    unique_vals = list(clean_s.unique())

    if set(unique_vals) == {0, 1} or set(unique_vals) == {0.0, 1.0}:
        mapped = series.astype(float).astype(int)
        mapping = {0: "0 (Clase Negativa)", 1: "1 (Clase Positiva)"}
        inv_mapping = {"0": 0, "1": 1}
        return mapped, mapping, inv_mapping

    positive_tokens = {
        "1",
        "1.0",
        "si",
        "sí",
        "yes",
        "true",
        "verdadero",
        "positivo",
        "positive",
        "alto",
        "high",
        "churn",
        "fuga",
        "default",
        "mora",
        "falla",
        "reingreso",
        "desercion",
        "activo",
    }

    val_str_0 = str(unique_vals[0]).strip().lower()
    val_str_1 = str(unique_vals[1]).strip().lower()

    if val_str_0 in positive_tokens and val_str_1 not in positive_tokens:
        neg_val, pos_val = unique_vals[1], unique_vals[0]
    elif val_str_1 in positive_tokens and val_str_0 not in positive_tokens:
        neg_val, pos_val = unique_vals[0], unique_vals[1]
    else:
        try:
            sorted_vals = sorted(unique_vals)
        except TypeError:
            sorted_vals = sorted(unique_vals, key=lambda x: str(x))
        neg_val, pos_val = sorted_vals[0], sorted_vals[1]

    raw_map = {neg_val: 0, pos_val: 1}
    mapped_series = series.map(raw_map).astype(int)
    target_mapping = {0: str(neg_val), 1: str(pos_val)}
    inverse_mapping = {str(neg_val): 0, str(pos_val): 1}
    return mapped_series, target_mapping, inverse_mapping


def validate_and_prepare_features(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    dummy_cols: list[str] | None = None,
) -> tuple[pd.DataFrame | None, pd.Series | None, dict[str, Any] | None, str | None]:
    """
    Valida la variable objetivo (debe ser estrictamente binaria) y prepara la matriz de características X
    aplicando codificación Dummy (One-Hot Encoding con drop_first=True) a las variables seleccionadas
    y a cualquier variable de texto/categórica remanente para evitar errores en LogisticRegression.

    Parámetros:
        df: DataFrame limpio.
        target_col: Nombre de la variable dependiente (Y).
        feature_cols: Lista de variables independientes (X).
        dummy_cols: Lista de columnas dentro de `feature_cols` que el usuario seleccionó para convertir en Dummy.

    Retorna:
        tuple[X_prepared, y_prepared, metadata_dict, error_msg]
    """
    if df is None or df.empty:
        return None, None, None, "El DataFrame está vacío. Carga y limpia los datos antes de continuar."

    if not target_col or target_col not in df.columns:
        return None, None, None, f"La variable objetivo '{target_col}' no existe en el dataset."

    if not feature_cols:
        return None, None, None, "Debes seleccionar al menos una variable independiente (predictora X)."

    clean_features = [c for c in feature_cols if c != target_col and c in df.columns]
    if not clean_features:
        return (
            None,
            None,
            None,
            "La lista de variables predictoras X no puede contener únicamente a la misma variable objetivo Y.",
        )

    valid_mask = df[target_col].notna()
    df_valid = df.loc[valid_mask].copy().reset_index(drop=True)

    n_classes = int(df_valid[target_col].nunique(dropna=True))
    if n_classes != 2:
        var_info = identify_variable_types(df_valid)
        bin_suggestions = var_info.get("binary_candidates", [])
        sug_text = (
            f"Variables binarias disponibles en tu dataset: {', '.join(bin_suggestions)}."
            if bin_suggestions
            else "No se detectaron columnas con exactamente 2 valores únicos en el dataset actual."
        )
        return (
            None,
            None,
            None,
            f"La variable objetivo seleccionada '{target_col}' tiene {n_classes} valores únicos y la Regresión Logística Binaria requiere exactamente 2 categorías (ej. 0/1, Sí/No). {sug_text}",
        )

    y_prepared, target_mapping, inverse_target_mapping = _map_binary_target(df_valid[target_col])

    class_counts = y_prepared.value_counts()
    if class_counts.min() < 2:
        return (
            None,
            None,
            None,
            f"La clase minoritaria de '{target_col}' tiene solo {int(class_counts.min())} registro(s). Se requieren al menos 2 casos por clase para dividir en entrenamiento y prueba.",
        )

    X_raw = df_valid[clean_features].copy()

    user_dummy_cols = [c for c in (dummy_cols or []) if c in clean_features]
    auto_encoded_cols: list[str] = []
    for col in clean_features:
        is_num = pd.api.types.is_numeric_dtype(X_raw[col]) and not pd.api.types.is_bool_dtype(X_raw[col])
        if not is_num and col not in user_dummy_cols:
            auto_encoded_cols.append(col)

    all_dummy_cols = list(dict.fromkeys(user_dummy_cols + auto_encoded_cols))

    for col in X_raw.columns:
        if X_raw[col].isna().any():
            if pd.api.types.is_numeric_dtype(X_raw[col]) and not pd.api.types.is_bool_dtype(X_raw[col]):
                med = X_raw[col].median()
                X_raw[col] = X_raw[col].fillna(0.0 if pd.isna(med) else med)
            else:
                modes = X_raw[col].mode()
                X_raw[col] = X_raw[col].fillna(modes.iloc[0] if not modes.empty else "Desconocido")

    for col in all_dummy_cols:
        X_raw[col] = X_raw[col].astype(str).str.strip()

    if all_dummy_cols:
        X_prepared = pd.get_dummies(X_raw, columns=all_dummy_cols, drop_first=True, dtype=float)
    else:
        X_prepared = X_raw.copy()

    try:
        X_prepared = X_prepared.astype(float)
    except Exception as exc:
        return (
            None,
            None,
            None,
            f"No fue posible convertir todas las variables predictoras a formato numérico: {exc}",
        )

    constant_cols = [c for c in X_prepared.columns if X_prepared[c].nunique(dropna=True) <= 1]
    if len(constant_cols) == len(X_prepared.columns):
        return (
            None,
            None,
            None,
            "Todas las variables seleccionadas tienen valor constante (varianza cero). Selecciona variables con variabilidad.",
        )

    metadata_dict = {
        "target_col": target_col,
        "target_mapping": target_mapping,
        "inverse_target_mapping": inverse_target_mapping,
        "class_distribution": {
            f"0 ({target_mapping[0]})": int((y_prepared == 0).sum()),
            f"1 ({target_mapping[1]})": int((y_prepared == 1).sum()),
        },
        "positive_rate": float(y_prepared.mean()),
        "original_features": clean_features,
        "user_dummy_cols": user_dummy_cols,
        "auto_encoded_cols": auto_encoded_cols,
        "all_dummy_cols": all_dummy_cols,
        "final_feature_names": list(X_prepared.columns),
        "n_samples": len(X_prepared),
        "n_features_before_encoding": len(clean_features),
        "n_features_after_encoding": X_prepared.shape[1],
        "constant_cols_detected": constant_cols,
    }

    return X_prepared, y_prepared, metadata_dict, None


# ==============================================================================
# FASE 3: MODELADO MACHINE LEARNING (REGRESIÓN LOGÍSTICA)
# ==============================================================================


def _format_latex_equation(intercept: float, coef_series: pd.Series) -> dict[str, str]:
    """
    Construye las representaciones matemáticas de la ecuación de Regresión Logística:
    - Fórmula general simbólica en LaTeX.
    - Ecuación del Logit (Z) con los valores reales de los coeficientes Beta.
    - Ecuación completa de Probabilidad P(Y=1) sustituida.
    - Versión en texto plano amigable.
    """
    latex_symbolic = r"P(Y=1) = \frac{1}{1 + e^{-\left(\beta_0 + \beta_1 X_1 + \beta_2 X_2 + \dots + \beta_n X_n\right)}}"

    latex_terms: list[str] = [f"{intercept:.4f}"]
    text_terms: list[str] = [f"{intercept:.4f}"]

    for feat_name, beta in coef_series.items():
        sign_str = "+" if beta >= 0 else "-"
        abs_beta = abs(float(beta))
        escaped_name = str(feat_name).replace("_", r"\_")
        latex_terms.append(f" {sign_str} {abs_beta:.4f} \\cdot \\text{{{escaped_name}}}")
        text_terms.append(f" {sign_str} {abs_beta:.4f} * [{feat_name}]")

    logit_latex_body = "".join(latex_terms)
    logit_text_body = "".join(text_terms)

    latex_logit = rf"Z = {logit_latex_body}"
    latex_prob_numeric = rf"P(Y=1) = \frac{{1}}{{1 + e^{{-\left({logit_latex_body}\right)}}}}"
    text_equation = f"Logit (Z) = {logit_text_body}  ==>  P(Y=1) = 1 / (1 + exp(-Z))"

    return {
        "latex_symbolic": latex_symbolic,
        "latex_logit": latex_logit,
        "latex_prob_numeric": latex_prob_numeric,
        "text_equation": text_equation,
    }


def train_logistic_model(
    X: pd.DataFrame,
    y: pd.Series,
    test_size: float = 0.30,
    random_state: int = 42,
    scale_continuous: bool = False,
    target_metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """
    Entrena un modelo de Regresión Logística Binaria siguiendo estrictamente ML Best Practices:
    1. División Entrenamiento (70%) / Prueba (30%) ANTES de ajustar cualquier imputador o escalador
       para prevenir fuga de datos (Data Leakage).
    2. Entrenamiento de LogisticRegression(max_iter=1000, random_state=random_state).
    3. Extracción de Intercepto (Beta_0), Coeficientes (Beta_i), Odds Ratios (exp(Beta_i)) e impacto porcentual.
    4. Construcción de las ecuaciones matemáticas en formato LaTeX y texto.
    5. Estadísticas descriptivas por variable en el set de entrenamiento para alimentar el simulador de escenarios.

    Parámetros:
        X: DataFrame de características numéricas/codificadas.
        y: Serie binaria (0 y 1).
        test_size: Proporción del conjunto de prueba (por defecto 0.30 = 30%).
        random_state: Semilla aleatoria para reproducibilidad.
        scale_continuous: Si True, estandariza variables continuas ajustando StandardScaler solo en X_train.
        target_metadata: Diccionario opcional devuelto por `validate_and_prepare_features`.

    Retorna:
        tuple[model_bundle | None, error_msg | None]
    """
    if X is None or y is None or X.empty or len(y) == 0:
        return None, "Los datos de entrada X o y están vacíos."

    if len(X) != len(y):
        return None, "El número de filas de X no coincide con la longitud de y."

    test_ratio = float(np.clip(test_size, 0.10, 0.50))

    try:
        # 1. Split train/test PRIMERO (Strict Featurization Ordering)
        try:
            X_train_raw, X_test_raw, y_train, y_test = train_test_split(
                X,
                y,
                test_size=test_ratio,
                random_state=random_state,
                stratify=y,
            )
        except ValueError:
            X_train_raw, X_test_raw, y_train, y_test = train_test_split(
                X,
                y,
                test_size=test_ratio,
                random_state=random_state,
            )

        feature_names = list(X.columns)

        # 2. Imputación preventiva ajustada SOLO en X_train (sin data leakage)
        imputer = SimpleImputer(strategy="median")
        X_train_imp = pd.DataFrame(
            imputer.fit_transform(X_train_raw),
            columns=feature_names,
            index=X_train_raw.index,
        )
        X_test_imp = pd.DataFrame(
            imputer.transform(X_test_raw),
            columns=feature_names,
            index=X_test_raw.index,
        )

        # 3. Escalado opcional ajustado SOLO en X_train
        scaler: StandardScaler | None = None
        continuous_to_scale: list[str] = []
        if scale_continuous:
            continuous_to_scale = [c for c in feature_names if X_train_imp[c].nunique() > 2]
            if continuous_to_scale:
                scaler = StandardScaler()
                X_train_imp[continuous_to_scale] = scaler.fit_transform(X_train_imp[continuous_to_scale])
                X_test_imp[continuous_to_scale] = scaler.transform(X_test_imp[continuous_to_scale])

        # 4. Entrenamiento del modelo de Regresión Logística
        model = LogisticRegression(max_iter=5000, random_state=random_state, solver="lbfgs")
        model.fit(X_train_imp, y_train)

        # 5. Extracción de parámetros matemáticos
        intercept = float(model.intercept_[0])
        coefs = model.coef_[0]
        coef_series = pd.Series(coefs, index=feature_names)
        odds_ratios = np.exp(np.clip(coefs, -20, 20))
        pct_change_odds = (odds_ratios - 1.0) * 100.0

        coef_df = pd.DataFrame(
            {
                "Variable": feature_names,
                "Coeficiente_Beta": np.round(coefs, 6),
                "Odds_Ratio": np.round(odds_ratios, 4),
                "Cambio_Porcentual_Odds": np.round(pct_change_odds, 2),
                "Impacto_Direccion": [
                    "Aumenta Probabilidad (Y=1)" if b > 0 else ("Reduce Probabilidad (Y=1)" if b < 0 else "Neutro")
                    for b in coefs
                ],
                "Importancia_Absoluta": np.round(np.abs(coefs), 6),
            }
        ).sort_values(by="Importancia_Absoluta", ascending=False).reset_index(drop=True)

        equations = _format_latex_equation(intercept, coef_series)

        # 6. Probabilidades predichas en Train y Test
        y_prob_train = model.predict_proba(X_train_imp)[:, 1]
        y_prob_test = model.predict_proba(X_test_imp)[:, 1]

        # 7. Estadísticas por variable (sobre X_train_raw antes de escalar para unidades reales)
        feature_stats: dict[str, dict[str, float | bool]] = {}
        for col in feature_names:
            col_s = X_train_raw[col].dropna()
            unique_vals = set(col_s.unique())
            is_bin = unique_vals.issubset({0, 1, 0.0, 1.0})
            feature_stats[col] = {
                "min": float(col_s.min()) if len(col_s) else 0.0,
                "max": float(col_s.max()) if len(col_s) else 1.0,
                "mean": float(col_s.mean()) if len(col_s) else 0.0,
                "median": float(col_s.median()) if len(col_s) else 0.0,
                "std": float(col_s.std()) if len(col_s) > 1 else 0.0,
                "p10": float(np.percentile(col_s, 10)) if len(col_s) else 0.0,
                "p25": float(np.percentile(col_s, 25)) if len(col_s) else 0.0,
                "p75": float(np.percentile(col_s, 75)) if len(col_s) else 0.0,
                "p90": float(np.percentile(col_s, 90)) if len(col_s) else 0.0,
                "mode": float(col_s.mode().iloc[0]) if not col_s.mode().empty else 0.0,
                "is_binary": bool(is_bin),
            }

        majority_class = int(y_train.mode().iloc[0])
        baseline_acc = float((y_test == majority_class).mean())

        target_map = (
            target_metadata.get("target_mapping", {0: "Clase 0", 1: "Clase 1"})
            if target_metadata
            else {0: "Clase 0", 1: "Clase 1"}
        )
        target_name = target_metadata.get("target_col", y.name or "Target") if target_metadata else (y.name or "Target")

        model_bundle: dict[str, Any] = {
            "model": model,
            "imputer": imputer,
            "scaler": scaler,
            "continuous_scaled_cols": continuous_to_scale,
            "scale_continuous": scale_continuous,
            "feature_names": feature_names,
            "intercept": intercept,
            "coefficients": coef_series.to_dict(),
            "odds_ratios": dict(zip(feature_names, odds_ratios)),
            "coef_df": coef_df,
            "equations": equations,
            "X_train": X_train_raw,
            "X_test": X_test_raw,
            "X_train_processed": X_train_imp,
            "X_test_processed": X_test_imp,
            "y_train": y_train,
            "y_test": y_test,
            "y_prob_train": y_prob_train,
            "y_prob_test": y_prob_test,
            "train_size": len(X_train_raw),
            "test_size": len(X_test_raw),
            "test_ratio": test_ratio,
            "feature_stats": feature_stats,
            "baseline_accuracy": baseline_acc,
            "target_col": target_name,
            "target_mapping": target_map,
        }
        return model_bundle, None

    except Exception as exc:
        return None, f"Error durante el entrenamiento del modelo de Regresión Logística: {exc}"


# ==============================================================================
# FASE 4: EVALUACIÓN DINÁMICA POR UMBRAL Y SIMULACIÓN DE 10+ ESCENARIOS
# ==============================================================================


def evaluate_with_threshold(model_bundle: dict[str, Any], threshold: float = 0.5) -> dict[str, Any]:
    """
    Evalúa el desempeño del modelo aplicando un umbral de decisión dinámico (`threshold`, por defecto 0.5).
    Recalcula las predicciones binarias, la Matriz de Confusión (TN, FP, FN, TP) y el Classification Report.

    Parámetros:
        model_bundle: Diccionario generado por `train_logistic_model`.
        threshold: Umbral de probabilidad en [0.01, 0.99] para clasificar como Y=1.

    Retorna:
        dict con todas las métricas, matriz de confusión y tablas listas para visualización.
    """
    if not model_bundle or "y_prob_test" not in model_bundle:
        raise ValueError("El paquete del modelo (`model_bundle`) es inválido o no contiene predicciones de prueba.")

    thr = float(np.clip(threshold, 0.01, 0.99))
    y_test = np.asarray(model_bundle["y_test"], dtype=int)
    y_prob_test = np.asarray(model_bundle["y_prob_test"], dtype=float)
    y_train = np.asarray(model_bundle["y_train"], dtype=int)
    y_prob_train = np.asarray(model_bundle["y_prob_train"], dtype=float)

    y_pred_test = (y_prob_test >= thr).astype(int)
    y_pred_train = (y_prob_train >= thr).astype(int)

    target_map = model_bundle.get("target_mapping", {0: "Clase 0", 1: "Clase 1"})
    label_0 = f"0 ({target_map.get(0, 'Negativo')})"
    label_1 = f"1 ({target_map.get(1, 'Positivo')})"

    cm = confusion_matrix(y_test, y_pred_test, labels=[0, 1])
    tn, fp, fn, tp = (int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1]))

    cm_df = pd.DataFrame(
        cm,
        index=[f"Real: {label_0}", f"Real: {label_1}"],
        columns=[f"Predicho: {label_0}", f"Predicho: {label_1}"],
    )

    report_dict = classification_report(
        y_test,
        y_pred_test,
        labels=[0, 1],
        target_names=[label_0, label_1],
        output_dict=True,
        zero_division=0,
    )

    report_rows = []
    for key in [label_0, label_1, "macro avg", "weighted avg"]:
        if key in report_dict:
            row_label = (
                "Promedio Macro"
                if key == "macro avg"
                else ("Promedio Ponderado" if key == "weighted avg" else key)
            )
            report_rows.append(
                {
                    "Clase / Métrica": row_label,
                    "Precisión (Precision)": round(float(report_dict[key]["precision"]), 4),
                    "Sensibilidad (Recall)": round(float(report_dict[key]["recall"]), 4),
                    "F1-Score": round(float(report_dict[key]["f1-score"]), 4),
                    "Soporte (Casos)": int(report_dict[key]["support"]),
                }
            )
    report_df = pd.DataFrame(report_rows)

    acc_test = float(accuracy_score(y_test, y_pred_test))
    acc_train = float(accuracy_score(y_train, y_pred_train))
    bal_acc = float(balanced_accuracy_score(y_test, y_pred_test))
    prec_pos = float(precision_score(y_test, y_pred_test, zero_division=0))
    rec_pos = float(recall_score(y_test, y_pred_test, zero_division=0))
    f1_pos = float(f1_score(y_test, y_pred_test, zero_division=0))
    specificity = float(tn / (tn + fp)) if (tn + fp) > 0 else 0.0

    try:
        roc_auc = float(roc_auc_score(y_test, y_prob_test))
        fpr, tpr, roc_thresholds = roc_curve(y_test, y_prob_test)
    except ValueError:
        roc_auc = 0.5
        fpr, tpr, roc_thresholds = np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.array([1.0, 0.0])

    try:
        pr_auc = float(average_precision_score(y_test, y_prob_test))
        pr_precision, pr_recall, pr_thresholds = precision_recall_curve(y_test, y_prob_test)
    except ValueError:
        pr_auc = 0.0
        pr_precision, pr_recall, pr_thresholds = np.array([1.0, 0.0]), np.array([0.0, 1.0]), np.array([0.5])

    return {
        "threshold": thr,
        "y_pred_test": y_pred_test,
        "y_pred_train": y_pred_train,
        "confusion_matrix": cm,
        "confusion_matrix_df": cm_df,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
        "accuracy_test": acc_test,
        "accuracy_train": acc_train,
        "balanced_accuracy": bal_acc,
        "precision": prec_pos,
        "recall": rec_pos,
        "specificity": specificity,
        "f1_score": f1_pos,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "classification_report_dict": report_dict,
        "classification_report_df": report_df,
        "roc_curve": {"fpr": fpr, "tpr": tpr, "thresholds": roc_thresholds},
        "pr_curve": {"precision": pr_precision, "recall": pr_recall, "thresholds": pr_thresholds},
    }


def get_base_scenarios_template(model_bundle: dict[str, Any], n_scenarios: int = 10) -> pd.DataFrame:
    """
    Construye un DataFrame plantilla con al menos 10 escenarios estratégicos preconfigurados
    basados en la distribución real de las variables de entrenamiento y en la dirección de los coeficientes.
    Ideal para presentarse en un `st.data_editor` editable en la interfaz antes de simular.
    """
    feature_names: list[str] = model_bundle["feature_names"]
    f_stats: dict[str, dict[str, Any]] = model_bundle["feature_stats"]
    coefs: dict[str, float] = model_bundle["coefficients"]
    n_total = max(int(n_scenarios), 10)

    sorted_pos = sorted(feature_names, key=lambda c: coefs.get(c, 0.0), reverse=True)
    sorted_neg = sorted(feature_names, key=lambda c: coefs.get(c, 0.0))
    top_pos_var = sorted_pos[0] if sorted_pos else feature_names[0]
    top_neg_var = sorted_neg[0] if sorted_neg else feature_names[-1]

    def _build_profile(mode: str, custom_idx: int = 0) -> dict[str, Any]:
        row: dict[str, Any] = {}
        for col in feature_names:
            st = f_stats[col]
            is_bin = bool(st["is_binary"])
            beta = float(coefs.get(col, 0.0))

            if mode == "promedio":
                val = st["mode"] if is_bin else st["mean"]
            elif mode == "mediana":
                val = st["mode"] if is_bin else st["median"]
            elif mode == "bajo_riesgo_p10":
                if is_bin:
                    val = 0.0 if beta >= 0 else 1.0
                else:
                    val = st["p10"] if beta >= 0 else st["p90"]
            elif mode == "moderado_bajo_p25":
                if is_bin:
                    val = 0.0 if beta >= 0 else 1.0
                else:
                    val = st["p25"] if beta >= 0 else st["p75"]
            elif mode == "moderado_alto_p75":
                if is_bin:
                    val = 1.0 if beta >= 0 else 0.0
                else:
                    val = st["p75"] if beta >= 0 else st["p25"]
            elif mode == "alto_riesgo_p90":
                if is_bin:
                    val = 1.0 if beta >= 0 else 0.0
                else:
                    val = st["p90"] if beta >= 0 else st["p10"]
            elif mode == "extremo_max_prob":
                if is_bin:
                    val = 1.0 if beta >= 0 else 0.0
                else:
                    val = st["max"] if beta >= 0 else st["min"]
            elif mode == "extremo_min_prob":
                if is_bin:
                    val = 0.0 if beta >= 0 else 1.0
                else:
                    val = st["min"] if beta >= 0 else st["max"]
            elif mode == "shock_driver_positivo":
                if col == top_pos_var:
                    val = 1.0 if is_bin else st["p90"]
                else:
                    val = st["mode"] if is_bin else st["median"]
            elif mode == "shock_driver_protector":
                if col == top_neg_var:
                    val = 1.0 if is_bin else st["p90"]
                else:
                    val = st["mode"] if is_bin else st["median"]
            else:
                alpha = ((custom_idx % 9) + 1) / 10.0
                if is_bin:
                    val = 1.0 if alpha > 0.5 else 0.0
                else:
                    val = st["min"] + alpha * (st["max"] - st["min"])

            row[col] = round(float(val), 4) if not is_bin else float(int(round(val)))
        return row

    preset_definitions = [
        ("Escenario 1: Base (Promedio Histórico)", "promedio"),
        ("Escenario 2: Típico (Mediana Operativa)", "mediana"),
        ("Escenario 3: Conservador / Baja Exposición (P10)", "bajo_riesgo_p10"),
        ("Escenario 4: Favorable Moderado (P25)", "moderado_bajo_p25"),
        ("Escenario 5: Presión Moderada-Alta (P75)", "moderado_alto_p75"),
        ("Escenario 6: Alta Exposición / Estrés (P90)", "alto_riesgo_p90"),
        (f"Escenario 7: Sensibilidad Driver Impulsor ({top_pos_var})", "shock_driver_positivo"),
        (f"Escenario 8: Sensibilidad Factor Amortiguador ({top_neg_var})", "shock_driver_protector"),
        ("Escenario 9: Caso Crítico (Máxima Probabilidad Y=1)", "extremo_max_prob"),
        ("Escenario 10: Caso Óptimo (Mínima Probabilidad Y=1)", "extremo_min_prob"),
    ]

    records = []
    for idx in range(n_total):
        if idx < len(preset_definitions):
            scen_name, mode = preset_definitions[idx]
            profile = _build_profile(mode, idx)
        else:
            scen_name = f"Escenario {idx + 1}: Simulación Personalizada #{idx - 9}"
            profile = _build_profile("custom", idx)
        row_data = {"Escenario": scen_name}
        row_data.update(profile)
        records.append(row_data)

    return pd.DataFrame(records)


def generate_simulation_scenarios(
    model_bundle: dict[str, Any],
    n_scenarios: int = 10,
    custom_scenarios_df: pd.DataFrame | None = None,
    threshold: float = 0.5,
) -> pd.DataFrame:
    """
    Simula al menos 10 escenarios distintos aplicando el modelo de Regresión Logística entrenado
    y el umbral de decisión dinámico (`threshold`).

    Si `custom_scenarios_df` es proporcionado (por ejemplo, editado por el usuario en Streamlit),
    evalúa las filas proporcionadas; de lo contrario, genera los `n_scenarios` (>= 10) escenarios base.

    Retorna:
        pd.DataFrame con los valores de entrada de cada escenario, `Logit_Z`, `Probabilidad_Y1`,
        `Porcentaje_Probabilidad`, `Umbral_Aplicado`, `Prediccion_Binaria`, `Clasificacion_Etiqueta`
        y `Nivel_Riesgo`.
    """
    if not model_bundle or "model" not in model_bundle:
        raise ValueError("El paquete del modelo (`model_bundle`) es inválido.")

    thr = float(np.clip(threshold, 0.01, 0.99))
    feature_names: list[str] = model_bundle["feature_names"]
    model: LogisticRegression = model_bundle["model"]
    imputer: SimpleImputer = model_bundle["imputer"]
    scaler: StandardScaler | None = model_bundle.get("scaler")
    scaled_cols: list[str] = model_bundle.get("continuous_scaled_cols", [])
    target_map: dict[int, str] = model_bundle.get("target_mapping", {0: "Clase 0", 1: "Clase 1"})

    if custom_scenarios_df is not None and not custom_scenarios_df.empty:
        scen_df = custom_scenarios_df.copy().reset_index(drop=True)
        if len(scen_df) < 10 and n_scenarios >= 10:
            missing_n = 10 - len(scen_df)
            extra_df = get_base_scenarios_template(model_bundle, n_scenarios=10).tail(missing_n)
            scen_df = pd.concat([scen_df, extra_df], ignore_index=True)
    else:
        scen_df = get_base_scenarios_template(model_bundle, n_scenarios=max(10, int(n_scenarios)))

    if "Escenario" not in scen_df.columns:
        scen_df.insert(0, "Escenario", [f"Escenario {i + 1}" for i in range(len(scen_df))])

    for col in feature_names:
        if col not in scen_df.columns:
            scen_df[col] = model_bundle["feature_stats"][col]["median"]
        scen_df[col] = pd.to_numeric(scen_df[col], errors="coerce")

    X_scen_raw = scen_df[feature_names].copy()
    X_scen_imp = pd.DataFrame(imputer.transform(X_scen_raw), columns=feature_names)

    if scaler is not None and scaled_cols:
        X_scen_imp[scaled_cols] = scaler.transform(X_scen_imp[scaled_cols])

    logits = model.decision_function(X_scen_imp)
    probs = model.predict_proba(X_scen_imp)[:, 1]
    preds = (probs >= thr).astype(int)

    def _risk_tier(p: float) -> str:
        if p < 0.25:
            return "Bajo"
        if p < 0.50:
            return "Moderado"
        if p < 0.75:
            return "Alto"
        return "Crítico"

    result_df = scen_df[["Escenario"] + feature_names].copy()
    result_df["Logit_Z"] = np.round(logits, 4)
    result_df["Probabilidad_Y1"] = np.round(probs, 4)
    result_df["Porcentaje_Probabilidad"] = np.round(probs * 100.0, 2)
    result_df["Umbral_Aplicado"] = round(thr, 2)
    result_df["Prediccion_Binaria"] = preds
    result_df["Clasificacion_Etiqueta"] = [
        f"1 ({target_map.get(1, 'Positivo')})" if p == 1 else f"0 ({target_map.get(0, 'Negativo')})"
        for p in preds
    ]
    result_df["Nivel_Riesgo"] = [_risk_tier(float(p)) for p in probs]

    return result_df


# ==============================================================================
# FASE 5: VALOR DE NEGOCIO (ROL ANALISTA DE NEGOCIOS)
# ==============================================================================

_SECTOR_CONTEXT: dict[str, dict[str, str]] = {
    "Finanzas y Banca": {
        "evento_objetivo": "riesgo de impago (default), mora crediticia o deserción de productos financieros",
        "foco_marketing": "segmentación por perfil de riesgo-rentabilidad y ofertas preaprobadas de bajo riesgo",
        "foco_finanzas": "optimización de provisiones de cartera, pérdidas esperadas (Expected Credit Loss) y margen financiero",
        "foco_ventas": "colocación consultiva de créditos y venta cruzada en clientes con alta probabilidad de cumplimiento",
        "foco_direccion": "gobierno de riesgo crediticio, solvencia patrimonial y crecimiento sostenible de cartera",
    },
    "Retail y E-commerce": {
        "evento_objetivo": "fuga de clientes (churn), abandono de recompra o conversión de campañas",
        "foco_marketing": "automatización de campañas de retención hiperpersonalizadas y optimización del CAC/LTV",
        "foco_finanzas": "protección del margen bruto, control del gasto en descuentos y flujo de caja por inventario",
        "foco_ventas": "incentivos de frecuencia de compra, membresías VIP y recuperación de carritos/clientes inactivos",
        "foco_direccion": "expansión del Customer Lifetime Value (LTV) y experiencia omnicanal rentable",
    },
    "Salud y Farmacéutica": {
        "evento_objetivo": "reingreso hospitalario temprano, falta de adherencia terapéutica o complicación clínica",
        "foco_marketing": "programas de educación al paciente, recordatorios multicanal y relacionamiento con médicos",
        "foco_finanzas": "reducción de costos por reingresos evitables, eficiencia cama/día y sostenibilidad de pólizas",
        "foco_ventas": "convenios institucionales basados en resultados en salud (Value-Based Healthcare)",
        "foco_direccion": "calidad asistencial, seguridad del paciente y acreditación clínica de excelencia",
    },
    "Telecomunicaciones": {
        "evento_objetivo": "cancelación de suscripción (churn), portabilidad numérica o degradación de ARPU",
        "foco_marketing": "ofertas convergentes (empaquetamiento fijo-móvil) y fidelización preventiva antes del vencimiento",
        "foco_finanzas": "estabilidad del ingreso recurrente (ARPU), amortización de costos de instalación y subsidio de equipos",
        "foco_ventas": "migración de contratos mes a mes hacia planes anuales y upselling a fibra óptica",
        "foco_direccion": "liderazgo en retención neta de suscriptores y retorno sobre inversión en infraestructura de red",
    },
    "Manufactura e Industria": {
        "evento_objetivo": "falla crítica de maquinaria, paro no programado de línea o lote defectuoso",
        "foco_marketing": "posicionamiento de confiabilidad de entregas (OTIF) y contratos de nivel de servicio industrial",
        "foco_finanzas": "minimización del costo por hora de paro de planta, CAPEX/OPEX de mantenimiento y merma",
        "foco_ventas": "cumplimiento estricto de tiempos de entrega y disponibilidad de inventario comprometido",
        "foco_direccion": "excelencia operacional (OEE), mantenimiento predictivo 4.0 y continuidad de cadena de suministro",
    },
    "Tecnología y SaaS": {
        "evento_objetivo": "cancelación de licencias (Logo/MRR Churn) o baja adopción de producto",
        "foco_marketing": "campañas de Product-Led Growth (PLG), activación in-app y casos de uso por vertical",
        "foco_finanzas": "protección del Net Dollar Retention (NDR), eficiencia del Burn Rate y relación LTV/CAC",
        "foco_ventas": "Customer Success proactivo en renovaciones, expansión de asientos y contratos multianuales",
        "foco_direccion": "escalabilidad recurrente (ARR), reducción del Churn estructural y valoración de la compañía",
    },
    "Educación": {
        "evento_objetivo": "deserción estudiantil entre periodos académicos o rezago en el desempeño",
        "foco_marketing": "comunicación temprana con familias/estudiantes y fortalecimiento de comunidad estudiantil",
        "foco_finanzas": "aseguramiento de ingresos por matrículas, asignación eficiente de becas y sostenibilidad presupuestal",
        "foco_ventas": "acompañamiento en rematrícula, orientación vocacional y programas de nivelación",
        "foco_direccion": "tasas de graduación oportuna, prestigio académico e impacto social medible",
    },
    "Energía y Servicios Públicos": {
        "evento_objetivo": "mora prolongada, suspensión de suministro o anomalías críticas de consumo",
        "foco_marketing": "programas de eficiencia energética, educación en consumo responsable y canales de pago digitales",
        "foco_finanzas": "recuperación de cartera vencida, reducción de pérdidas no técnicas y flujo de caja regulado",
        "foco_ventas": "acuerdos de pago flexibles, domiciliación bancaria y servicios de valor agregado (medición inteligente)",
        "foco_direccion": "continuidad del servicio público, transición energética y sostenibilidad financiera operativa",
    },
}


def generate_business_recommendations(
    model_bundle: dict[str, Any],
    eval_metrics: dict[str, Any],
    sector: str,
) -> dict[str, Any]:
    """
    Genera un informe estratégico y cuantitativo de recomendaciones de negocio adaptado al sector económico,
    a los coeficientes Beta / Odds Ratios del modelo y a las métricas del umbral de decisión actual.

    Devuelve recomendaciones estructuradas para las 4 áreas clave:
        1. 'Marketing'
        3. 'Finanzas'
        3. 'Ventas'
        4. 'Alta Dirección'
    """
    if not model_bundle or not eval_metrics:
        raise ValueError("Se requieren `model_bundle` y `eval_metrics` válidos para generar recomendaciones.")

    sec_info = _SECTOR_CONTEXT.get(sector, _SECTOR_CONTEXT["Finanzas y Banca"])
    coef_df: pd.DataFrame = model_bundle["coef_df"]
    target_col = model_bundle.get("target_col", "Target")
    target_map = model_bundle.get("target_mapping", {0: "0", 1: "1"})
    pos_label = f"1 ({target_map.get(1, 'Positivo')})"

    thr = float(eval_metrics.get("threshold", 0.5))
    acc = float(eval_metrics.get("accuracy_test", 0.0)) * 100.0
    prec = float(eval_metrics.get("precision", 0.0)) * 100.0
    rec = float(eval_metrics.get("recall", 0.0)) * 100.0
    f1 = float(eval_metrics.get("f1_score", 0.0)) * 100.0
    roc_auc = float(eval_metrics.get("roc_auc", 0.5)) * 100.0
    tp = int(eval_metrics.get("tp", 0))
    fp = int(eval_metrics.get("fp", 0))
    fn = int(eval_metrics.get("fn", 0))
    tn = int(eval_metrics.get("tn", 0))

    pos_drivers_df = coef_df[coef_df["Coeficiente_Beta"] > 0].sort_values(by="Coeficiente_Beta", ascending=False)
    neg_drivers_df = coef_df[coef_df["Coeficiente_Beta"] < 0].sort_values(by="Coeficiente_Beta", ascending=True)

    if not pos_drivers_df.empty:
        top_pos_row = pos_drivers_df.iloc[0]
        top_pos_name = str(top_pos_row["Variable"])
        top_pos_beta = float(top_pos_row["Coeficiente_Beta"])
        top_pos_or = float(top_pos_row["Odds_Ratio"])
        top_pos_desc = f"**{top_pos_name}** ($\\beta = {top_pos_beta:+.4f}$, Odds Ratio = ${top_pos_or:.2f}x$)"
    else:
        top_pos_name = str(coef_df.iloc[0]["Variable"])
        top_pos_beta = float(coef_df.iloc[0]["Coeficiente_Beta"])
        top_pos_or = float(coef_df.iloc[0]["Odds_Ratio"])
        top_pos_desc = f"**{top_pos_name}** ($\\beta = {top_pos_beta:+.4f}$, Odds Ratio = ${top_pos_or:.2f}x$)"

    if not neg_drivers_df.empty:
        top_neg_row = neg_drivers_df.iloc[0]
        top_neg_name = str(top_neg_row["Variable"])
        top_neg_beta = float(top_neg_row["Coeficiente_Beta"])
        top_neg_or = float(top_neg_row["Odds_Ratio"])
        top_neg_desc = f"**{top_neg_name}** ($\\beta = {top_neg_beta:+.4f}$, Odds Ratio = ${top_neg_or:.2f}x$)"
    else:
        top_neg_name = str(coef_df.iloc[-1]["Variable"])
        top_neg_beta = float(coef_df.iloc[-1]["Coeficiente_Beta"])
        top_neg_or = float(coef_df.iloc[-1]["Odds_Ratio"])
        top_neg_desc = f"**{top_neg_name}** ($\\beta = {top_neg_beta:+.4f}$, Odds Ratio = ${top_neg_or:.2f}x$)"

    if thr < 0.40:
        postura_umbral = "Preventiva / Alta Sensibilidad (Captura máxima de casos positivos)"
        impacto_umbral = (
            f"Con un umbral bajo ({thr:.2f}), el modelo prioriza detectar la mayor cantidad posible de casos '{pos_label}' "
            f"(Recall = {rec:.1f}%, {tp} verdaderos positivos), asumiendo un mayor volumen de alertas preventivas ({fp} falsos positivos)."
        )
    elif thr > 0.60:
        postura_umbral = "Conservadora / Alta Precisión (Focalización estricta de recursos)"
        impacto_umbral = (
            f"Con un umbral exigente ({thr:.2f}), el modelo interviene únicamente cuando la certeza de '{pos_label}' es alta "
            f"(Precisión = {prec:.1f}%, solo {fp} falsos positivos), aunque deja escapar {fn} casos reales (falsos negativos)."
        )
    else:
        postura_umbral = "Equilibrada / Balance Costo-Beneficio (Estándar Operativo)"
        impacto_umbral = (
            f"Con un umbral balanceado ({thr:.2f}), el modelo logra un equilibrio entre Precisión ({prec:.1f}%) y Sensibilidad/Recall ({rec:.1f}%), "
            f"identificando {tp} casos reales con {fp} falsas alarmas y {fn} casos no detectados."
        )

    resumen_ejecutivo = (
        f"En el sector de **{sector}**, el modelo de Regresión Logística para predecir **{target_col}** (`{pos_label}`) "
        f"alcanza un poder discriminante **ROC-AUC de {roc_auc:.1f}%** y una exactitud (Accuracy) de **{acc:.1f}%** en el conjunto de prueba (30%). "
        f"El principal factor acelerador del evento es {top_pos_desc}, mientras que el principal factor amortiguador/protector es {top_neg_desc}."
    )

    areas: dict[str, dict[str, Any]] = {
        "Marketing": {
            "area": "Marketing",
            "icono": "📣",
            "titulo": f"Estrategia de Marketing Data-Driven para {sector}",
            "enfoque_sector": sec_info["foco_marketing"],
            "diagnostico_modelo": (
                f"La variable {top_pos_desc} incrementa significativamente la propensión hacia `{pos_label}`, "
                f"mientras que {top_neg_desc} actúa como ancla de estabilidad. Al umbral actual de **{thr:.2f}**, "
                f"las campañas focalizadas tienen una efectividad esperada (Precisión) del **{prec:.1f}%**."
            ),
            "estrategias_accionables": [
                f"**Micro-segmentación por Probabilidad Estimada:** Dividir la base en 3 niveles según $P(Y=1)$: "
                f"Crítico ($\\ge 0.75$), En Riesgo ($[{thr:.2f}, 0.75)$) y Saludable ($< {thr:.2f}$), asignando presupuestos diferenciados.",
                f"**Intervención directa sobre `{top_pos_name}`:** Diseñar comunicaciones automatizadas (triggers) cuando `{top_pos_name}` "
                f"supere su mediana operativa, ya que su Odds Ratio de **{top_pos_or:.2f}x** lo convierte en el principal detonante de `{target_col}`.",
                f"**Potenciación del factor `{top_neg_name}`:** Incentivar mediante programas de fidelización el atributo `{top_neg_name}`, "
                f"que reduce las probabilidades relativas del evento a **{top_neg_or:.2f}x**.",
                f"**Optimización del gasto en campañas (Control de {fp} Falsos Positivos):** Utilizar incentivos de bajo costo (notificaciones in-app/email) "
                f"en probabilidades cercanas a {thr:.2f} y reservar beneficios económicos solo para probabilidades $> 0.70$.",
            ],
            "kpis_sugeridos": [
                f"Tasa de Conversión / Retención sobre el segmento predicho como `{pos_label}`",
                f"Reducción del CAC / Costo de Retención por campaña focalizada (Meta: mejorar Precisión actual de {prec:.1f}%)",
                f"Índice de adopción del factor protector `{top_neg_name}`",
            ],
            "impacto_esperado": (
                f"Incremento de la eficiencia de inversión publicitaria/retención al concentrar recursos en el {rec:.1f}% de casos reales detectados."
            ),
        },
        "Finanzas": {
            "area": "Finanzas",
            "icono": "💰",
            "titulo": f"Optimización Financiera y Control de Riesgo en {sector}",
            "enfoque_sector": sec_info["foco_finanzas"],
            "diagnostico_modelo": (
                f"La Matriz de Confusión al umbral **{thr:.2f}** registra **{tp} aciertos positivos (TP)**, **{tn} aciertos negativos (TN)**, "
                f"**{fp} Falsos Positivos (costo de intervención innecesaria)** y **{fn} Falsos Negativos (costo de omisión/pérdida directa)**."
            ),
            "estrategias_accionables": [
                f"**Valoración Económica de la Matriz de Confusión:** Cuantificar el costo unitario de un Falso Negativo ({fn} casos omitidos de `{target_col}`) "
                f"frente al costo operativo de un Falso Positivo ({fp} casos). Si el costo de omisión supera 3x el de intervención, reducir el umbral por debajo de {thr:.2f}.",
                f"**Presupuesto y Provisiones Basadas en Probabilidad Esperada:** Calcular la exposición financiera ponderando el valor monetario de cada registro "
                f"por su probabilidad individual $P(Y=1)$ en lugar de usar promedios estáticos.",
                f"**Auditoría de Sensibilidad en `{top_pos_name}`:** Incorporar `{top_pos_name}` como indicador adelantado (Leading Indicator) en el flujo de caja "
                f"y estrés financiero trimestral.",
                f"**Retorno sobre la Intervención (ROI del Modelo):** Con un F1-Score de **{f1:.1f}%** y ROC-AUC de **{roc_auc:.1f}%**, el modelo supera la asignación aleatoria "
                f"y permite liberar capital inmovilizado en los **{tn}** casos clasificados con seguridad como negativos.",
            ],
            "kpis_sugeridos": [
                f"Ahorro Neto por Prevención de `{target_col}` vs. Costo de Falsos Positivos ({fp} casos)",
                "Margen Operativo Protegido ponderado por probabilidad $P(Y=1)$",
                f"Reducción porcentual de pérdidas por Falsos Negativos (actualmente {fn} en set de prueba)",
            ],
            "impacto_esperado": (
                "Asignación óptima de capital de trabajo y reducción de pérdidas inesperadas mediante cuantificación probabilística."
            ),
        },
        "Ventas": {
            "area": "Ventas",
            "icono": "🤝",
            "titulo": f"Ejecución Comercial y Gestión de Cuentas en {sector}",
            "enfoque_sector": sec_info["foco_ventas"],
            "diagnostico_modelo": (
                f"El equipo comercial cuenta ahora con un score probabilístico objetivo para priorizar su gestión diaria. "
                f"Al umbral **{thr:.2f}**, el modelo identifica el **{rec:.1f}%** de los casos reales de `{pos_label}`."
            ),
            "estrategias_accionables": [
                f"**Priorización Diaria del Pipeline Comercial:** Integrar la probabilidad $P(Y=1)$ en el CRM para que los ejecutivos atiendan primero "
                f"los registros que superan el umbral del **{thr * 100:.0f}%** y presentan altos valores en `{top_pos_name}`.",
                f"**Argumentario Comercial Basado en `{top_neg_name}`:** Estructurar las propuestas comerciales potenciando `{top_neg_name}`, "
                f"dado que estadísticamente desplaza el Logit ($Z$) hacia la zona segura ($\\beta = {top_neg_beta:+.4f}$).",
                f"**Protocolo Diferenciado según Nivel de Riesgo:** Para cuentas en nivel *Moderado/Alto* ($P \\ge {thr:.2f}$), activar contacto consultivo inmediato; "
                f"para cuentas en nivel *Bajo* ($P < 0.25$), habilitar venta cruzada (cross-selling / upselling) automatizada.",
                f"**Calibración de Esfuerzo Comercial:** Evitar desgastar a la fuerza de ventas en cuentas con baja probabilidad o reducir el umbral si el equipo "
                f"tiene capacidad instalada para absorber más de los {tp + fp} casos actualmente alertados.",
            ],
            "kpis_sugeridos": [
                f"Tasa de Efectividad Comercial en cuentas con $P(Y=1) \\ge {thr:.2f}$",
                "Tiempo de respuesta (SLA) ante alertas tempranas generadas por el modelo",
                f"Volumen de cuentas migradas hacia condiciones favorables en `{top_neg_name}`",
            ],
            "impacto_esperado": (
                "Mayor productividad por ejecutivo comercial y focalización quirúrgica en las cuentas que definen la meta del periodo."
            ),
        },
        "Alta Dirección": {
            "area": "Alta Dirección",
            "icono": "🏛️",
            "titulo": f"Gobierno Corporativo y Hoja de Ruta Ejecutiva en {sector}",
            "enfoque_sector": sec_info["foco_direccion"],
            "diagnostico_modelo": (
                f"Postura estratégica actual: **{postura_umbral}**. {impacto_umbral}"
            ),
            "estrategias_accionables": [
                f"**Institucionalización de la Toma de Decisiones Analítica:** Adoptar este modelo de Regresión Logística (ROC-AUC **{roc_auc:.1f}%**) "
                f"como estándar corporativo para anticipar {sec_info['evento_objetivo']}.",
                f"**Política Corporativa de Umbral Dinámico (`Threshold = {thr:.2f}`):** Establecer en comité directivo el umbral oficial según el apetito de riesgo "
                f"del trimestre: disminuirlo en periodos de defensa de mercado (maximizar Recall) o incrementarlo en periodos de austeridad (maximizar Precisión).",
                f"**Rediseño Estructural de Procesos en torno a `{top_pos_name}` y `{top_neg_name}`:** Alinear los OKRs de Operaciones, Producto y Comercial "
                f"para mitigar estructuralmente `{top_pos_name}` y escalar `{top_neg_name}` en toda la organización.",
                "**Gobierno del Modelo y Reentrenamiento Continuo:** Monitorear trimestralmente el desempeño sobre nuevos datos (Data Drift) para mantener "
                f"la ventaja competitiva sobre la línea base ({model_bundle.get('baseline_accuracy', 0.5) * 100:.1f}%).",
            ],
            "kpis_sugeridos": [
                f"Evolución trimestral de la tasa global de `{target_col}` en la organización",
                f"ROC-AUC y Estabilidad del Modelo en Producción (Referencia actual: {roc_auc:.1f}%)",
                "EBITDA / Impacto Estratégico Neto atribuible a decisiones guiadas por el simulador",
            ],
            "impacto_esperado": (
                "Transición de una gestión reactiva a una dirección predictiva respaldada por evidencia estadística auditable."
            ),
        },
    }

    return {
        "sector": sector,
        "target_col": target_col,
        "resumen_ejecutivo": resumen_ejecutivo,
        "postura_umbral": postura_umbral,
        "impacto_umbral": impacto_umbral,
        "top_positive_driver": {
            "variable": top_pos_name,
            "beta": top_pos_beta,
            "odds_ratio": top_pos_or,
            "descripcion": top_pos_desc,
        },
        "top_negative_driver": {
            "variable": top_neg_name,
            "beta": top_neg_beta,
            "odds_ratio": top_neg_or,
            "descripcion": top_neg_desc,
        },
        "areas": areas,
        "Marketing": areas["Marketing"],
        "Finanzas": areas["Finanzas"],
        "Ventas": areas["Ventas"],
        "Alta Dirección": areas["Alta Dirección"],
    }


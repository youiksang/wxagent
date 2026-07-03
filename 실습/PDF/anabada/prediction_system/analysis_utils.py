"""데이터 업로드, 전처리, 탐색적 분석, 모델 검증 그래프 유틸리티."""

from __future__ import annotations

import os
import platform
import uuid
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib import font_manager

ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls"}


def setup_korean_font() -> str:
    """운영체제별 한글 matplotlib 폰트 설정."""
    system = platform.system()
    candidates: List[str] = []

    if system == "Windows":
        candidates = ["Malgun Gothic", "맑은 고딕", "NanumGothic"]
    elif system == "Darwin":
        candidates = ["AppleGothic", "NanumGothic", "Arial Unicode MS"]
    else:
        candidates = ["NanumGothic", "Nanum Gothic", "DejaVu Sans"]

    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = "DejaVu Sans"
    for name in candidates:
        if name in available:
            selected = name
            break

    plt.rcParams["font.family"] = selected
    plt.rcParams["axes.unicode_minus"] = False
    sns.set_theme(style="whitegrid", font=selected)
    return selected


def allowed_file(filename: str) -> bool:
    """허용된 확장자인지 확인."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def get_file_extension(filename: str) -> str:
    """파일 확장자 반환."""
    return filename.rsplit(".", 1)[1].lower()


def save_dataframe(df: pd.DataFrame, path: str) -> None:
    """DataFrame을 pickle 파일로 저장."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    joblib.dump(df, path)


def load_dataframe(path: str) -> pd.DataFrame:
    """pickle 파일에서 DataFrame 로드."""
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"데이터 파일을 찾을 수 없습니다: {path}")
    return joblib.load(path)


def read_data_file(filepath: str, extension: str) -> pd.DataFrame:
    """CSV 또는 Excel 파일을 DataFrame으로 읽기."""
    ext = extension.lower()
    if ext == "csv":
        df = pd.read_csv(filepath, encoding="utf-8")
    elif ext in ("xlsx", "xls"):
        df = pd.read_excel(filepath)
    else:
        raise ValueError("지원하지 않는 파일 형식입니다. CSV 또는 Excel 파일만 업로드할 수 있습니다.")

    if df.empty:
        raise ValueError("빈 데이터 파일입니다. 데이터가 포함된 파일을 업로드해주세요.")

    return df


def dataframe_to_html_head(df: pd.DataFrame, n: int = 10) -> str:
    """DataFrame 상위 n행 HTML 테이블."""
    return df.head(n).to_html(classes="table table-striped table-hover table-sm", index=False)


def dataframe_to_html_describe(df: pd.DataFrame) -> str:
    """describe(include='all') HTML 테이블."""
    return df.describe(include="all").transpose().to_html(classes="table table-bordered table-sm")


def get_numeric_columns(df: pd.DataFrame, columns: Optional[List[str]] = None) -> List[str]:
    """숫자형 컬럼 목록."""
    target = columns if columns else df.columns.tolist()
    return [col for col in target if col in df.columns and pd.api.types.is_numeric_dtype(df[col])]


def get_categorical_columns(df: pd.DataFrame, columns: Optional[List[str]] = None) -> List[str]:
    """범주형(비숫자) 컬럼 목록."""
    target = columns if columns else df.columns.tolist()
    return [col for col in target if col in df.columns and not pd.api.types.is_numeric_dtype(df[col])]


def process_missing_values(
    df: pd.DataFrame,
    analysis_columns: List[str],
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """선택 변수 기준 결측치 행 제거."""
    missing_cols = [col for col in analysis_columns if col not in df.columns]
    if missing_cols:
        raise ValueError(f"선택한 변수가 데이터에 존재하지 않습니다: {', '.join(missing_cols)}")

    subset = df[analysis_columns]
    rows_before = len(df)
    missing_mask = subset.isnull().any(axis=1)
    missing_rows = int(missing_mask.sum())
    cleaned = df.loc[~missing_mask].copy()
    rows_after = len(cleaned)

    stats = {
        "rows_before": rows_before,
        "missing_rows": missing_rows,
        "removed_rows": missing_rows,
        "rows_after": rows_after,
    }
    return cleaned, stats


def detect_outliers(
    df: pd.DataFrame,
    analysis_columns: List[str],
) -> List[Dict[str, Any]]:
    """3-sigma 기준 이상치 탐색."""
    numeric_cols = get_numeric_columns(df, analysis_columns)
    results: List[Dict[str, Any]] = []

    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        mean_val = float(series.mean())
        std_val = float(series.std())
        if std_val == 0 or np.isnan(std_val):
            continue

        lower = mean_val - 3 * std_val
        upper = mean_val + 3 * std_val
        outlier_mask = (df[col] < lower) | (df[col] > upper)
        outlier_count = int(outlier_mask.sum())

        results.append(
            {
                "variable": col,
                "mean": round(mean_val, 4),
                "std": round(std_val, 4),
                "lower": round(lower, 4),
                "upper": round(upper, 4),
                "outlier_count": outlier_count,
            }
        )

    return results


def remove_outliers(
    df: pd.DataFrame,
    variables: List[str],
    detection_results: List[Dict[str, Any]],
) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """선택 변수 기준 이상치 행 제거."""
    if not variables:
        return df.copy(), {
            "rows_before": len(df),
            "removed_rows": 0,
            "rows_after": len(df),
        }

    detection_map = {item["variable"]: item for item in detection_results}
    outlier_mask = pd.Series(False, index=df.index)

    for var in variables:
        if var not in detection_map or var not in df.columns:
            continue
        info = detection_map[var]
        var_mask = (df[var] < info["lower"]) | (df[var] > info["upper"])
        outlier_mask = outlier_mask | var_mask

    rows_before = len(df)
    cleaned = df.loc[~outlier_mask].copy()
    removed_rows = int(outlier_mask.sum())

    return cleaned, {
        "rows_before": rows_before,
        "removed_rows": removed_rows,
        "rows_after": len(cleaned),
    }


def build_plot_filename(session_id: str, prefix: str, extension: str = "png") -> str:
    """그래프 파일명 생성."""
    return f"{session_id}_{prefix}_{uuid.uuid4().hex[:8]}.{extension}"


def save_figure(fig: plt.Figure, plots_dir: str, filename: str) -> str:
    """matplotlib Figure 저장."""
    os.makedirs(plots_dir, exist_ok=True)
    filepath = os.path.join(plots_dir, filename)
    fig.savefig(filepath, bbox_inches="tight", dpi=120)
    plt.close(fig)
    return filepath


def create_histogram(
    df: pd.DataFrame,
    variable: str,
    plots_dir: str,
    session_id: str,
) -> Tuple[str, str]:
    """히스토그램 + KDE 생성."""
    setup_korean_font()
    if variable not in df.columns:
        raise ValueError(f"변수 '{variable}'가 데이터에 존재하지 않습니다.")
    if not pd.api.types.is_numeric_dtype(df[variable]):
        raise ValueError("히스토그램은 숫자형 변수만 선택할 수 있습니다.")

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.histplot(df[variable].dropna(), kde=True, ax=ax, color="#7ec8a3", edgecolor="white")
    ax.set_title(f"{variable} 히스토그램", fontsize=14)
    ax.set_xlabel(variable)
    ax.set_ylabel("빈도")

    filename = build_plot_filename(session_id, "histogram")
    filepath = save_figure(fig, plots_dir, filename)
    return filepath, filename


def create_scatter_plot(
    df: pd.DataFrame,
    variables: List[str],
    plots_dir: str,
    session_id: str,
) -> Tuple[str, str]:
    """산점도 또는 pairplot 생성."""
    setup_korean_font()
    if len(variables) < 2:
        raise ValueError("산점도 분석을 위해서는 최소 2개 이상의 숫자형 변수를 선택해야 합니다.")

    for var in variables:
        if var not in df.columns:
            raise ValueError(f"변수 '{var}'가 데이터에 존재하지 않습니다.")
        if not pd.api.types.is_numeric_dtype(df[var]):
            raise ValueError(f"변수 '{var}'는 숫자형이 아닙니다.")

    plot_df = df[variables].dropna()

    if len(variables) == 2:
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(plot_df[variables[0]], plot_df[variables[1]], alpha=0.6, color="#6baed6")
        ax.set_title(f"{variables[0]} vs {variables[1]} 산점도", fontsize=14)
        ax.set_xlabel(variables[0])
        ax.set_ylabel(variables[1])
    else:
        fig = sns.pairplot(plot_df, diag_kind="hist", plot_kws={"alpha": 0.6, "color": "#6baed6"})
        fig.fig.suptitle("산점도 행렬", y=1.02, fontsize=14)
        fig = fig.fig

    filename = build_plot_filename(session_id, "scatter")
    filepath = save_figure(fig, plots_dir, filename)
    return filepath, filename


def create_correlation_heatmap(
    df: pd.DataFrame,
    analysis_columns: List[str],
    plots_dir: str,
    session_id: str,
) -> Tuple[str, str, pd.DataFrame]:
    """상관관계 히트맵 생성."""
    setup_korean_font()
    numeric_cols = get_numeric_columns(df, analysis_columns)
    if len(numeric_cols) < 2:
        raise ValueError("상관관계 분석을 위해서는 최소 2개 이상의 숫자형 변수가 필요합니다.")

    corr_df = df[numeric_cols].corr()
    fig, ax = plt.subplots(figsize=(max(6, len(numeric_cols)), max(5, len(numeric_cols) - 1)))
    sns.heatmap(
        corr_df,
        annot=True,
        fmt=".2f",
        cmap="RdYlBu_r",
        center=0,
        linewidths=0.5,
        ax=ax,
    )
    ax.set_title("상관관계 히트맵", fontsize=14)

    filename = build_plot_filename(session_id, "heatmap")
    filepath = save_figure(fig, plots_dir, filename)
    return filepath, filename, corr_df


def create_validation_plots(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    residuals: np.ndarray,
    plots_dir: str,
    session_id: str,
) -> Dict[str, str]:
    """모델 검증용 잔차 분석 그래프 생성."""
    setup_korean_font()
    plot_paths: Dict[str, str] = {}

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(y_true, y_pred, alpha=0.6, color="#6baed6")
    min_val = min(y_true.min(), y_pred.min())
    max_val = max(y_true.max(), y_pred.max())
    ax.plot([min_val, max_val], [min_val, max_val], "r--", linewidth=1)
    ax.set_title("실제값 vs 예측값")
    ax.set_xlabel("실제값")
    ax.set_ylabel("예측값")
    plot_paths["actual_vs_pred"] = save_figure(
        fig, plots_dir, build_plot_filename(session_id, "val_actual_pred")
    )

    fig, ax = plt.subplots(figsize=(7, 5))
    sns.histplot(residuals, kde=True, ax=ax, color="#7ec8a3")
    ax.set_title("잔차 히스토그램")
    ax.set_xlabel("잔차")
    ax.set_ylabel("빈도")
    plot_paths["residual_hist"] = save_figure(
        fig, plots_dir, build_plot_filename(session_id, "val_residual_hist")
    )

    fig, ax = plt.subplots(figsize=(7, 5))
    from scipy import stats

    stats.probplot(residuals, dist="norm", plot=ax)
    ax.set_title("잔차 Q-Q Plot")
    plot_paths["qq_plot"] = save_figure(
        fig, plots_dir, build_plot_filename(session_id, "val_qq")
    )

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(y_pred, residuals, alpha=0.6, color="#9ecae1")
    ax.axhline(0, color="red", linestyle="--", linewidth=1)
    ax.set_title("잔차 vs 예측값")
    ax.set_xlabel("예측값")
    ax.set_ylabel("잔차")
    plot_paths["residual_vs_pred"] = save_figure(
        fig, plots_dir, build_plot_filename(session_id, "val_residual_pred")
    )

    return plot_paths


def plot_to_static_url(filepath: str) -> str:
    """static 폴더 기준 URL 경로 반환."""
    normalized = filepath.replace("\\", "/")
    if "/static/" in normalized:
        return normalized.split("/static/", 1)[1]
    return os.path.basename(filepath)


def format_number(value: Any) -> str:
    """숫자 포맷 (천 단위 구분)."""
    try:
        num = float(value)
        if num == int(num):
            return f"{int(num):,}"
        return f"{num:,.4f}"
    except (TypeError, ValueError):
        return str(value)


def export_dataframe_to_bytes(df: pd.DataFrame, file_format: str) -> Tuple[BytesIO, str, str]:
    """DataFrame을 다운로드용 바이트로 변환."""
    buffer = BytesIO()
    if file_format == "csv":
        df.to_csv(buffer, index=False, encoding="utf-8-sig")
        mimetype = "text/csv"
        filename = "analysis_data.csv"
    elif file_format == "xlsx":
        df.to_excel(buffer, index=False)
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "analysis_data.xlsx"
    else:
        raise ValueError("지원하지 않는 다운로드 형식입니다.")
    buffer.seek(0)
    return buffer, mimetype, filename

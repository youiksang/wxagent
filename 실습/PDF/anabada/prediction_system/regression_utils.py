"""회귀분석, 모델 저장/로드, 성능 지표 계산 유틸리티."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import Lasso, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.preprocessing import StandardScaler


REGRESSION_METHODS = {
    "forward": "전진선택법",
    "backward": "후진제거법",
    "ridge": "릿지 회귀",
    "lasso": "라쏘 회귀",
}


def calculate_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """MAPE 계산."""
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    mask = y_true != 0
    if not mask.any():
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def calculate_adjusted_r2(r2: float, n_samples: int, n_features: int) -> float:
    """Adjusted R² 계산."""
    if n_samples <= n_features + 1:
        return float("nan")
    return 1 - (1 - r2) * (n_samples - 1) / (n_samples - n_features - 1)


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_features: int,
) -> Dict[str, Any]:
    """예측 성능 지표 계산."""
    r2 = float(r2_score(y_true, y_pred))
    n_samples = len(y_true)
    adj_r2 = calculate_adjusted_r2(r2, n_samples, n_features)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    mape = calculate_mape(y_true, y_pred)

    return {
        "R2": round(r2, 4),
        "Adjusted_R2": round(adj_r2, 4) if not np.isnan(adj_r2) else None,
        "RMSE": round(rmse, 4),
        "MAE": round(mae, 4),
        "MAPE": round(mape, 4) if not np.isnan(mape) else None,
    }


def prepare_regression_data(
    df: pd.DataFrame,
    dependent_var: str,
    independent_vars: List[str],
    test_size: float = 0.2,
    random_state: int = 42,
) -> Dict[str, Any]:
    """회귀분석용 데이터 전처리 및 train/test 분리."""
    if dependent_var not in df.columns:
        raise ValueError(f"종속변수 '{dependent_var}'가 데이터에 존재하지 않습니다.")

    missing_indeps = [v for v in independent_vars if v not in df.columns]
    if missing_indeps:
        raise ValueError(f"독립변수가 데이터에 존재하지 않습니다: {', '.join(missing_indeps)}")

    if not independent_vars:
        raise ValueError("독립변수를 하나 이상 선택해야 합니다.")

    if not pd.api.types.is_numeric_dtype(df[dependent_var]):
        raise ValueError("종속변수는 숫자형이어야 합니다.")

    work_df = df[[dependent_var] + independent_vars].copy()
    work_df = work_df.dropna()

    if len(work_df) < 10:
        raise ValueError("회귀분석에 사용할 수 있는 데이터 행이 부족합니다. (최소 10행 필요)")

    y = work_df[dependent_var]
    X_raw = work_df[independent_vars]

    numeric_cols = [c for c in independent_vars if pd.api.types.is_numeric_dtype(X_raw[c])]
    categorical_cols = [c for c in independent_vars if c not in numeric_cols]

    X_processed = pd.get_dummies(X_raw, columns=categorical_cols, drop_first=True)
    feature_columns = X_processed.columns.tolist()

    if not feature_columns:
        raise ValueError("회귀분석에 사용할 독립변수가 없습니다.")

    X_train, X_test, y_train, y_test = train_test_split(
        X_processed,
        y,
        test_size=test_size,
        random_state=random_state,
    )

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_columns": feature_columns,
        "dummy_columns": [c for c in feature_columns if c not in numeric_cols],
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "original_independent_vars": independent_vars,
        "dependent_var": dependent_var,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
    }


def build_equation(
    dependent_var: str,
    intercept: float,
    coefficients: Dict[str, float],
    selected_features: Optional[List[str]] = None,
) -> str:
    """한글 회귀식 문자열 생성."""
    features = selected_features if selected_features else list(coefficients.keys())
    terms: List[str] = []
    for feat in features:
        if feat not in coefficients:
            continue
        coef = coefficients[feat]
        sign = "+" if coef >= 0 else "-"
        terms.append(f" {sign} {abs(coef):.4f}×{feat}")

    equation = f"{dependent_var} = {intercept:.4f}"
    if terms:
        equation += "".join(terms)
    return equation


def forward_selection(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    p_enter: float = 0.05,
) -> Tuple[List[str], Any, Dict[str, float]]:
    """전진선택법 (statsmodels OLS)."""
    remaining = list(X_train.columns)
    selected: List[str] = []

    while remaining:
        best_pvalue = None
        best_var = None
        best_model = None

        for var in remaining:
            trial_vars = selected + [var]
            X_trial = sm.add_constant(X_train[trial_vars])
            model = sm.OLS(y_train, X_trial).fit()
            pvalue = model.pvalues[var]
            if best_pvalue is None or pvalue < best_pvalue:
                best_pvalue = pvalue
                best_var = var
                best_model = model

        if best_var is None or best_pvalue is None or best_pvalue >= p_enter:
            break

        selected.append(best_var)
        remaining.remove(best_var)

    if not selected:
        X_const = sm.add_constant(X_train.iloc[:, :1])
        final_model = sm.OLS(y_train, X_const).fit()
        selected = [X_train.columns[0]]
    else:
        X_final = sm.add_constant(X_train[selected])
        final_model = sm.OLS(y_train, X_final).fit()

    pvalues = {var: float(final_model.pvalues[var]) for var in selected}
    return selected, final_model, pvalues


def backward_elimination(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    p_remove: float = 0.05,
) -> Tuple[List[str], Any, Dict[str, float]]:
    """후진제거법 (statsmodels OLS)."""
    selected = list(X_train.columns)

    while len(selected) > 0:
        X_trial = sm.add_constant(X_train[selected])
        model = sm.OLS(y_train, X_trial).fit()
        pvalues = {var: float(model.pvalues[var]) for var in selected}
        worst_var = max(pvalues, key=pvalues.get)
        worst_p = pvalues[worst_var]

        if worst_p <= p_remove:
            break
        selected.remove(worst_var)

    if not selected:
        selected = [X_train.columns[0]]

    X_final = sm.add_constant(X_train[selected])
    final_model = sm.OLS(y_train, X_final).fit()
    pvalues = {var: float(final_model.pvalues[var]) for var in selected}
    return selected, final_model, pvalues


def ols_predict(
    model: Any,
    X: pd.DataFrame,
    selected_features: List[str],
) -> np.ndarray:
    """OLS 모델 예측."""
    X_const = sm.add_constant(X[selected_features], has_constant="add")
    return np.array(model.predict(X_const))


def run_ridge_regression(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> Dict[str, Any]:
    """릿지 회귀 (GridSearchCV)."""
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    alphas = [0.01, 0.1, 1, 10, 100]
    ridge = Ridge(random_state=42)
    grid = GridSearchCV(ridge, param_grid={"alpha": alphas}, cv=5, scoring="r2")
    grid.fit(X_train_scaled, y_train)

    best_model = grid.best_estimator_
    y_train_pred = best_model.predict(X_train_scaled)
    y_test_pred = best_model.predict(X_test_scaled)

    coef_map = {col: float(coef) for col, coef in zip(X_train.columns, best_model.coef_)}
    selected = list(X_train.columns)

    train_metrics = compute_metrics(y_train.values, y_train_pred, len(selected))
    test_metrics = compute_metrics(y_test.values, y_test_pred, len(selected))

    return {
        "model": best_model,
        "scaler": scaler,
        "selected_features": selected,
        "coefficients": coef_map,
        "intercept": float(best_model.intercept_),
        "alpha": float(grid.best_params_["alpha"]),
        "pvalues": {},
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "y_test_pred": y_test_pred,
    }


def run_lasso_regression(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> Dict[str, Any]:
    """라쏘 회귀 (GridSearchCV)."""
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    alphas = [0.001, 0.01, 0.1, 1, 10]
    lasso = Lasso(max_iter=10000, random_state=42)
    grid = GridSearchCV(lasso, param_grid={"alpha": alphas}, cv=5, scoring="r2")
    grid.fit(X_train_scaled, y_train)

    best_model = grid.best_estimator_
    y_train_pred = best_model.predict(X_train_scaled)
    y_test_pred = best_model.predict(X_test_scaled)

    coef_map = {col: float(coef) for col, coef in zip(X_train.columns, best_model.coef_)}
    selected = [col for col, coef in coef_map.items() if abs(coef) > 1e-10]

    train_metrics = compute_metrics(y_train.values, y_train_pred, max(len(selected), 1))
    test_metrics = compute_metrics(y_test.values, y_test_pred, max(len(selected), 1))

    return {
        "model": best_model,
        "scaler": scaler,
        "selected_features": selected if selected else list(X_train.columns),
        "coefficients": coef_map,
        "intercept": float(best_model.intercept_),
        "alpha": float(grid.best_params_["alpha"]),
        "pvalues": {},
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "y_test_pred": y_test_pred,
    }


def run_ols_regression(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    method: str,
) -> Dict[str, Any]:
    """전진선택법 또는 후진제거법 실행."""
    if method == "forward":
        selected, model, pvalues = forward_selection(X_train, y_train)
        method_label = "전진선택법"
    elif method == "backward":
        selected, model, pvalues = backward_elimination(X_train, y_train)
        method_label = "후진제거법"
    else:
        raise ValueError(f"지원하지 않는 OLS 방법: {method}")

    y_train_pred = ols_predict(model, X_train, selected)
    y_test_pred = ols_predict(model, X_test, selected)

    coef_map = {feat: float(model.params[feat]) for feat in selected}
    intercept = float(model.params["const"])

    train_metrics = compute_metrics(y_train.values, y_train_pred, len(selected))
    test_metrics = compute_metrics(y_test.values, y_test_pred, len(selected))

    train_metrics["Adjusted_R2"] = round(float(model.rsquared_adj), 4)

    return {
        "model": model,
        "scaler": None,
        "selected_features": selected,
        "coefficients": coef_map,
        "intercept": intercept,
        "alpha": None,
        "pvalues": pvalues,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "method_label": method_label,
        "y_test_pred": y_test_pred,
        "ols_rsquared": float(model.rsquared),
        "ols_adj_rsquared": float(model.rsquared_adj),
    }


def save_model_bundle(
    models_dir: str,
    session_id: str,
    method: str,
    bundle: Dict[str, Any],
) -> str:
    """모델 및 전처리 정보 저장."""
    os.makedirs(models_dir, exist_ok=True)
    filepath = os.path.join(models_dir, f"{session_id}_{method}_model.joblib")
    joblib.dump(bundle, filepath)
    return filepath


def load_model_bundle(path: str) -> Dict[str, Any]:
    """저장된 모델 번들 로드."""
    if not path or not os.path.exists(path):
        raise FileNotFoundError("모델 파일을 불러올 수 없습니다.")
    return joblib.load(path)


def predict_with_bundle(
    bundle: Dict[str, Any],
    X: pd.DataFrame,
) -> np.ndarray:
    """저장된 모델 번들로 예측."""
    model = bundle["model"]
    method = bundle.get("method", "")
    selected_features = bundle.get("selected_features", [])
    feature_columns = bundle.get("feature_columns", selected_features)
    scaler = bundle.get("scaler")

    X_input = X.copy()
    for col in feature_columns:
        if col not in X_input.columns:
            X_input[col] = 0
    X_input = X_input[feature_columns]

    if method in ("ridge", "lasso") and scaler is not None:
        X_scaled = scaler.transform(X_input)
        return model.predict(X_scaled)

    if method in ("forward", "backward"):
        return ols_predict(model, X_input, selected_features)

    if hasattr(model, "predict"):
        if scaler is not None:
            return model.predict(scaler.transform(X_input))
        return model.predict(X_input)

    raise ValueError("예측에 사용할 수 없는 모델입니다.")


def run_regression_analysis(
    df: pd.DataFrame,
    dependent_var: str,
    independent_vars: List[str],
    method: str,
    models_dir: str,
    session_id: str,
) -> Dict[str, Any]:
    """회귀분석 통합 실행."""
    if method not in REGRESSION_METHODS:
        raise ValueError("지원하지 않는 회귀분석 방법입니다.")

    data = prepare_regression_data(df, dependent_var, independent_vars)
    X_train = data["X_train"]
    X_test = data["X_test"]
    y_train = data["y_train"]
    y_test = data["y_test"]

    if method in ("forward", "backward"):
        result = run_ols_regression(X_train, X_test, y_train, y_test, method)
        method_label = result["method_label"]
        test_metrics = result["test_metrics"]
        if result.get("ols_adj_rsquared") is not None:
            test_metrics["Adjusted_R2"] = round(result["ols_adj_rsquared"], 4)
    elif method == "ridge":
        result = run_ridge_regression(X_train, X_test, y_train, y_test)
        method_label = "릿지 회귀"
        test_metrics = result["test_metrics"]
    elif method == "lasso":
        result = run_lasso_regression(X_train, X_test, y_train, y_test)
        method_label = "라쏘 회귀"
        test_metrics = result["test_metrics"]
    else:
        raise ValueError("지원하지 않는 회귀분석 방법입니다.")

    equation = build_equation(
        dependent_var,
        result["intercept"],
        result["coefficients"],
        result["selected_features"],
    )

    bundle = {
        "method": method,
        "model": result["model"],
        "scaler": result.get("scaler"),
        "selected_features": result["selected_features"],
        "feature_columns": data["feature_columns"],
        "dummy_columns": data["dummy_columns"],
        "numeric_columns": data["numeric_columns"],
        "categorical_columns": data["categorical_columns"],
        "original_independent_vars": independent_vars,
        "dependent_var": dependent_var,
        "intercept": result["intercept"],
        "coefficients": result["coefficients"],
        "equation": equation,
    }

    model_path = save_model_bundle(models_dir, session_id, method, bundle)
    scaler_path = None
    if result.get("scaler") is not None:
        scaler_path = os.path.join(models_dir, f"{session_id}_{method}_scaler.joblib")
        joblib.dump(result["scaler"], scaler_path)

    combined_metrics = {
        **test_metrics,
        "train_rows": data["train_rows"],
        "test_rows": data["test_rows"],
    }

    coef_table = []
    for feat in result["selected_features"]:
        row = {
            "변수": feat,
            "회귀계수": round(result["coefficients"].get(feat, 0), 4),
            "p-value": round(result["pvalues"].get(feat, float("nan")), 4)
            if feat in result.get("pvalues", {})
            else None,
        }
        coef_table.append(row)

    return {
        "method": method,
        "method_label": method_label,
        "dependent_var": dependent_var,
        "selected_features": result["selected_features"],
        "all_feature_columns": data["feature_columns"],
        "dummy_columns": data["dummy_columns"],
        "coefficients": result["coefficients"],
        "intercept": result["intercept"],
        "pvalues": result.get("pvalues", {}),
        "alpha": result.get("alpha"),
        "metrics": combined_metrics,
        "equation": equation,
        "model_pkl_path": model_path,
        "scaler_pkl_path": scaler_path,
        "coef_table": coef_table,
        "train_rows": data["train_rows"],
        "test_rows": data["test_rows"],
    }


def run_validation_analysis(
    df: pd.DataFrame,
    bundle: Dict[str, Any],
    plots_dir: str,
    session_id: str,
) -> Dict[str, Any]:
    """모델 검증: 잔차분석 및 적합도 검정."""
    from analysis_utils import create_validation_plots

    dependent_var = bundle["dependent_var"]
    independent_vars = bundle.get("original_independent_vars", [])

    work_df = df[[dependent_var] + independent_vars].dropna()
    y = work_df[dependent_var].values

    X_raw = work_df[independent_vars]
    categorical_cols = bundle.get("categorical_columns", [])
    X_processed = pd.get_dummies(X_raw, columns=categorical_cols, drop_first=True)

    for col in bundle.get("feature_columns", []):
        if col not in X_processed.columns:
            X_processed[col] = 0
    X_processed = X_processed[bundle.get("feature_columns", X_processed.columns.tolist())]

    y_pred = predict_with_bundle(bundle, X_processed)
    residuals = y - y_pred

    from scipy import stats

    residual_stats = {
        "mean": round(float(np.mean(residuals)), 4),
        "std": round(float(np.std(residuals)), 4),
        "min": round(float(np.min(residuals)), 4),
        "max": round(float(np.max(residuals)), 4),
    }

    n_features = len(bundle.get("selected_features", []))
    metrics = compute_metrics(y, y_pred, n_features)

    test_results: Dict[str, Any] = {}

    if len(residuals) >= 3:
        shapiro_stat, shapiro_p = stats.shapiro(residuals[:5000])
        test_results["shapiro"] = {
            "statistic": round(float(shapiro_stat), 4),
            "p_value": round(float(shapiro_p), 4),
            "interpretation": (
                "p-value가 0.05보다 크면 잔차가 정규성을 만족한다고 볼 수 있습니다."
                if shapiro_p > 0.05
                else "p-value가 0.05 이하이면 잔차의 정규성 가정이 충족되지 않을 수 있습니다."
            ),
            "passed": shapiro_p > 0.05,
        }

        jb_stat, jb_p = stats.jarque_bera(residuals)
        test_results["jarque_bera"] = {
            "statistic": round(float(jb_stat), 4),
            "p_value": round(float(jb_p), 4),
            "interpretation": (
                "p-value가 0.05보다 크면 정규성을 만족한다고 볼 수 있습니다."
                if jb_p > 0.05
                else "p-value가 0.05 이하이면 정규성 가정이 위배될 수 있습니다."
            ),
            "passed": jb_p > 0.05,
        }

    try:
        from statsmodels.stats.diagnostic import het_breuschpagan

        bp_stat, bp_p, _, _ = het_breuschpagan(residuals, sm.add_constant(y_pred.reshape(-1, 1)))
        test_results["breusch_pagan"] = {
            "statistic": round(float(bp_stat), 4),
            "p_value": round(float(bp_p), 4),
            "interpretation": (
                "p-value가 0.05보다 크면 등분산성을 만족한다고 볼 수 있습니다."
                if bp_p > 0.05
                else "p-value가 0.05 이하이면 등분산성 가정이 위배될 수 있습니다."
            ),
            "passed": bp_p > 0.05,
        }
    except Exception:
        test_results["breusch_pagan"] = {
            "interpretation": "등분산성 검정(Breusch-Pagan)을 수행할 수 없습니다.",
            "passed": None,
        }

    try:
        X_ols = sm.add_constant(X_processed[bundle.get("selected_features", X_processed.columns)])
        ols_model = sm.OLS(y, X_ols).fit()
        dw = sm.stats.stattools.durbin_watson(ols_model.resid)
        test_results["durbin_watson"] = {
            "statistic": round(float(dw), 4),
            "interpretation": (
                "Durbin-Watson 값이 2에 가까우면 자기상관이 약하다고 해석할 수 있습니다."
                if 1.5 <= dw <= 2.5
                else "Durbin-Watson 값이 2에서 멀면 자기상관이 있을 수 있습니다."
            ),
            "passed": 1.5 <= dw <= 2.5,
        }
    except Exception:
        dw = sm.stats.stattools.durbin_watson(residuals)
        test_results["durbin_watson"] = {
            "statistic": round(float(dw), 4),
            "interpretation": (
                "Durbin-Watson 값이 2에 가까우면 자기상관이 약하다고 해석할 수 있습니다."
            ),
            "passed": 1.5 <= dw <= 2.5,
        }

    plot_paths = create_validation_plots(y, y_pred, residuals, plots_dir, session_id)

    sample_size = min(20, len(y))
    residual_sample = []
    for i in range(sample_size):
        residual_sample.append(
            {
                "실제값": round(float(y[i]), 4),
                "예측값": round(float(y_pred[i]), 4),
                "잔차": round(float(residuals[i]), 4),
            }
        )

    return {
        "residual_stats": residual_stats,
        "metrics": metrics,
        "test_results": test_results,
        "plot_paths": plot_paths,
        "residual_sample": residual_sample,
    }

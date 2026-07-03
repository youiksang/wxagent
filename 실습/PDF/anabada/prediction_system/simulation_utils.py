"""Plotly/Dash 기반 시뮬레이션 유틸리티."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html

from regression_utils import load_model_bundle, predict_with_bundle


def get_simulation_inputs_config(
    df: pd.DataFrame,
    independent_vars: List[str],
) -> Dict[str, Any]:
    """슬라이더/드롭다운 설정 생성."""
    numeric_inputs: List[Dict[str, Any]] = []
    categorical_inputs: List[Dict[str, Any]] = []

    for var in independent_vars:
        if var not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[var]):
            series = df[var].dropna()
            numeric_inputs.append(
                {
                    "name": var,
                    "min": float(series.min()),
                    "max": float(series.max()),
                    "default": float(series.mean()),
                    "step": float((series.max() - series.min()) / 100) if series.max() != series.min() else 0.1,
                }
            )
        else:
            categories = sorted(df[var].dropna().unique().tolist())
            categorical_inputs.append(
                {
                    "name": var,
                    "options": [{"label": str(c), "value": str(c)} for c in categories],
                    "default": str(categories[0]) if categories else "",
                }
            )

    return {
        "numeric_inputs": numeric_inputs,
        "categorical_inputs": categorical_inputs,
    }


def build_feature_row(
    input_values: Dict[str, Any],
    bundle: Dict[str, Any],
) -> pd.DataFrame:
    """사용자 입력값을 모델 feature 행으로 변환."""
    independent_vars = bundle.get("original_independent_vars", [])
    row_data: Dict[str, Any] = {}

    for var in independent_vars:
        if var in input_values:
            val = input_values[var]
            if isinstance(val, str):
                try:
                    val = float(val)
                except ValueError:
                    pass
            row_data[var] = [val]
        elif var in bundle.get("categorical_columns", []):
            row_data[var] = [""]

    raw_df = pd.DataFrame(row_data)
    categorical_cols = bundle.get("categorical_columns", [])
    processed = pd.get_dummies(raw_df, columns=categorical_cols, drop_first=True)

    for col in bundle.get("feature_columns", []):
        if col not in processed.columns:
            processed[col] = 0

    feature_columns = bundle.get("feature_columns", processed.columns.tolist())
    return processed[feature_columns]


def predict_simulation(
    bundle: Dict[str, Any],
    input_values: Dict[str, Any],
) -> float:
    """시뮬레이션 예측값 계산."""
    feature_row = build_feature_row(input_values, bundle)
    prediction = predict_with_bundle(bundle, feature_row)
    return float(prediction[0])


def create_bar_chart_figure(
    dependent_var: str,
    predicted_value: float,
) -> go.Figure:
    """예측값 막대그래프."""
    fig = go.Figure(
        data=[
            go.Bar(
                x=[dependent_var],
                y=[predicted_value],
                marker_color="#7ec8a3",
                text=[f"{predicted_value:,.2f}"],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=f"예측된 {dependent_var}",
        yaxis_title="예측값",
        template="plotly_white",
        height=350,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def create_simulation_dash_app(
    server: Any,
    url_base_pathname: str,
    session_id: str,
    bundle: Dict[str, Any],
    input_config: Dict[str, Any],
    on_predict_callback: Optional[Any] = None,
) -> Dash:
    """Flask 서버에 연동되는 Dash 시뮬레이션 앱 생성."""
    dependent_var = bundle.get("dependent_var", "종속변수")
    numeric_inputs = input_config.get("numeric_inputs", [])
    categorical_inputs = input_config.get("categorical_inputs", [])

    dash_app = Dash(
        __name__,
        server=server,
        url_base_pathname=url_base_pathname,
        suppress_callback_exceptions=True,
    )

    slider_components = []
    slider_ids = []
    for item in numeric_inputs:
        slider_id = f"slider-{item['name']}"
        slider_ids.append(slider_id)
        slider_components.append(
            html.Div(
                [
                    html.Label(f"{item['name']}: ", className="sim-label"),
                    dcc.Slider(
                        id=slider_id,
                        min=item["min"],
                        max=item["max"],
                        step=max(item["step"], 0.01),
                        value=item["default"],
                        marks={
                            item["min"]: f"{item['min']:.1f}",
                            item["max"]: f"{item['max']:.1f}",
                        },
                        tooltip={"placement": "bottom", "always_visible": True},
                    ),
                ],
                className="sim-slider-group mb-3",
            )
        )

    dropdown_components = []
    dropdown_ids = []
    for item in categorical_inputs:
        dropdown_id = f"dropdown-{item['name']}"
        dropdown_ids.append(dropdown_id)
        dropdown_components.append(
            html.Div(
                [
                    html.Label(f"{item['name']}: ", className="sim-label"),
                    dcc.Dropdown(
                        id=dropdown_id,
                        options=item["options"],
                        value=item["default"],
                        clearable=False,
                    ),
                ],
                className="sim-dropdown-group mb-3",
            )
        )

    dash_app.layout = html.Div(
        [
            html.H5("독립변수 입력", className="mb-3"),
            html.Div(slider_components + dropdown_components, className="sim-inputs"),
            html.Hr(),
            html.Div(id="current-inputs-display", className="mb-3"),
            html.H4(id="prediction-display", className="prediction-value mb-3"),
            dcc.Graph(id="prediction-bar-chart"),
            dcc.Store(id="session-store", data={"session_id": session_id}),
        ],
        className="simulation-dash-container p-3",
    )

    all_input_ids = slider_ids + dropdown_ids
    if not all_input_ids:
        all_input_ids = [dcc.Store(id="empty-store")]

    @dash_app.callback(
        Output("prediction-display", "children"),
        Output("prediction-bar-chart", "figure"),
        Output("current-inputs-display", "children"),
        [Input(component_id, "value") for component_id in (slider_ids + dropdown_ids)]
        if (slider_ids + dropdown_ids)
        else [Input("empty-store", "data")],
    )
    def update_prediction(*args):
        input_values: Dict[str, Any] = {}

        for item, val in zip(numeric_inputs, args[: len(numeric_inputs)]):
            input_values[item["name"]] = val

        cat_offset = len(numeric_inputs)
        for idx, item in enumerate(categorical_inputs):
            input_values[item["name"]] = args[cat_offset + idx]

        if not numeric_inputs and not categorical_inputs:
            return (
                "입력 가능한 독립변수가 없습니다.",
                create_bar_chart_figure(dependent_var, 0),
                "",
            )

        try:
            predicted = predict_simulation(bundle, input_values)
        except Exception as exc:
            return (
                f"예측 중 오류가 발생했습니다: {exc}",
                create_bar_chart_figure(dependent_var, 0),
                "",
            )

        if on_predict_callback:
            on_predict_callback(session_id, input_values, predicted)

        inputs_text = ", ".join([f"{k}: {v}" for k, v in input_values.items()])
        display = f"예측된 {dependent_var}: {predicted:,.4f}"
        fig = create_bar_chart_figure(dependent_var, predicted)

        return display, fig, html.P(f"현재 입력값: {inputs_text}", className="text-muted")

    return dash_app


def get_default_input_values(input_config: Dict[str, Any]) -> Dict[str, Any]:
    """기본 입력값 딕셔너리."""
    values: Dict[str, Any] = {}
    for item in input_config.get("numeric_inputs", []):
        values[item["name"]] = item["default"]
    for item in input_config.get("categorical_inputs", []):
        values[item["name"]] = item["default"]
    return values


def run_static_simulation(
    bundle_path: str,
    input_values: Dict[str, Any],
) -> Dict[str, Any]:
    """Dash 없이 단일 예측 실행."""
    bundle = load_model_bundle(bundle_path)
    predicted = predict_simulation(bundle, input_values)
    dependent_var = bundle.get("dependent_var", "종속변수")
    return {
        "dependent_var": dependent_var,
        "predicted_value": predicted,
        "input_values": input_values,
        "figure": create_bar_chart_figure(dependent_var, predicted),
    }

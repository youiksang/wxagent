"""예측 시스템 Flask 애플리케이션."""

from __future__ import annotations

import os
import uuid
from functools import wraps
from io import BytesIO

import pandas as pd
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from analysis_utils import (
    ALLOWED_EXTENSIONS,
    allowed_file,
    create_correlation_heatmap,
    create_histogram,
    create_scatter_plot,
    dataframe_to_html_describe,
    dataframe_to_html_head,
    detect_outliers,
    export_dataframe_to_bytes,
    format_number,
    get_file_extension,
    get_numeric_columns,
    load_dataframe,
    plot_to_static_url,
    process_missing_values,
    read_data_file,
    remove_outliers,
    save_dataframe,
)
from models import (
    EDAHistory,
    FinalModel,
    MissingDataResult,
    OutlierResult,
    RegressionResult,
    SimulationRecord,
    UploadRecord,
    ValidationResult,
    VariableSelection,
    add_activity_log,
    build_session_paths,
    db,
    delete_all_sessions,
    get_or_create_session,
    get_session_by_id,
    get_step_label,
    init_db,
    reset_session_data,
    reset_analysis_for_reupload,
    save_final_model_from_regression,
    save_regression_result,
)
from regression_utils import REGRESSION_METHODS, load_model_bundle, run_regression_analysis, run_validation_analysis
from simulation_utils import create_simulation_dash_app, get_default_input_values, get_simulation_inputs_config

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "prediction-system-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "instance", "prediction_system.sqlite3")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

init_db(app)

_dash_apps: dict = {}


def get_current_analysis_session():
    """Flask session에서 AnalysisSession 조회."""
    session_id = session.get("session_id")
    return get_or_create_session(session_id)


def ensure_flask_session(analysis_session) -> None:
    """Flask session에 session_id 저장."""
    session["session_id"] = analysis_session.session_id


def step_access_required(route_name: str):
    """단계별 접근 제어 데코레이터."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            analysis_session = get_current_analysis_session()
            ensure_flask_session(analysis_session)
            if not analysis_session.can_access_route(route_name):
                flash("이전 단계를 먼저 완료해주세요.", "warning")
                return redirect(url_for("upload"))
            return view_func(analysis_session, *args, **kwargs)

        return wrapper

    return decorator


def render_step(
    analysis_session,
    template_name: str,
    route_name: str,
    step_title: str,
    **context,
):
    """공통 템플릿 렌더."""
    menu_states = analysis_session.get_menu_states(active_route=route_name)
    return render_template(
        template_name,
        session_obj=analysis_session,
        menu_states=menu_states,
        step_title=step_title,
        current_route=route_name,
        **context,
    )


def get_working_dataframe(analysis_session) -> pd.DataFrame:
    """현재 분석용 DataFrame 로드."""
    path = analysis_session.current_pkl_path or analysis_session.original_pkl_path
    if not path:
        raise FileNotFoundError("업로드된 데이터가 없습니다.")
    return load_dataframe(path)


def save_working_dataframe(analysis_session, df: pd.DataFrame) -> str:
    """현재 분석용 DataFrame 저장."""
    paths = build_session_paths(BASE_DIR, analysis_session.session_id)
    save_dataframe(df, paths["current_pkl"])
    analysis_session.current_pkl_path = paths["current_pkl"]
    db.session.commit()
    return paths["current_pkl"]


@app.route("/")
def index():
    return redirect(url_for("upload"))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    analysis_session = get_current_analysis_session()
    ensure_flask_session(analysis_session)

    if request.method == "POST":
        if "file" not in request.files:
            flash("파일을 선택해주세요.", "danger")
            return redirect(url_for("upload"))

        file = request.files["file"]
        if not file or not file.filename:
            flash("파일을 선택해주세요.", "danger")
            return redirect(url_for("upload"))

        filename = secure_filename(file.filename)
        if not allowed_file(filename):
            flash("지원하지 않는 파일 형식입니다. CSV 또는 Excel(.xlsx, .xls) 파일만 업로드할 수 있습니다.", "danger")
            return redirect(url_for("upload"))

        try:
            ext = get_file_extension(filename)
            paths = build_session_paths(BASE_DIR, analysis_session.session_id)
            stored_name = f"{analysis_session.session_id}_{uuid.uuid4().hex[:8]}_{filename}"
            stored_path = os.path.join(paths["uploads_dir"], stored_name)
            file.save(stored_path)

            df = read_data_file(stored_path, ext)
            save_dataframe(df, paths["original_pkl"])
            save_dataframe(df, paths["current_pkl"])

            reset_analysis_for_reupload(analysis_session.session_id)
            db.session.refresh(analysis_session)

            upload_record = UploadRecord(
                session_id=analysis_session.session_id,
                original_filename=filename,
                stored_path=stored_path,
                pkl_path=paths["original_pkl"],
                row_count=len(df),
                column_count=len(df.columns),
                file_extension=ext,
            )
            upload_record.set_columns(df.columns.tolist())

            analysis_session.original_pkl_path = paths["original_pkl"]
            analysis_session.current_pkl_path = paths["current_pkl"]
            analysis_session.mark_step_complete("upload")
            db.session.add(upload_record)
            db.session.commit()

            add_activity_log(
                analysis_session.session_id,
                "파일 업로드 완료",
                {"filename": filename, "rows": len(df), "columns": len(df.columns)},
            )
            flash("파일 업로드가 완료되었습니다.", "success")
            return redirect(url_for("upload"))

        except Exception as exc:
            flash(f"파일을 읽을 수 없습니다: {exc}", "danger")
            return redirect(url_for("upload"))

    preview_html = None
    describe_html = None
    upload_info = None

    if analysis_session.upload_record:
        try:
            df = get_working_dataframe(analysis_session)
            rec = analysis_session.upload_record
            upload_info = {
                "filename": rec.original_filename,
                "rows": rec.row_count,
                "columns": rec.column_count,
                "column_list": rec.columns,
            }
            preview_html = dataframe_to_html_head(df, 10)
            describe_html = dataframe_to_html_describe(df)
        except Exception as exc:
            flash(f"데이터 미리보기 오류: {exc}", "warning")

    return render_step(
        analysis_session,
        "upload.html",
        "upload",
        "1. 파일 업로드",
        upload_info=upload_info,
        preview_html=preview_html,
        describe_html=describe_html,
        format_number=format_number,
    )


@app.route("/variables", methods=["GET", "POST"])
@step_access_required("variables")
def variables(analysis_session):
    columns = []
    if analysis_session.upload_record:
        columns = analysis_session.upload_record.columns

    selected_dep = None
    selected_indeps = []
    result_info = None

    if request.method == "POST":
        dependent_var = request.form.get("dependent_var", "").strip()
        independent_vars = request.form.getlist("independent_vars")

        if not dependent_var:
            flash("종속변수를 선택해주세요.", "danger")
            return redirect(url_for("variables"))
        if not independent_vars:
            flash("독립변수를 하나 이상 선택해주세요.", "danger")
            return redirect(url_for("variables"))
        if dependent_var in independent_vars:
            flash("종속변수가 독립변수에 중복 선택되었습니다.", "danger")
            return redirect(url_for("variables"))

        missing = [v for v in [dependent_var] + independent_vars if v not in columns]
        if missing:
            flash(f"선택한 변수가 데이터에 존재하지 않습니다: {', '.join(missing)}", "danger")
            return redirect(url_for("variables"))

        try:
            df = get_working_dataframe(analysis_session)
            analysis_cols = [dependent_var] + independent_vars
            subset = df[analysis_cols]

            if analysis_session.variable_selection:
                vs = analysis_session.variable_selection
            else:
                vs = VariableSelection(session_id=analysis_session.session_id)
                db.session.add(vs)

            vs.dependent_var = dependent_var
            vs.set_independent_vars(independent_vars)
            vs.set_analysis_columns(analysis_cols)
            vs.row_count = len(subset)
            vs.column_count = len(analysis_cols)

            analysis_session.mark_step_complete("variables")
            db.session.commit()

            add_activity_log(
                analysis_session.session_id,
                "변수 선택 완료",
                {"dependent": dependent_var, "independent": independent_vars},
            )
            flash("변수 선택이 완료되었습니다.", "success")
            return redirect(url_for("variables"))

        except Exception as exc:
            flash(f"변수 선택 처리 오류: {exc}", "danger")
            return redirect(url_for("variables"))

    if analysis_session.variable_selection:
        vs = analysis_session.variable_selection
        selected_dep = vs.dependent_var
        selected_indeps = vs.independent_list
        result_info = {
            "dependent": vs.dependent_var,
            "independent": vs.independent_list,
            "analysis_columns": vs.analysis_list,
            "rows": vs.row_count,
            "columns": vs.column_count,
        }

    return render_step(
        analysis_session,
        "variable_select.html",
        "variables",
        "2. 변수 선택",
        columns=columns,
        selected_dep=selected_dep,
        selected_indeps=selected_indeps,
        result_info=result_info,
        format_number=format_number,
    )


@app.route("/missing", methods=["GET", "POST"])
@step_access_required("missing")
def missing(analysis_session):
    if not analysis_session.variable_selection:
        flash("변수 선택을 먼저 완료해주세요.", "warning")
        return redirect(url_for("variables"))

    result_info = None
    preview_html = None

    if request.method == "POST":
        try:
            df = get_working_dataframe(analysis_session)
            vs = analysis_session.variable_selection
            cleaned, stats = process_missing_values(df, vs.analysis_list)

            if stats["rows_after"] == 0:
                flash("결측치 제거 후 데이터가 비어버렸습니다. 다른 변수를 선택하거나 원본 데이터를 확인해주세요.", "danger")
                return redirect(url_for("missing"))

            pkl_path = save_working_dataframe(analysis_session, cleaned)

            if analysis_session.missing_result:
                mr = analysis_session.missing_result
            else:
                mr = MissingDataResult(session_id=analysis_session.session_id)
                db.session.add(mr)

            mr.rows_before = stats["rows_before"]
            mr.missing_rows = stats["missing_rows"]
            mr.removed_rows = stats["removed_rows"]
            mr.rows_after = stats["rows_after"]
            mr.pkl_path = pkl_path

            analysis_session.mark_step_complete("missing")
            db.session.commit()

            add_activity_log(analysis_session.session_id, "결측치 제거 완료", stats)
            flash("결측치 제거가 완료되었습니다.", "success")
            return redirect(url_for("missing"))

        except Exception as exc:
            flash(f"결측치 제거 오류: {exc}", "danger")
            return redirect(url_for("missing"))

    if analysis_session.missing_result:
        mr = analysis_session.missing_result
        result_info = {
            "rows_before": mr.rows_before,
            "missing_rows": mr.missing_rows,
            "removed_rows": mr.removed_rows,
            "rows_after": mr.rows_after,
        }
        try:
            df = get_working_dataframe(analysis_session)
            preview_html = dataframe_to_html_head(df[analysis_session.variable_selection.analysis_list], 10)
        except Exception:
            pass

    return render_step(
        analysis_session,
        "missing.html",
        "missing",
        "3. 결측치 제거",
        result_info=result_info,
        preview_html=preview_html,
        format_number=format_number,
    )


@app.route("/outlier", methods=["GET", "POST"])
@step_access_required("outlier")
def outlier(analysis_session):
    if not analysis_session.variable_selection:
        flash("변수 선택을 먼저 완료해주세요.", "warning")
        return redirect(url_for("variables"))

    detection_results = []
    result_info = None
    preview_html = None
    action = request.form.get("action", "explore") if request.method == "POST" else None

    try:
        df = get_working_dataframe(analysis_session)
        vs = analysis_session.variable_selection
        detection_results = detect_outliers(df, vs.analysis_list)
    except Exception as exc:
        flash(f"이상치 탐색 오류: {exc}", "danger")

    if request.method == "POST":
        try:
            df = get_working_dataframe(analysis_session)
            vs = analysis_session.variable_selection

            if not detection_results:
                numeric = get_numeric_columns(df, vs.analysis_list)
                if not numeric:
                    flash("숫자형 변수가 없어 이상치 탐색을 수행할 수 없습니다.", "warning")
                analysis_session.mark_step_complete("outlier")
                db.session.commit()
                return redirect(url_for("outlier"))

            if action == "remove":
                remove_vars = request.form.getlist("remove_vars")
                cleaned, stats = remove_outliers(df, remove_vars, detection_results)

                if stats["rows_after"] == 0:
                    flash("이상치 제거 후 데이터가 비어버렸습니다.", "danger")
                    return redirect(url_for("outlier"))

                pkl_path = save_working_dataframe(analysis_session, cleaned)

                if analysis_session.outlier_result:
                    orr = analysis_session.outlier_result
                else:
                    orr = OutlierResult(session_id=analysis_session.session_id)
                    db.session.add(orr)

                orr.set_detection_results(detection_results)
                orr.rows_before = stats["rows_before"]
                orr.removed_rows = stats["removed_rows"]
                orr.rows_after = stats["rows_after"]
                orr.set_removed_variables(remove_vars)
                orr.pkl_path = pkl_path
                orr.explored_only = False

                add_activity_log(
                    analysis_session.session_id,
                    "이상치 제거 완료",
                    {"removed_vars": remove_vars, **stats},
                )
                flash("이상치 제거가 완료되었습니다.", "success")
            else:
                if analysis_session.outlier_result:
                    orr = analysis_session.outlier_result
                else:
                    orr = OutlierResult(session_id=analysis_session.session_id)
                    db.session.add(orr)

                orr.set_detection_results(detection_results)
                orr.rows_before = len(df)
                orr.removed_rows = 0
                orr.rows_after = len(df)
                orr.set_removed_variables([])
                orr.explored_only = True

                add_activity_log(analysis_session.session_id, "이상치 탐색 완료", {"variables": len(detection_results)})
                flash("이상치 탐색이 완료되었습니다.", "success")

            analysis_session.mark_step_complete("outlier")
            db.session.commit()
            return redirect(url_for("outlier"))

        except Exception as exc:
            flash(f"이상치 처리 오류: {exc}", "danger")
            return redirect(url_for("outlier"))

    if analysis_session.outlier_result:
        orr = analysis_session.outlier_result
        detection_results = orr.detection_list
        result_info = {
            "rows_before": orr.rows_before,
            "removed_rows": orr.removed_rows,
            "rows_after": orr.rows_after,
            "removed_vars": orr.removed_var_list,
        }
        try:
            df = get_working_dataframe(analysis_session)
            preview_html = dataframe_to_html_head(df[analysis_session.variable_selection.analysis_list], 10)
        except Exception:
            pass

    numeric_available = bool(detection_results)

    return render_step(
        analysis_session,
        "outlier.html",
        "outlier",
        "4. 이상치 탐색",
        detection_results=detection_results,
        result_info=result_info,
        preview_html=preview_html,
        numeric_available=numeric_available,
        format_number=format_number,
    )


@app.route("/eda", methods=["GET", "POST"])
@step_access_required("eda")
def eda(analysis_session):
    if not analysis_session.variable_selection:
        flash("변수 선택을 먼저 완료해주세요.", "warning")
        return redirect(url_for("variables"))

    vs = analysis_session.variable_selection
    df = get_working_dataframe(analysis_session)
    numeric_cols = get_numeric_columns(df, vs.analysis_list)

    plot_url = None
    corr_html = None
    eda_message = None
    selected_type = request.form.get("analysis_type", "") if request.method == "POST" else ""

    if request.method == "POST":
        action = request.form.get("action", "run")

        if action == "complete":
            analysis_session.mark_step_complete("eda")
            db.session.commit()
            add_activity_log(analysis_session.session_id, "탐색적 분석 완료", {})
            flash("탐색적 분석 단계가 완료되었습니다.", "success")
            return redirect(url_for("regression"))

        analysis_type = request.form.get("analysis_type", "")
        paths = build_session_paths(BASE_DIR, analysis_session.session_id)

        try:
            if analysis_type == "histogram":
                variable = request.form.get("hist_var", "")
                filepath, filename = create_histogram(df, variable, paths["plots_dir"], analysis_session.session_id)
                plot_url = url_for("static", filename=f"plots/{filename}")
                eda_message = f"선택한 변수: {variable}"

            elif analysis_type == "scatter":
                scatter_vars = request.form.getlist("scatter_vars")
                if len(scatter_vars) < 2:
                    eda_message = "산점도 분석을 위해서는 최소 2개 이상의 숫자형 변수를 선택해야 합니다."
                else:
                    filepath, filename = create_scatter_plot(
                        df, scatter_vars, paths["plots_dir"], analysis_session.session_id
                    )
                    plot_url = url_for("static", filename=f"plots/{filename}")
                    eda_message = f"선택한 변수: {', '.join(scatter_vars)}"

            elif analysis_type == "heatmap":
                if len(numeric_cols) < 2:
                    eda_message = "상관관계 분석을 위해서는 최소 2개 이상의 숫자형 변수가 필요합니다."
                else:
                    filepath, filename, corr_df = create_correlation_heatmap(
                        df, vs.analysis_list, paths["plots_dir"], analysis_session.session_id
                    )
                    plot_url = url_for("static", filename=f"plots/{filename}")
                    corr_html = corr_df.to_html(classes="table table-bordered table-sm")
                    eda_message = "숫자형 변수 상관관계 분석"

            if plot_url:
                history = EDAHistory(
                    session_id=analysis_session.session_id,
                    analysis_type=analysis_type,
                    plot_path=filepath,
                )
                history.set_parameters(request.form.to_dict())
                db.session.add(history)
                if not analysis_session.eda_completed:
                    analysis_session.mark_step_complete("eda")
                db.session.commit()
                add_activity_log(
                    analysis_session.session_id,
                    "탐색적 분석 실행",
                    {"type": analysis_type},
                )
                flash("탐색적 분석 그래프가 생성되었습니다.", "success")

        except Exception as exc:
            flash(f"그래프 생성 실패: {exc}", "danger")

    eda_histories = analysis_session.eda_histories[:5] if analysis_session.eda_histories else []

    return render_step(
        analysis_session,
        "eda.html",
        "eda",
        "5. 탐색적 분석",
        numeric_cols=numeric_cols,
        plot_url=plot_url,
        corr_html=corr_html,
        eda_message=eda_message,
        selected_type=selected_type,
        eda_histories=eda_histories,
    )


@app.route("/regression", methods=["GET", "POST"])
@step_access_required("regression")
def regression(analysis_session):
    if not analysis_session.variable_selection:
        flash("변수 선택을 먼저 완료해주세요.", "warning")
        return redirect(url_for("variables"))

    vs = analysis_session.variable_selection
    regression_results = {}
    selected_method = request.form.get("method", "") if request.method == "POST" else ""

    if request.method == "POST" and request.form.get("action") == "run":
        method = request.form.get("method", "")
        if method not in REGRESSION_METHODS:
            flash("회귀분석 방법을 선택해주세요.", "danger")
            return redirect(url_for("regression"))

        try:
            df = get_working_dataframe(analysis_session)
            paths = build_session_paths(BASE_DIR, analysis_session.session_id)
            result = run_regression_analysis(
                df,
                vs.dependent_var,
                vs.independent_list,
                method,
                paths["models_dir"],
                analysis_session.session_id,
            )

            save_regression_result(
                session_id=analysis_session.session_id,
                method=result["method"],
                method_label=result["method_label"],
                dependent_var=result["dependent_var"],
                selected_features=result["selected_features"],
                coefficients=result["coefficients"],
                metrics=result["metrics"],
                equation=result["equation"],
                model_pkl_path=result["model_pkl_path"],
                scaler_pkl_path=result["scaler_pkl_path"],
                alpha=result.get("alpha"),
                pvalues=result.get("pvalues"),
                all_feature_columns=result["all_feature_columns"],
                dummy_columns=result["dummy_columns"],
                intercept=result["intercept"],
                train_rows=result["train_rows"],
                test_rows=result["test_rows"],
            )

            add_activity_log(
                analysis_session.session_id,
                "회귀분석 실행",
                {"method": result["method_label"]},
            )
            flash(f"{result['method_label']} 회귀분석이 완료되었습니다.", "success")
            return redirect(url_for("regression"))

        except Exception as exc:
            flash(f"회귀분석 실패: {exc}", "danger")
            return redirect(url_for("regression"))

    for reg in analysis_session.regression_results:
        regression_results[reg.method] = {
            "method_label": reg.method_label,
            "equation": reg.equation,
            "metrics": reg.metrics_dict,
            "selected_features": reg.feature_list,
            "coef_table": [
                {
                    "변수": feat,
                    "회귀계수": reg.coef_dict.get(feat),
                    "p-value": reg.pvalue_dict.get(feat),
                }
                for feat in reg.feature_list
            ],
            "alpha": reg.alpha,
            "intercept": reg.intercept,
        }

    final_model = analysis_session.final_model

    return render_step(
        analysis_session,
        "regression.html",
        "regression",
        "6. 회귀분석",
        methods=REGRESSION_METHODS,
        regression_results=regression_results,
        selected_method=selected_method,
        final_model=final_model,
        dependent_var=vs.dependent_var,
    )


@app.route("/select-model", methods=["GET", "POST"])
@step_access_required("regression")
def select_model(analysis_session):
    if request.method == "POST":
        method = request.form.get("final_method", "")
        reg = next((r for r in analysis_session.regression_results if r.method == method), None)

        if not reg:
            flash("선택한 모델의 회귀분석 결과가 없습니다. 먼저 회귀분석을 실행해주세요.", "danger")
            return redirect(url_for("regression"))

        model_name = REGRESSION_METHODS.get(method, method)
        save_final_model_from_regression(analysis_session, reg, model_name)
        analysis_session.mark_step_complete("regression")
        db.session.commit()

        add_activity_log(
            analysis_session.session_id,
            "최종 모델 선택",
            {"model": model_name},
        )
        flash(f"최종 모델로 '{model_name}'이(가) 선택되었습니다.", "success")
        return redirect(url_for("validation"))

    return redirect(url_for("regression"))


@app.route("/validation", methods=["GET", "POST"])
@step_access_required("validation")
def validation(analysis_session):
    if not analysis_session.final_model:
        flash("최종 모델을 먼저 선택해주세요.", "warning")
        return redirect(url_for("regression"))

    validation_data = None
    plot_urls = {}

    if request.method == "POST":
        try:
            fm = analysis_session.final_model
            bundle = load_model_bundle(fm.model_pkl_path)
            df = get_working_dataframe(analysis_session)
            paths = build_session_paths(BASE_DIR, analysis_session.session_id)

            result = run_validation_analysis(
                df, bundle, paths["plots_dir"], analysis_session.session_id
            )

            if analysis_session.validation_result:
                vr = analysis_session.validation_result
            else:
                vr = ValidationResult(session_id=analysis_session.session_id)
                db.session.add(vr)

            vr.set_residual_stats(result["residual_stats"])
            vr.set_metrics(result["metrics"])
            vr.set_test_results(result["test_results"])
            vr.set_plot_paths(result["plot_paths"])
            vr.set_residual_sample(result["residual_sample"])

            analysis_session.mark_step_complete("validation")
            db.session.commit()

            add_activity_log(analysis_session.session_id, "모델 검증 완료", {})
            flash("모델 검증이 완료되었습니다.", "success")
            return redirect(url_for("validation"))

        except Exception as exc:
            flash(f"모델 검증 오류: {exc}", "danger")

    if analysis_session.validation_result:
        try:
            vr = analysis_session.validation_result
            validation_data = {
                "residual_stats": vr.residual_stats_dict,
                "metrics": vr.metrics_dict,
                "test_results": vr.test_results_dict,
                "residual_sample": loads_json_safe(vr.residual_sample),
            }
            for key, path in vr.plot_path_dict.items():
                if path and os.path.exists(path):
                    plot_urls[key] = url_for("static", filename=f"plots/{os.path.basename(path)}")
        except Exception as exc:
            flash(f"검증 결과 표시 오류: {exc}", "warning")

    return render_step(
        analysis_session,
        "validation.html",
        "validation",
        "7. 모델 검증",
        final_model=analysis_session.final_model,
        validation_data=validation_data,
        plot_urls=plot_urls,
    )


def loads_json_safe(text):
    from models import loads_json
    return loads_json(text, default=[])


def _save_simulation_record(session_id: str, input_values: dict, predicted: float) -> None:
    """Dash 콜백에서 시뮬레이션 기록 저장."""
    with app.app_context():
        analysis_session = get_session_by_id(session_id)
        if not analysis_session or not analysis_session.final_model:
            return
        fm = analysis_session.final_model
        record = SimulationRecord(
            session_id=session_id,
            predicted_value=predicted,
            dependent_var=fm.dependent_var,
            model_name=fm.model_name,
        )
        record.set_input_values(input_values)
        db.session.add(record)
        if not analysis_session.simulation_completed:
            analysis_session.mark_step_complete("simulation")
        db.session.commit()


@app.route("/simulation")
@step_access_required("simulation")
def simulation_view(analysis_session):
    if not analysis_session.final_model:
        flash("최종 모델을 먼저 선택해주세요.", "warning")
        return redirect(url_for("regression"))

    if not analysis_session.validation_completed:
        flash("모델 검증을 먼저 완료해주세요.", "warning")
        return redirect(url_for("validation"))

    fm = analysis_session.final_model
    dash_path = f"/simulation/dash/{analysis_session.session_id}/"
    input_config: dict = {"numeric_inputs": [], "categorical_inputs": []}

    try:
        bundle = load_model_bundle(fm.model_pkl_path)
        df = get_working_dataframe(analysis_session)
        input_config = get_simulation_inputs_config(df, fm.independent_list)

        if analysis_session.session_id not in _dash_apps:
            create_simulation_dash_app(
                server=app,
                url_base_pathname=dash_path,
                session_id=analysis_session.session_id,
                bundle=bundle,
                input_config=input_config,
                on_predict_callback=_save_simulation_record,
            )
            _dash_apps[analysis_session.session_id] = dash_path

    except Exception as exc:
        flash(f"Dash 앱 연동 실패: {exc}", "danger")
        dash_path = None

    recent_simulations = analysis_session.simulation_records[:10]

    return render_step(
        analysis_session,
        "simulation.html",
        "simulation",
        "8. 시뮬레이션",
        final_model=fm,
        dash_path=dash_path,
        input_config=input_config,
        recent_simulations=recent_simulations,
    )


@app.route("/reset", methods=["POST"])
def reset():
    analysis_session = get_current_analysis_session()
    session_id = analysis_session.session_id

    if session_id in _dash_apps:
        del _dash_apps[session_id]

    reset_session_data(analysis_session, BASE_DIR)
    session.clear()

    new_session = get_or_create_session()
    ensure_flask_session(new_session)
    flash("전체 분석이 초기화되었습니다.", "info")
    return redirect(url_for("upload"))


@app.route("/download/current-data")
@step_access_required("upload")
def download_current_data(analysis_session):
    try:
        df = get_working_dataframe(analysis_session)
        fmt = request.args.get("format", "csv")
        buffer, mimetype, filename = export_dataframe_to_bytes(df, fmt)
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)
    except Exception as exc:
        flash(f"다운로드 오류: {exc}", "danger")
        return redirect(url_for("upload"))


@app.route("/download/regression-result")
@step_access_required("regression")
def download_regression_result(analysis_session):
    try:
        rows = []
        for reg in analysis_session.regression_results:
            rows.append(
                {
                    "방법": reg.method_label,
                    "종속변수": reg.dependent_var,
                    "선택변수": ", ".join(reg.feature_list),
                    "R2": reg.metrics_dict.get("R2"),
                    "Adjusted_R2": reg.metrics_dict.get("Adjusted_R2"),
                    "RMSE": reg.metrics_dict.get("RMSE"),
                    "MAE": reg.metrics_dict.get("MAE"),
                    "MAPE": reg.metrics_dict.get("MAPE"),
                    "회귀식": reg.equation,
                }
            )
        df = pd.DataFrame(rows)
        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding="utf-8-sig")
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="text/csv",
            as_attachment=True,
            download_name="regression_results.csv",
        )
    except Exception as exc:
        flash(f"다운로드 오류: {exc}", "danger")
        return redirect(url_for("regression"))


@app.route("/download/validation-result")
@step_access_required("validation")
def download_validation_result(analysis_session):
    try:
        if not analysis_session.validation_result:
            flash("모델 검증 결과가 없습니다.", "warning")
            return redirect(url_for("validation"))

        vr = analysis_session.validation_result
        rows = [
            {"항목": "R2", "값": vr.metrics_dict.get("R2")},
            {"항목": "Adjusted_R2", "값": vr.metrics_dict.get("Adjusted_R2")},
            {"항목": "RMSE", "값": vr.metrics_dict.get("RMSE")},
            {"항목": "MAE", "값": vr.metrics_dict.get("MAE")},
            {"항목": "MAPE", "값": vr.metrics_dict.get("MAPE")},
        ]
        for key, val in vr.residual_stats_dict.items():
            rows.append({"항목": f"잔차_{key}", "값": val})

        df = pd.DataFrame(rows)
        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding="utf-8-sig")
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="text/csv",
            as_attachment=True,
            download_name="validation_results.csv",
        )
    except Exception as exc:
        flash(f"다운로드 오류: {exc}", "danger")
        return redirect(url_for("validation"))


if __name__ == "__main__":
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000)

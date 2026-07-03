"""SQLite3 데이터베이스 모델 및 세션 관리 유틸리티."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# 단계 번호 및 라우트 매핑
STEP_DEFINITIONS: List[Dict[str, Any]] = [
    {"step": 1, "key": "upload", "label": "1. 파일 업로드", "route": "upload", "flag": "upload_completed"},
    {"step": 2, "key": "variables", "label": "2. 변수 선택", "route": "variables", "flag": "variable_selected"},
    {"step": 3, "key": "missing", "label": "3. 결측치 제거", "route": "missing", "flag": "missing_processed"},
    {"step": 4, "key": "outlier", "label": "4. 이상치 탐색", "route": "outlier", "flag": "outlier_processed"},
    {"step": 5, "key": "eda", "label": "5. 탐색적 분석", "route": "eda", "flag": "eda_completed"},
    {"step": 6, "key": "regression", "label": "6. 회귀분석", "route": "regression", "flag": "regression_completed"},
    {"step": 7, "key": "validation", "label": "7. 모델 검증", "route": "validation", "flag": "validation_completed"},
    {"step": 8, "key": "simulation", "label": "8. 시뮬레이션", "route": "simulation", "flag": "simulation_completed"},
]

STEP_ROUTE_MAP: Dict[str, int] = {item["route"]: item["step"] for item in STEP_DEFINITIONS}
STEP_FLAG_MAP: Dict[str, str] = {item["route"]: item["flag"] for item in STEP_DEFINITIONS}


def utcnow() -> datetime:
    """UTC 기준 현재 시각."""
    return datetime.now(timezone.utc)


def dumps_json(data: Any) -> str:
    """Python 객체를 JSON 문자열로 직렬화."""
    return json.dumps(data, ensure_ascii=False, default=str)


def loads_json(text: Optional[str], default: Any = None) -> Any:
    """JSON 문자열을 Python 객체로 역직렬화."""
    if not text:
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


class AnalysisSession(db.Model):
    """사용자 분석 세션의 전체 진행 상태."""

    __tablename__ = "analysis_sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    current_step = db.Column(db.Integer, default=1, nullable=False)

    upload_completed = db.Column(db.Boolean, default=False, nullable=False)
    variable_selected = db.Column(db.Boolean, default=False, nullable=False)
    missing_processed = db.Column(db.Boolean, default=False, nullable=False)
    outlier_processed = db.Column(db.Boolean, default=False, nullable=False)
    eda_completed = db.Column(db.Boolean, default=False, nullable=False)
    regression_completed = db.Column(db.Boolean, default=False, nullable=False)
    validation_completed = db.Column(db.Boolean, default=False, nullable=False)
    simulation_completed = db.Column(db.Boolean, default=False, nullable=False)

    original_pkl_path = db.Column(db.String(512), nullable=True)
    current_pkl_path = db.Column(db.String(512), nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    upload_record = db.relationship(
        "UploadRecord",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    variable_selection = db.relationship(
        "VariableSelection",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    missing_result = db.relationship(
        "MissingDataResult",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    outlier_result = db.relationship(
        "OutlierResult",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    eda_histories = db.relationship(
        "EDAHistory",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="EDAHistory.created_at.desc()",
    )
    regression_results = db.relationship(
        "RegressionResult",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="RegressionResult.created_at.desc()",
    )
    final_model = db.relationship(
        "FinalModel",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    validation_result = db.relationship(
        "ValidationResult",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )
    simulation_records = db.relationship(
        "SimulationRecord",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SimulationRecord.created_at.desc()",
    )
    activity_logs = db.relationship(
        "ActivityLog",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ActivityLog.created_at.desc()",
    )

    def get_flag(self, flag_name: str) -> bool:
        """단계 완료 플래그 조회."""
        return bool(getattr(self, flag_name, False))

    def set_flag(self, flag_name: str, value: bool = True) -> None:
        """단계 완료 플래그 설정."""
        if hasattr(self, flag_name):
            setattr(self, flag_name, value)
            self.updated_at = utcnow()

    def is_step_completed(self, step_number: int) -> bool:
        """특정 단계 완료 여부."""
        for item in STEP_DEFINITIONS:
            if item["step"] == step_number:
                return self.get_flag(item["flag"])
        return False

    def max_accessible_step(self) -> int:
        """현재 접근 가능한 최대 단계 번호."""
        if not self.upload_completed:
            return 1
        if not self.variable_selected:
            return 2
        if not self.missing_processed:
            return 3
        if not self.outlier_processed:
            return 4
        if not self.eda_completed:
            return 5
        if not self.regression_completed:
            return 6
        if not self.validation_completed:
            return 7
        if not self.simulation_completed:
            return 8
        return 8

    def can_access_route(self, route_name: str) -> bool:
        """라우트 접근 가능 여부."""
        step_number = STEP_ROUTE_MAP.get(route_name, 1)
        return step_number <= self.max_accessible_step()

    def mark_step_complete(self, route_name: str) -> None:
        """라우트에 해당하는 단계를 완료 처리."""
        flag_name = STEP_FLAG_MAP.get(route_name)
        if flag_name:
            self.set_flag(flag_name, True)
        step_number = STEP_ROUTE_MAP.get(route_name)
        if step_number:
            next_step = min(step_number + 1, 8)
            if next_step > self.current_step:
                self.current_step = next_step
            self.updated_at = utcnow()

    def get_menu_states(self, active_route: Optional[str] = None) -> List[Dict[str, Any]]:
        """사이드바 메뉴 상태 목록."""
        max_step = self.max_accessible_step()
        states: List[Dict[str, Any]] = []

        for item in STEP_DEFINITIONS:
            step = item["step"]
            completed = self.is_step_completed(step)
            accessible = step <= max_step
            is_current = active_route == item["route"] if active_route else step == self.current_step

            if completed:
                status = "completed"
            elif accessible:
                status = "available"
            else:
                status = "disabled"

            states.append(
                {
                    "step": step,
                    "key": item["key"],
                    "label": item["label"],
                    "route": item["route"],
                    "status": status,
                    "completed": completed,
                    "accessible": accessible,
                    "is_current": is_current,
                }
            )
        return states

    def to_dict(self) -> Dict[str, Any]:
        """세션 상태 딕셔너리."""
        return {
            "session_id": self.session_id,
            "current_step": self.current_step,
            "upload_completed": self.upload_completed,
            "variable_selected": self.variable_selected,
            "missing_processed": self.missing_processed,
            "outlier_processed": self.outlier_processed,
            "eda_completed": self.eda_completed,
            "regression_completed": self.regression_completed,
            "validation_completed": self.validation_completed,
            "simulation_completed": self.simulation_completed,
            "original_pkl_path": self.original_pkl_path,
            "current_pkl_path": self.current_pkl_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class UploadRecord(db.Model):
    """파일 업로드 메타데이터."""

    __tablename__ = "upload_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    original_filename = db.Column(db.String(512), nullable=False)
    stored_path = db.Column(db.String(512), nullable=False)
    pkl_path = db.Column(db.String(512), nullable=False)
    row_count = db.Column(db.Integer, nullable=False)
    column_count = db.Column(db.Integer, nullable=False)
    column_names = db.Column(db.Text, nullable=False)
    file_extension = db.Column(db.String(16), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="upload_record")

    @property
    def columns(self) -> List[str]:
        return loads_json(self.column_names, default=[])

    def set_columns(self, columns: List[str]) -> None:
        self.column_names = dumps_json(columns)


class VariableSelection(db.Model):
    """종속/독립 변수 선택 결과."""

    __tablename__ = "variable_selections"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    dependent_var = db.Column(db.String(256), nullable=False)
    independent_vars = db.Column(db.Text, nullable=False)
    analysis_columns = db.Column(db.Text, nullable=False)
    row_count = db.Column(db.Integer, nullable=True)
    column_count = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="variable_selection")

    @property
    def independent_list(self) -> List[str]:
        return loads_json(self.independent_vars, default=[])

    @property
    def analysis_list(self) -> List[str]:
        return loads_json(self.analysis_columns, default=[])

    def set_independent_vars(self, variables: List[str]) -> None:
        self.independent_vars = dumps_json(variables)

    def set_analysis_columns(self, columns: List[str]) -> None:
        self.analysis_columns = dumps_json(columns)


class MissingDataResult(db.Model):
    """결측치 제거 결과."""

    __tablename__ = "missing_data_results"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    rows_before = db.Column(db.Integer, nullable=False)
    missing_rows = db.Column(db.Integer, nullable=False)
    removed_rows = db.Column(db.Integer, nullable=False)
    rows_after = db.Column(db.Integer, nullable=False)
    pkl_path = db.Column(db.String(512), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="missing_result")


class OutlierResult(db.Model):
    """이상치 탐색 및 제거 결과."""

    __tablename__ = "outlier_results"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    detection_results = db.Column(db.Text, nullable=False)
    rows_before = db.Column(db.Integer, nullable=True)
    removed_rows = db.Column(db.Integer, nullable=True)
    rows_after = db.Column(db.Integer, nullable=True)
    removed_variables = db.Column(db.Text, nullable=True)
    pkl_path = db.Column(db.String(512), nullable=True)
    explored_only = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="outlier_result")

    @property
    def detection_list(self) -> List[Dict[str, Any]]:
        return loads_json(self.detection_results, default=[])

    def set_detection_results(self, results: List[Dict[str, Any]]) -> None:
        self.detection_results = dumps_json(results)

    @property
    def removed_var_list(self) -> List[str]:
        return loads_json(self.removed_variables, default=[])

    def set_removed_variables(self, variables: List[str]) -> None:
        self.removed_variables = dumps_json(variables)


class EDAHistory(db.Model):
    """탐색적 분석 실행 이력."""

    __tablename__ = "eda_histories"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_type = db.Column(db.String(64), nullable=False)
    parameters = db.Column(db.Text, nullable=True)
    plot_path = db.Column(db.String(512), nullable=True)
    result_summary = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="eda_histories")

    @property
    def params(self) -> Dict[str, Any]:
        return loads_json(self.parameters, default={})

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.parameters = dumps_json(params)


class RegressionResult(db.Model):
    """회귀분석 방법별 결과."""

    __tablename__ = "regression_results"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method = db.Column(db.String(64), nullable=False, index=True)
    method_label = db.Column(db.String(128), nullable=False)
    dependent_var = db.Column(db.String(256), nullable=False)
    selected_features = db.Column(db.Text, nullable=False)
    all_feature_columns = db.Column(db.Text, nullable=True)
    dummy_columns = db.Column(db.Text, nullable=True)
    coefficients = db.Column(db.Text, nullable=False)
    intercept = db.Column(db.Float, nullable=True)
    metrics = db.Column(db.Text, nullable=False)
    equation = db.Column(db.Text, nullable=True)
    model_pkl_path = db.Column(db.String(512), nullable=True)
    scaler_pkl_path = db.Column(db.String(512), nullable=True)
    alpha = db.Column(db.Float, nullable=True)
    pvalues = db.Column(db.Text, nullable=True)
    train_rows = db.Column(db.Integer, nullable=True)
    test_rows = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="regression_results")

    @property
    def feature_list(self) -> List[str]:
        return loads_json(self.selected_features, default=[])

    @property
    def metrics_dict(self) -> Dict[str, Any]:
        return loads_json(self.metrics, default={})

    @property
    def coef_dict(self) -> Dict[str, float]:
        return loads_json(self.coefficients, default={})

    @property
    def pvalue_dict(self) -> Dict[str, float]:
        return loads_json(self.pvalues, default={})

    def set_selected_features(self, features: List[str]) -> None:
        self.selected_features = dumps_json(features)

    def set_all_feature_columns(self, columns: List[str]) -> None:
        self.all_feature_columns = dumps_json(columns)

    def set_dummy_columns(self, columns: List[str]) -> None:
        self.dummy_columns = dumps_json(columns)

    def set_coefficients(self, coef_map: Dict[str, float]) -> None:
        self.coefficients = dumps_json(coef_map)

    def set_metrics(self, metrics: Dict[str, Any]) -> None:
        self.metrics = dumps_json(metrics)

    def set_pvalues(self, pvalues: Dict[str, float]) -> None:
        self.pvalues = dumps_json(pvalues)


class FinalModel(db.Model):
    """사용자가 선택한 최종 회귀모형."""

    __tablename__ = "final_models"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    model_name = db.Column(db.String(128), nullable=False)
    method = db.Column(db.String(64), nullable=False)
    dependent_var = db.Column(db.String(256), nullable=False)
    independent_vars = db.Column(db.Text, nullable=False)
    feature_columns = db.Column(db.Text, nullable=False)
    dummy_columns = db.Column(db.Text, nullable=True)
    coefficients = db.Column(db.Text, nullable=False)
    intercept = db.Column(db.Float, nullable=True)
    metrics = db.Column(db.Text, nullable=False)
    equation = db.Column(db.Text, nullable=True)
    model_pkl_path = db.Column(db.String(512), nullable=False)
    scaler_pkl_path = db.Column(db.String(512), nullable=True)
    regression_result_id = db.Column(db.Integer, nullable=True)
    selected_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="final_model")

    @property
    def independent_list(self) -> List[str]:
        return loads_json(self.independent_vars, default=[])

    @property
    def feature_list(self) -> List[str]:
        return loads_json(self.feature_columns, default=[])

    @property
    def dummy_list(self) -> List[str]:
        return loads_json(self.dummy_columns, default=[])

    @property
    def metrics_dict(self) -> Dict[str, Any]:
        return loads_json(self.metrics, default={})

    @property
    def coef_dict(self) -> Dict[str, float]:
        return loads_json(self.coefficients, default={})

    def set_independent_vars(self, variables: List[str]) -> None:
        self.independent_vars = dumps_json(variables)

    def set_feature_columns(self, columns: List[str]) -> None:
        self.feature_columns = dumps_json(columns)

    def set_dummy_columns(self, columns: List[str]) -> None:
        self.dummy_columns = dumps_json(columns)

    def set_coefficients(self, coef_map: Dict[str, float]) -> None:
        self.coefficients = dumps_json(coef_map)

    def set_metrics(self, metrics: Dict[str, Any]) -> None:
        self.metrics = dumps_json(metrics)


class ValidationResult(db.Model):
    """모델 검증 결과."""

    __tablename__ = "validation_results"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    residual_stats = db.Column(db.Text, nullable=False)
    metrics = db.Column(db.Text, nullable=False)
    test_results = db.Column(db.Text, nullable=False)
    plot_paths = db.Column(db.Text, nullable=True)
    residual_sample = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="validation_result")

    @property
    def residual_stats_dict(self) -> Dict[str, Any]:
        return loads_json(self.residual_stats, default={})

    @property
    def metrics_dict(self) -> Dict[str, Any]:
        return loads_json(self.metrics, default={})

    @property
    def test_results_dict(self) -> Dict[str, Any]:
        return loads_json(self.test_results, default={})

    @property
    def plot_path_dict(self) -> Dict[str, str]:
        return loads_json(self.plot_paths, default={})

    def set_residual_stats(self, stats: Dict[str, Any]) -> None:
        self.residual_stats = dumps_json(stats)

    def set_metrics(self, metrics: Dict[str, Any]) -> None:
        self.metrics = dumps_json(metrics)

    def set_test_results(self, results: Dict[str, Any]) -> None:
        self.test_results = dumps_json(results)

    def set_plot_paths(self, paths: Dict[str, str]) -> None:
        self.plot_paths = dumps_json(paths)

    def set_residual_sample(self, sample: List[Dict[str, Any]]) -> None:
        self.residual_sample = dumps_json(sample)


class SimulationRecord(db.Model):
    """시뮬레이션 입력값 및 예측값 이력."""

    __tablename__ = "simulation_records"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    input_values = db.Column(db.Text, nullable=False)
    predicted_value = db.Column(db.Float, nullable=False)
    dependent_var = db.Column(db.String(256), nullable=True)
    model_name = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="simulation_records")

    @property
    def inputs(self) -> Dict[str, Any]:
        return loads_json(self.input_values, default={})

    def set_input_values(self, values: Dict[str, Any]) -> None:
        self.input_values = dumps_json(values)


class ActivityLog(db.Model):
    """단계별 작업 로그."""

    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.String(64),
        db.ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = db.Column(db.String(256), nullable=False)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    session = db.relationship("AnalysisSession", back_populates="activity_logs")

    @property
    def detail_dict(self) -> Dict[str, Any]:
        return loads_json(self.details, default={})

    def set_details(self, details: Dict[str, Any]) -> None:
        self.details = dumps_json(details)


def init_db(app) -> None:
    """Flask 앱에 SQLAlchemy를 초기화하고 테이블을 생성."""
    db.init_app(app)
    with app.app_context():
        db.create_all()


def generate_session_id() -> str:
    """고유 세션 ID 생성."""
    return str(uuid.uuid4())


def get_session_by_id(session_id: str) -> Optional[AnalysisSession]:
    """session_id로 AnalysisSession 조회."""
    if not session_id:
        return None
    return AnalysisSession.query.filter_by(session_id=session_id).first()


def get_or_create_session(session_id: Optional[str] = None) -> AnalysisSession:
    """세션 조회 또는 신규 생성."""
    if session_id:
        existing = get_session_by_id(session_id)
        if existing:
            return existing

    new_session = AnalysisSession(session_id=generate_session_id())
    db.session.add(new_session)
    db.session.commit()
    return new_session


def reset_analysis_for_reupload(session_id: str) -> None:
    """재업로드 시 기존 분석 결과 및 업로드 기록 삭제."""
    UploadRecord.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    VariableSelection.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    MissingDataResult.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    OutlierResult.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    EDAHistory.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    RegressionResult.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    FinalModel.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    ValidationResult.query.filter_by(session_id=session_id).delete(synchronize_session=False)
    SimulationRecord.query.filter_by(session_id=session_id).delete(synchronize_session=False)

    analysis_session = get_session_by_id(session_id)
    if analysis_session:
        analysis_session.upload_completed = False
        analysis_session.variable_selected = False
        analysis_session.missing_processed = False
        analysis_session.outlier_processed = False
        analysis_session.eda_completed = False
        analysis_session.regression_completed = False
        analysis_session.validation_completed = False
        analysis_session.simulation_completed = False
        analysis_session.current_step = 1
        analysis_session.original_pkl_path = None
        analysis_session.current_pkl_path = None
        analysis_session.updated_at = utcnow()

    db.session.flush()


def add_activity_log(
    session_id: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
) -> ActivityLog:
    """작업 로그 추가."""
    log = ActivityLog(session_id=session_id, action=action)
    if details:
        log.set_details(details)
    db.session.add(log)
    db.session.commit()
    return log


def get_step_label(route_name: str) -> str:
    """라우트명에 해당하는 단계 라벨."""
    for item in STEP_DEFINITIONS:
        if item["route"] == route_name:
            return item["label"]
    return "예측 시스템"


def build_session_paths(base_dir: str, session_id: str) -> Dict[str, str]:
    """세션별 파일 경로 생성."""
    processed_dir = os.path.join(base_dir, "data", "processed")
    models_dir = os.path.join(base_dir, "data", "models")
    metadata_dir = os.path.join(base_dir, "data", "metadata")
    plots_dir = os.path.join(base_dir, "static", "plots")
    uploads_dir = os.path.join(base_dir, "static", "uploads")

    for directory in (processed_dir, models_dir, metadata_dir, plots_dir, uploads_dir):
        os.makedirs(directory, exist_ok=True)

    return {
        "processed_dir": processed_dir,
        "models_dir": models_dir,
        "metadata_dir": metadata_dir,
        "plots_dir": plots_dir,
        "uploads_dir": uploads_dir,
        "original_pkl": os.path.join(processed_dir, f"{session_id}_original.pkl"),
        "current_pkl": os.path.join(processed_dir, f"{session_id}_current.pkl"),
        "session_metadata": os.path.join(metadata_dir, f"{session_id}_meta.json"),
    }


def reset_session_data(session: AnalysisSession, base_dir: str) -> None:
    """세션 관련 DB 레코드 및 파일 삭제."""
    session_id = session.session_id
    paths = build_session_paths(base_dir, session_id)

    files_to_remove: List[str] = [
        paths["original_pkl"],
        paths["current_pkl"],
        paths["session_metadata"],
    ]

    if session.upload_record:
        if session.upload_record.stored_path and os.path.exists(session.upload_record.stored_path):
            files_to_remove.append(session.upload_record.stored_path)
        if session.upload_record.pkl_path and os.path.exists(session.upload_record.pkl_path):
            files_to_remove.append(session.upload_record.pkl_path)

    if session.missing_result and session.missing_result.pkl_path:
        if os.path.exists(session.missing_result.pkl_path):
            files_to_remove.append(session.missing_result.pkl_path)

    if session.outlier_result and session.outlier_result.pkl_path:
        if os.path.exists(session.outlier_result.pkl_path):
            files_to_remove.append(session.outlier_result.pkl_path)

    if session.final_model:
        if session.final_model.model_pkl_path and os.path.exists(session.final_model.model_pkl_path):
            files_to_remove.append(session.final_model.model_pkl_path)
        if session.final_model.scaler_pkl_path and os.path.exists(session.final_model.scaler_pkl_path):
            files_to_remove.append(session.final_model.scaler_pkl_path)

    for reg in session.regression_results:
        if reg.model_pkl_path and os.path.exists(reg.model_pkl_path):
            files_to_remove.append(reg.model_pkl_path)
        if reg.scaler_pkl_path and os.path.exists(reg.scaler_pkl_path):
            files_to_remove.append(reg.scaler_pkl_path)

    for eda in session.eda_histories:
        if eda.plot_path and os.path.exists(eda.plot_path):
            files_to_remove.append(eda.plot_path)

    if session.validation_result:
        for plot_path in session.validation_result.plot_path_dict.values():
            if plot_path and os.path.exists(plot_path):
                files_to_remove.append(plot_path)

    plot_prefix = os.path.join(paths["plots_dir"], session_id)
    if os.path.isdir(paths["plots_dir"]):
        for filename in os.listdir(paths["plots_dir"]):
            if filename.startswith(session_id):
                files_to_remove.append(os.path.join(paths["plots_dir"], filename))

    model_prefix = os.path.join(paths["models_dir"], session_id)
    if os.path.isdir(paths["models_dir"]):
        for filename in os.listdir(paths["models_dir"]):
            if filename.startswith(session_id):
                files_to_remove.append(os.path.join(paths["models_dir"], filename))

    for file_path in set(files_to_remove):
        try:
            if file_path and os.path.isfile(file_path):
                os.remove(file_path)
        except OSError:
            pass

    AnalysisSession.query.filter_by(session_id=session_id).delete()
    db.session.commit()


def delete_all_sessions(base_dir: str) -> None:
    """모든 세션 및 관련 파일 삭제 (전체 초기화용)."""
    sessions = AnalysisSession.query.all()
    for session in sessions:
        reset_session_data(session, base_dir)

    uploads_dir = os.path.join(base_dir, "static", "uploads")
    plots_dir = os.path.join(base_dir, "static", "plots")
    processed_dir = os.path.join(base_dir, "data", "processed")
    models_dir = os.path.join(base_dir, "data", "models")
    metadata_dir = os.path.join(base_dir, "data", "metadata")

    for directory in (uploads_dir, plots_dir, processed_dir, models_dir, metadata_dir):
        if not os.path.isdir(directory):
            continue
        for filename in os.listdir(directory):
            if filename == ".gitkeep":
                continue
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except OSError:
                pass


def get_regression_result_by_method(
    session_id: str,
    method: str,
) -> Optional[RegressionResult]:
    """세션의 특정 회귀분석 방법 결과 조회."""
    return (
        RegressionResult.query.filter_by(session_id=session_id, method=method)
        .order_by(RegressionResult.created_at.desc())
        .first()
    )


def save_regression_result(
    session_id: str,
    method: str,
    method_label: str,
    dependent_var: str,
    selected_features: List[str],
    coefficients: Dict[str, float],
    metrics: Dict[str, Any],
    equation: str,
    model_pkl_path: Optional[str] = None,
    scaler_pkl_path: Optional[str] = None,
    alpha: Optional[float] = None,
    pvalues: Optional[Dict[str, float]] = None,
    all_feature_columns: Optional[List[str]] = None,
    dummy_columns: Optional[List[str]] = None,
    intercept: Optional[float] = None,
    train_rows: Optional[int] = None,
    test_rows: Optional[int] = None,
) -> RegressionResult:
    """회귀분석 결과 저장 (동일 method는 갱신)."""
    existing = get_regression_result_by_method(session_id, method)
    if existing:
        result = existing
    else:
        result = RegressionResult(session_id=session_id, method=method)
        db.session.add(result)

    result.method_label = method_label
    result.dependent_var = dependent_var
    result.set_selected_features(selected_features)
    result.set_coefficients(coefficients)
    result.set_metrics(metrics)
    result.equation = equation
    result.model_pkl_path = model_pkl_path
    result.scaler_pkl_path = scaler_pkl_path
    result.alpha = alpha
    result.intercept = intercept
    result.train_rows = train_rows
    result.test_rows = test_rows

    if pvalues is not None:
        result.set_pvalues(pvalues)
    if all_feature_columns is not None:
        result.set_all_feature_columns(all_feature_columns)
    if dummy_columns is not None:
        result.set_dummy_columns(dummy_columns)

    db.session.commit()
    return result


def save_final_model_from_regression(
    session: AnalysisSession,
    regression_result: RegressionResult,
    model_name: str,
) -> FinalModel:
    """회귀분석 결과를 기반으로 최종 모델 저장."""
    variable_selection = session.variable_selection
    independent_vars = variable_selection.independent_list if variable_selection else []

    existing = session.final_model
    if existing:
        final_model = existing
    else:
        final_model = FinalModel(session_id=session.session_id)
        db.session.add(final_model)

    final_model.model_name = model_name
    final_model.method = regression_result.method
    final_model.dependent_var = regression_result.dependent_var
    final_model.set_independent_vars(independent_vars)
    final_model.set_feature_columns(regression_result.feature_list)
    final_model.set_dummy_columns(loads_json(regression_result.dummy_columns, default=[]))
    final_model.set_coefficients(regression_result.coef_dict)
    final_model.intercept = regression_result.intercept
    final_model.set_metrics(regression_result.metrics_dict)
    final_model.equation = regression_result.equation
    final_model.model_pkl_path = regression_result.model_pkl_path or ""
    final_model.scaler_pkl_path = regression_result.scaler_pkl_path
    final_model.regression_result_id = regression_result.id
    final_model.selected_at = utcnow()

    db.session.commit()
    return final_model

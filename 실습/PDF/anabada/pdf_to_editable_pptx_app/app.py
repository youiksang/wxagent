"""
이미지 PDF 슬라이드 → 편집 가능한 PPTX 변환기

PyQt5 기반 데스크톱 앱 메인 진입점.
"""

from __future__ import annotations

import os
import sys
import traceback

PACKAGE_INSTALL_HINTS = {
    "PyQt5": "pip install PyQt5",
    "fitz": "pip install PyMuPDF",
    "easyocr": "pip install easyocr",
    "pptx": "pip install python-pptx",
    "PIL": "pip install Pillow",
    "cv2": "pip install opencv-python",
    "numpy": "pip install numpy",
    "torch": "pip install torch torchvision",
}


def check_required_packages() -> tuple[bool, list[str]]:
    """필수 패키지 import 가능 여부를 확인합니다."""
    missing: list[str] = []

    checks = [
        ("PyQt5", "PyQt5"),
        ("fitz", "PyMuPDF"),
        ("easyocr", "easyocr"),
        ("pptx", "python-pptx"),
        ("PIL", "Pillow"),
        ("cv2", "opencv-python"),
        ("numpy", "numpy"),
    ]

    for module_name, _ in checks:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)

    try:
        import torch  # noqa: F401
    except ImportError:
        missing.append("torch")

    return len(missing) == 0, missing


def show_missing_package_message(missing_modules: list[str]) -> None:
    """누락된 패키지 설치 안내 메시지를 표시합니다."""
    lines = [
        "필수 패키지가 설치되어 있지 않습니다.",
        "",
        "프로젝트 폴더에서 아래 명령을 실행해 주세요:",
        "",
        "  pip install -r requirements.txt",
        "",
        "누락된 패키지:",
    ]
    for module_name in missing_modules:
        hint = PACKAGE_INSTALL_HINTS.get(module_name, f"pip install {module_name}")
        lines.append(f"  - {module_name}: {hint}")

    message = "\n".join(lines)

    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "패키지 설치 필요", message)
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    ok, missing = check_required_packages()
    if not ok:
        show_missing_package_message(missing)
        return 1

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QCloseEvent, QFont
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSpinBox,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    from converter_worker import ConversionSettings, ConverterWorker
    from font_utils import (
        DEFAULT_FONT_OPTION,
        format_font_status_for_log,
        get_default_font_combo_index,
        get_font_combo_items,
    )

    class MainWindow(QMainWindow):
        APP_TITLE = "이미지 PDF 슬라이드 → 편집 가능한 PPTX 변환기"

        def __init__(self):
            super().__init__()
            self.pdf_path = ""
            self.output_path = ""
            self.worker: ConverterWorker | None = None
            self._setup_ui()
            self._append_log(format_font_status_for_log())
            self._append_log("PDF 파일을 선택한 뒤 변환 시작 버튼을 눌러 주세요.")

        def _setup_ui(self) -> None:
            self.setWindowTitle(self.APP_TITLE)
            self.setMinimumSize(820, 720)

            central = QWidget()
            self.setCentralWidget(central)
            root_layout = QVBoxLayout(central)

            title_label = QLabel(self.APP_TITLE)
            title_label.setAlignment(Qt.AlignCenter)
            title_font = QFont()
            title_font.setPointSize(14)
            title_font.setBold(True)
            title_label.setFont(title_font)
            root_layout.addWidget(title_label)

            file_group = QGroupBox("파일 선택")
            file_layout = QVBoxLayout(file_group)

            pdf_row = QHBoxLayout()
            self.pdf_path_edit = QLineEdit()
            self.pdf_path_edit.setReadOnly(True)
            self.pdf_path_edit.setPlaceholderText("PDF 파일 경로")
            pdf_select_btn = QPushButton("PDF 파일 선택")
            pdf_select_btn.clicked.connect(self._select_pdf_file)
            pdf_row.addWidget(self.pdf_path_edit, stretch=1)
            pdf_row.addWidget(pdf_select_btn)
            file_layout.addLayout(pdf_row)

            output_row = QHBoxLayout()
            self.output_path_edit = QLineEdit()
            self.output_path_edit.setPlaceholderText("저장할 PPTX 경로")
            output_select_btn = QPushButton("저장 경로 선택")
            output_select_btn.clicked.connect(self._select_output_path)
            output_row.addWidget(self.output_path_edit, stretch=1)
            output_row.addWidget(output_select_btn)
            file_layout.addLayout(output_row)

            root_layout.addWidget(file_group)

            option_group = QGroupBox("변환 옵션")
            option_layout = QFormLayout(option_group)

            self.font_combo = QComboBox()
            self.font_combo.addItems(get_font_combo_items())
            self.font_combo.setCurrentIndex(get_default_font_combo_index())
            option_layout.addRow("기본 폰트:", self.font_combo)

            self.render_scale_combo = QComboBox()
            self.render_scale_combo.addItems(["2배 (권장)", "3배", "1.5배"])
            self.render_scale_combo.setCurrentIndex(0)
            option_layout.addRow("PDF 렌더링 배율:", self.render_scale_combo)

            self.gpu_combo = QComboBox()
            self.gpu_combo.addItems(["CPU 사용", "GPU 사용"])
            self.gpu_combo.setCurrentIndex(0)
            option_layout.addRow("OCR 장치:", self.gpu_combo)

            self.confidence_spin = QDoubleSpinBox()
            self.confidence_spin.setRange(0.0, 1.0)
            self.confidence_spin.setSingleStep(0.05)
            self.confidence_spin.setValue(0.35)
            self.confidence_spin.setDecimals(2)
            option_layout.addRow("OCR 최소 신뢰도:", self.confidence_spin)

            self.mask_expand_spin = QSpinBox()
            self.mask_expand_spin.setRange(0, 20)
            self.mask_expand_spin.setValue(4)
            option_layout.addRow("텍스트 mask 확장(px):", self.mask_expand_spin)

            self.inpaint_radius_spin = QSpinBox()
            self.inpaint_radius_spin.setRange(1, 20)
            self.inpaint_radius_spin.setValue(3)
            option_layout.addRow("텍스트 제거 강도(inpaint):", self.inpaint_radius_spin)

            self.font_size_scale_spin = QDoubleSpinBox()
            self.font_size_scale_spin.setRange(0.3, 2.0)
            self.font_size_scale_spin.setSingleStep(0.1)
            self.font_size_scale_spin.setValue(0.8)
            self.font_size_scale_spin.setDecimals(1)
            option_layout.addRow("폰트 크기 보정 배율:", self.font_size_scale_spin)

            self.keep_temp_checkbox = QCheckBox("변환 후 임시 파일 유지")
            option_layout.addRow("", self.keep_temp_checkbox)

            root_layout.addWidget(option_group)

            action_row = QHBoxLayout()
            self.convert_btn = QPushButton("변환 시작")
            self.convert_btn.clicked.connect(self._start_conversion)
            action_row.addWidget(self.convert_btn)
            root_layout.addLayout(action_row)

            progress_group = QGroupBox("진행 상태")
            progress_layout = QVBoxLayout(progress_group)

            self.page_status_label = QLabel("대기 중")
            progress_layout.addWidget(self.page_status_label)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            progress_layout.addWidget(self.progress_bar)

            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)
            self.log_text.setMinimumHeight(220)
            progress_layout.addWidget(self.log_text)

            root_layout.addWidget(progress_group, stretch=1)

        def _append_log(self, message: str) -> None:
            self.log_text.append(message)

        def _select_pdf_file(self) -> None:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "PDF 파일 선택",
                "",
                "PDF Files (*.pdf);;All Files (*)",
            )
            if not file_path:
                return

            self.pdf_path = file_path
            self.pdf_path_edit.setText(file_path)

            base, _ = os.path.splitext(file_path)
            auto_output = base + ".pptx"
            self.output_path = auto_output
            self.output_path_edit.setText(auto_output)
            self._append_log(f"PDF 선택: {file_path}")
            self._append_log(f"자동 저장 PPTX: {auto_output}")

        def _select_output_path(self) -> None:
            initial = self.output_path_edit.text().strip()
            if not initial and self.pdf_path:
                base, _ = os.path.splitext(self.pdf_path)
                initial = base + ".pptx"

            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "PPTX 저장 경로 선택",
                initial,
                "PowerPoint Files (*.pptx);;All Files (*)",
            )
            if not file_path:
                return

            if not file_path.lower().endswith(".pptx"):
                file_path = file_path + ".pptx"

            self.output_path = file_path
            self.output_path_edit.setText(file_path)
            self._append_log(f"저장 경로 설정: {file_path}")

        def _get_render_scale(self) -> float:
            text = self.render_scale_combo.currentText()
            if text.startswith("3"):
                return 3.0
            if text.startswith("1.5"):
                return 1.5
            return 2.0

        def _set_ui_busy(self, busy: bool) -> None:
            self.convert_btn.setEnabled(not busy)
            self.font_combo.setEnabled(not busy)

        def _start_conversion(self) -> None:
            pdf_path = self.pdf_path_edit.text().strip()
            output_path = self.output_path_edit.text().strip()

            if not pdf_path:
                QMessageBox.warning(self, "입력 오류", "PDF 파일을 선택해 주세요.")
                return
            if not output_path:
                QMessageBox.warning(self, "입력 오류", "저장 경로를 지정해 주세요.")
                return
            if not os.path.isfile(pdf_path):
                QMessageBox.critical(
                    self,
                    "파일 오류",
                    f"PDF 파일을 열 수 없습니다:\n{pdf_path}",
                )
                return

            if self.worker is not None and self.worker.isRunning():
                QMessageBox.information(self, "진행 중", "이미 변환이 진행 중입니다.")
                return

            settings = ConversionSettings(
                pdf_path=pdf_path,
                output_pptx_path=output_path,
                font_name=self.font_combo.currentText() or DEFAULT_FONT_OPTION,
                render_scale=self._get_render_scale(),
                min_confidence=float(self.confidence_spin.value()),
                use_gpu=self.gpu_combo.currentIndex() == 1,
                mask_expand_px=int(self.mask_expand_spin.value()),
                inpaint_radius=int(self.inpaint_radius_spin.value()),
                font_size_scale=float(self.font_size_scale_spin.value()),
                keep_temp_files=self.keep_temp_checkbox.isChecked(),
            )

            self.progress_bar.setValue(0)
            self.page_status_label.setText("변환 준비 중...")
            self._append_log("=" * 40)
            self._append_log("변환을 시작합니다.")
            self._set_ui_busy(True)

            self.worker = ConverterWorker(settings)
            self.worker.progress_changed.connect(self.progress_bar.setValue)
            self.worker.page_status_changed.connect(self.page_status_label.setText)
            self.worker.log_message.connect(self._append_log)
            self.worker.conversion_finished.connect(self._on_conversion_finished)
            self.worker.conversion_failed.connect(self._on_conversion_failed)
            self.worker.start()

        def _on_conversion_finished(self, saved_path: str) -> None:
            self._set_ui_busy(False)
            self.page_status_label.setText("변환 완료")
            self.progress_bar.setValue(100)
            QMessageBox.information(
                self,
                "변환 완료",
                f"PPTX 파일이 저장되었습니다.\n\n{saved_path}",
            )

        def _on_conversion_failed(self, error_message: str) -> None:
            self._set_ui_busy(False)
            self.page_status_label.setText("변환 실패")
            self._append_log(f"[오류] {error_message}")
            QMessageBox.critical(self, "변환 실패", error_message)

        def closeEvent(self, event: QCloseEvent) -> None:
            if self.worker is not None and self.worker.isRunning():
                reply = QMessageBox.question(
                    self,
                    "변환 진행 중",
                    "변환이 진행 중입니다. 종료하시겠습니까?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self.worker.request_cancel()
                    self.worker.wait(3000)
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()

    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        window = MainWindow()
        window.show()
        return app.exec_()
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

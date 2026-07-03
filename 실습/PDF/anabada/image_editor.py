"""
간단한 이미지 편집기
PyQt5 + Pillow(PIL) 기반 데스크톱 애플리케이션

실행 방법:
    pip install PyQt5 Pillow
    python image_editor.py
"""

import sys

from PIL import Image
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# 이미지 뷰어 위젯
# ---------------------------------------------------------------------------
class ImageViewer(QScrollArea):
    """
    좌측 이미지 미리보기 영역.

    QScrollArea 안에 QLabel을 두어, 창 크기가 변해도 이미지 비율(aspect ratio)을
    유지한 채로 가능한 한 크게 표시한다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #2b2b2b;")

        # 실제 이미지를 그리는 QLabel
        self._label = QLabel("이미지를 업로드해 주세요.")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._label.setMinimumSize(200, 200)
        self.setWidget(self._label)

        # 원본 해상도 QPixmap (스케일링 전)
        self._source_pixmap = None

    def set_image(self, pil_image: Image.Image):
        """
        Pillow Image 객체를 받아 뷰어에 표시한다.

        PIL -> QImage -> QPixmap 변환 후, 현재 뷰포트 크기에 맞춰
        Qt.KeepAspectRatio 옵션으로 비율을 유지하며 축소/확대한다.
        """
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        width, height = pil_image.size
        # QImage.Format_RGB888: 픽셀당 R,G,B 3바이트
        qimage = QImage(
            pil_image.tobytes("raw", "RGB"),
            width,
            height,
            width * 3,
            QImage.Format_RGB888,
        )
        self._source_pixmap = QPixmap.fromImage(qimage)
        self._refresh_scaled_pixmap()

    def clear_image(self):
        """뷰어를 초기 안내 문구 상태로 되돌린다."""
        self._source_pixmap = None
        self._label.setText("이미지를 업로드해 주세요.")
        self._label.setPixmap(QPixmap())

    def _refresh_scaled_pixmap(self):
        """뷰포트(스크롤 영역) 크기에 맞춰 pixmap을 다시 스케일링한다."""
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return

        viewport = self.viewport()
        scaled = self._source_pixmap.scaled(
            viewport.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.setMinimumSize(scaled.size())

    def resizeEvent(self, event):
        """창 크기 변경 시 이미지 스케일을 다시 계산한다."""
        super().resizeEvent(event)
        self._refresh_scaled_pixmap()


# ---------------------------------------------------------------------------
# 메인 윈도우
# ---------------------------------------------------------------------------
class ImageEditorWindow(QMainWindow):
    """
    이미지 편집기 메인 윈도우.

    [이미지 처리 파이프라인]
    1. 업로드 시 Pillow로 이미지를 열어 self.original_image 에 보관한다.
       -> 이 객체는 RGB 슬라이더 조작으로 직접 수정하지 않는다 (불변 원본).
    2. 슬라이더 변경 시 original_image.copy() 로 복사본을 만든 뒤,
       채널별 곱셈 보정을 적용해 미리보기만 갱신한다.
    3. '크기 적용' 시 original_image 자체를 리사이즈하여 새 기준 이미지로 삼는다.
    4. '결과 저장' 시 현재 미리보기(= RGB가 적용된 최종 결과)를 파일로 저장한다.
    """

    # RGB 슬라이더 기본값: 100 = 변화 없음 (곱셈 계수 1.0)
    SLIDER_DEFAULT = 100
    SLIDER_MIN = 0
    SLIDER_MAX = 200

    def __init__(self):
        super().__init__()
        self.setWindowTitle("간단한 이미지 편집기")
        self.resize(1000, 650)

        # Pillow 원본 이미지 (업로드/리사이즈 후의 기준 이미지, RGB로 직접 훼손하지 않음)
        self.original_image = None

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _build_ui(self):
        """좌측 뷰어 + 우측 컨트롤 패널 레이아웃을 구성한다."""
        central = QWidget()
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(16)

        # ---- 좌측: 이미지 뷰어 ----
        self.viewer = ImageViewer()
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root_layout.addWidget(self.viewer, stretch=3)

        # ---- 우측: 컨트롤 패널 ----
        control_panel = QWidget()
        control_panel.setFixedWidth(320)
        control_layout = QVBoxLayout(control_panel)
        control_layout.setSpacing(14)

        font = QFont()
        font.setPointSize(15)
        self.setFont(font)

        # [1] 이미지 업로드
        upload_group = QGroupBox("파일")
        upload_layout = QVBoxLayout(upload_group)
        self.btn_upload = QPushButton("이미지 업로드")
        upload_layout.addWidget(self.btn_upload)
        control_layout.addWidget(upload_group)

        # [2] RGB 컬러 조정 슬라이더
        rgb_group = QGroupBox("컬러 조정 (RGB)")
        rgb_layout = QVBoxLayout(rgb_group)

        self.slider_red, self.label_red = self._create_rgb_slider("Red", (200, 80, 80))
        self.slider_green, self.label_green = self._create_rgb_slider("Green", (80, 180, 80))
        self.slider_blue, self.label_blue = self._create_rgb_slider("Blue", (80, 120, 220))

        rgb_layout.addWidget(self.label_red)
        rgb_layout.addWidget(self.slider_red)
        rgb_layout.addWidget(self.label_green)
        rgb_layout.addWidget(self.slider_green)
        rgb_layout.addWidget(self.label_blue)
        rgb_layout.addWidget(self.slider_blue)
        control_layout.addWidget(rgb_group)

        # [3] 크기 조정
        resize_group = QGroupBox("크기 조정 (픽셀)")
        resize_layout = QVBoxLayout(resize_group)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Width (X):"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 99999)
        self.spin_width.setValue(800)
        width_row.addWidget(self.spin_width)

        height_row = QHBoxLayout()
        height_row.addWidget(QLabel("Height (Y):"))
        self.spin_height = QSpinBox()
        self.spin_height.setRange(1, 99999)
        self.spin_height.setValue(600)
        height_row.addWidget(self.spin_height)

        self.btn_resize = QPushButton("크기 적용")
        resize_layout.addLayout(width_row)
        resize_layout.addLayout(height_row)
        resize_layout.addWidget(self.btn_resize)
        control_layout.addWidget(resize_group)

        # [4] 결과 저장
        save_group = QGroupBox("저장")
        save_layout = QVBoxLayout(save_group)
        self.btn_save = QPushButton("결과 저장")
        save_layout.addWidget(self.btn_save)
        control_layout.addWidget(save_group)

        control_layout.addStretch()
        root_layout.addWidget(control_panel, stretch=0)

        # 초기에는 편집 관련 버튼 비활성화
        self._set_editing_enabled(False)

    def _create_rgb_slider(self, channel_name: str, color_rgb: tuple):
        """
        채널별 RGB 슬라이더와 현재 값을 표시하는 QLabel을 생성한다.

        슬라이더 범위 0~200, 기본값 100:
          - 100 -> 곱셈 계수 1.0 (원본과 동일)
          - 150 -> 1.5배 밝게
          -  50 -> 0.5배 어둡게
        """
        value_label = QLabel(f"{channel_name}: {self.SLIDER_DEFAULT}")
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(self.SLIDER_MIN)
        slider.setMaximum(self.SLIDER_MAX)
        slider.setValue(self.SLIDER_DEFAULT)
        slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height: 8px; background: #ddd; border-radius: 4px; }}"
            f"QSlider::handle:horizontal {{ background: rgb{color_rgb}; width: 18px; margin: -5px 0; border-radius: 9px; }}"
        )
        return slider, value_label

    def _connect_signals(self):
        """버튼·슬라이더 시그널을 각 처리 메서드에 연결한다."""
        self.btn_upload.clicked.connect(self.upload_image)
        self.btn_resize.clicked.connect(self.apply_resize)
        self.btn_save.clicked.connect(self.save_image)

        self.slider_red.valueChanged.connect(self._on_rgb_changed)
        self.slider_green.valueChanged.connect(self._on_rgb_changed)
        self.slider_blue.valueChanged.connect(self._on_rgb_changed)

    def _set_editing_enabled(self, enabled: bool):
        """이미지가 없을 때는 편집/저장 컨트롤을 비활성화한다."""
        self.slider_red.setEnabled(enabled)
        self.slider_green.setEnabled(enabled)
        self.slider_blue.setEnabled(enabled)
        self.btn_resize.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    # ------------------------------------------------------------------
    # RGB 실시간 처리 (핵심 로직)
    # ------------------------------------------------------------------
    def _on_rgb_changed(self):
        """
        RGB 슬라이더 값이 바뀔 때마다 호출된다.

        원본(self.original_image)은 건드리지 않고,
        복사본에만 채널별 보정을 적용한 뒤 뷰어를 갱신한다.
        """
        if self.original_image is None:
            return

        self.label_red.setText(f"Red: {self.slider_red.value()}")
        self.label_green.setText(f"Green: {self.slider_green.value()}")
        self.label_blue.setText(f"Blue: {self.slider_blue.value()}")

        preview = self._apply_rgb_adjustment(
            self.original_image,
            self.slider_red.value(),
            self.slider_green.value(),
            self.slider_blue.value(),
        )
        self.viewer.set_image(preview)

    def _apply_rgb_adjustment(
        self,
        source: Image.Image,
        red_value: int,
        green_value: int,
        blue_value: int,
    ) -> Image.Image:
        """
        Pillow를 이용해 RGB 채널별 밝기를 조절한다.

        [동작 원리]
        1. source.copy() 로 원본과 분리된 복사본을 만든다.
        2. RGB 모드로 변환 후 R, G, B 채널을 각각 분리(split)한다.
        3. 각 채널 픽셀값에 (슬라이더값 / 100) 계수를 곱한다.
           예) Red 슬라이더 120 -> R 채널 픽셀 * 1.2
        4. point() 로 픽셀 단위 연산 후, merge() 로 다시 RGB 이미지를 합친다.
        5. 결과값은 0~255 범위로 clamp 한다.

        Parameters
        ----------
        source : PIL.Image
            보정 대상 원본(복사 전 원본 객체, 직접 수정하지 않음)
        red_value, green_value, blue_value : int
            슬라이더 값 (0~200, 100=변화 없음)

        Returns
        -------
        PIL.Image
            RGB 보정이 적용된 새 이미지
        """
        img = source.copy()
        if img.mode != "RGB":
            img = img.convert("RGB")

        r_factor = red_value / 100.0
        g_factor = green_value / 100.0
        b_factor = blue_value / 100.0

        r_channel, g_channel, b_channel = img.split()

        # point(lambda): 각 픽셀에 함수를 적용. min(255, ...) 로 상한 클램프.
        r_channel = r_channel.point(lambda px: min(255, int(px * r_factor)))
        g_channel = g_channel.point(lambda px: min(255, int(px * g_factor)))
        b_channel = b_channel.point(lambda px: min(255, int(px * b_factor)))

        return Image.merge("RGB", (r_channel, g_channel, b_channel))

    def _get_current_result_image(self) -> Image.Image:
        """
        현재 슬라이더 설정이 반영된 최종 결과 이미지를 반환한다.
        저장 및 리사이즈 미리보기 갱신에 사용한다.
        """
        if self.original_image is None:
            return None
        return self._apply_rgb_adjustment(
            self.original_image,
            self.slider_red.value(),
            self.slider_green.value(),
            self.slider_blue.value(),
        )

    def _reset_rgb_sliders(self):
        """RGB 슬라이더를 기본값(100)으로 되돌린다."""
        self.slider_red.blockSignals(True)
        self.slider_green.blockSignals(True)
        self.slider_blue.blockSignals(True)

        self.slider_red.setValue(self.SLIDER_DEFAULT)
        self.slider_green.setValue(self.SLIDER_DEFAULT)
        self.slider_blue.setValue(self.SLIDER_DEFAULT)

        self.slider_red.blockSignals(False)
        self.slider_green.blockSignals(False)
        self.slider_blue.blockSignals(False)

        self.label_red.setText(f"Red: {self.SLIDER_DEFAULT}")
        self.label_green.setText(f"Green: {self.SLIDER_DEFAULT}")
        self.label_blue.setText(f"Blue: {self.SLIDER_DEFAULT}")

    # ------------------------------------------------------------------
    # 파일 업로드 / 리사이즈 / 저장
    # ------------------------------------------------------------------
    def upload_image(self):
        """QFileDialog로 로컬 이미지를 선택해 불러온다."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "이미지 선택",
            "",
            "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;모든 파일 (*.*)",
        )
        if not file_path:
            return

        try:
            loaded = Image.open(file_path)
            # GIF 등 팔레트/RGBA 이미지도 RGB 편집 파이프라인에 맞게 변환
            self.original_image = loaded.convert("RGB")
        except Exception as exc:
            QMessageBox.critical(self, "오류", f"이미지를 불러올 수 없습니다.\n{exc}")
            return

        width, height = self.original_image.size
        self.spin_width.setValue(width)
        self.spin_height.setValue(height)

        self._reset_rgb_sliders()
        self._set_editing_enabled(True)
        self.viewer.set_image(self.original_image)

    def apply_resize(self):
        """
        SpinBox에 입력된 Width/Height 픽셀 크기로 original_image 를 리사이즈한다.

        리사이즈는 RGB 보정이 적용되기 '전' 기준 이미지(original_image)에 수행되며,
        이후 슬라이더 값에 따라 다시 실시간 미리보기가 갱신된다.
        """
        if self.original_image is None:
            return

        new_width = self.spin_width.value()
        new_height = self.spin_height.value()

        if new_width < 1 or new_height < 1:
            QMessageBox.warning(self, "입력 오류", "너비와 높이는 1 이상이어야 합니다.")
            return

        try:
            self.original_image = self.original_image.resize(
                (new_width, new_height),
                Image.Resampling.LANCZOS,
            )
        except Exception as exc:
            QMessageBox.critical(self, "오류", f"리사이즈에 실패했습니다.\n{exc}")
            return

        # 리사이즈 후 현재 RGB 슬라이더 설정을 반영한 미리보기 표시
        preview = self._get_current_result_image()
        self.viewer.set_image(preview)

    def save_image(self):
        """현재 편집 결과(컬러 + 크기 반영)를 사용자가 선택한 포맷으로 저장한다."""
        result = self._get_current_result_image()
        if result is None:
            QMessageBox.warning(self, "알림", "저장할 이미지가 없습니다.")
            return

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "결과 저장",
            "",
            "JPEG (*.jpg);;PNG (*.png);;GIF (*.gif)",
        )
        if not file_path:
            return

        try:
            save_image = result.copy()

            # 선택된 확장자/필터에 맞게 포맷 결정
            lower_path = file_path.lower()
            if selected_filter.startswith("JPEG") or lower_path.endswith((".jpg", ".jpeg")):
                if not lower_path.endswith((".jpg", ".jpeg")):
                    file_path += ".jpg"
                save_image.save(file_path, format="JPEG", quality=95)
            elif selected_filter.startswith("GIF") or lower_path.endswith(".gif"):
                if not lower_path.endswith(".gif"):
                    file_path += ".gif"
                # GIF는 팔레트 모드가 필요할 수 있음
                save_image = save_image.convert("P", palette=Image.ADAPTIVE)
                save_image.save(file_path, format="GIF")
            else:
                if not lower_path.endswith(".png"):
                    file_path += ".png"
                save_image.save(file_path, format="PNG")

            QMessageBox.information(self, "완료", f"이미지가 저장되었습니다.\n{file_path}")
        except Exception as exc:
            QMessageBox.critical(self, "오류", f"저장에 실패했습니다.\n{exc}")


# ---------------------------------------------------------------------------
# 애플리케이션 진입점
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = ImageEditorWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

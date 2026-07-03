#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDF 분할/병합 프로그램

PyQt5 기반 데스크톱 앱으로 PDF 파일을 미리보기하고,
범위/페이지/고정 단위로 분할하거나 여러 PDF를 병합할 수 있습니다.

실행 방법:
    python pdf_split_merge_app.py
"""

import os
import sys
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# PDF 처리 라이브러리 (pypdf 우선, 없으면 PyPDF2 사용)
# ---------------------------------------------------------------------------
try:
    from pypdf import PdfReader, PdfWriter, PdfMerger
    PDF_LIB = "pypdf"
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter, PdfMerger
        PDF_LIB = "PyPDF2"
    except ImportError:
        print("오류: pypdf 또는 PyPDF2 패키지가 필요합니다.")
        print("설치: pip install pypdf  또는  pip install PyPDF2")
        sys.exit(1)

# PyMuPDF (썸네일 미리보기용)
try:
    import fitz  # PyMuPDF
except ImportError:
    print("오류: PyMuPDF 패키지가 필요합니다.")
    print("설치: pip install PyMuPDF")
    sys.exit(1)

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
THUMBNAIL_WIDTH = 150          # 썸네일 가로 크기 (px)
APP_TITLE = "PDF 분할/병합 프로그램"


# ---------------------------------------------------------------------------
# PDF 처리 유틸리티
# ---------------------------------------------------------------------------
class PDFProcessor:
    """PDF 읽기, 분할, 병합을 담당하는 클래스"""

    @staticmethod
    def is_pdf_file(file_path: str) -> bool:
        """파일 확장자가 PDF인지 확인"""
        return file_path.lower().endswith(".pdf")

    @staticmethod
    def open_reader(file_path: str) -> PdfReader:
        """
        PDF 파일을 열어 PdfReader 객체를 반환합니다.
        암호화된 PDF 등 열 수 없는 경우 예외를 발생시킵니다.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        if not PDFProcessor.is_pdf_file(file_path):
            raise ValueError("PDF 파일만 선택할 수 있습니다.")

        try:
            reader = PdfReader(file_path)
        except Exception as exc:
            raise ValueError(
                f"PDF 파일을 열 수 없습니다.\n"
                f"암호화된 PDF이거나 손상된 파일일 수 있습니다.\n\n{exc}"
            ) from exc

        # 암호화된 PDF 확인
        if getattr(reader, "is_encrypted", False):
            try:
                # 빈 비밀번호로 열기 시도
                if reader.decrypt("") == 0:
                    raise ValueError(
                        "암호화된 PDF입니다. 비밀번호가 필요한 파일은 처리할 수 없습니다."
                    )
            except Exception as exc:
                raise ValueError(
                    "암호화된 PDF이거나 읽기 어려운 PDF입니다.\n"
                    "비밀번호가 설정된 파일은 지원하지 않습니다."
                ) from exc

        if len(reader.pages) == 0:
            raise ValueError("페이지가 없는 PDF 파일입니다.")

        return reader

    @staticmethod
    def get_page_count(file_path: str) -> int:
        """PDF 전체 페이지 수 반환"""
        reader = PDFProcessor.open_reader(file_path)
        return len(reader.pages)

    @staticmethod
    def save_pages(reader: PdfReader, page_indices: List[int], output_path: str) -> None:
        """
        지정한 페이지 인덱스(0부터 시작)만 추출해 새 PDF로 저장합니다.
        """
        writer = PdfWriter()
        total = len(reader.pages)

        for idx in page_indices:
            if idx < 0 or idx >= total:
                raise ValueError(
                    f"페이지 번호가 범위를 벗어났습니다. (1~{total} 페이지)"
                )
            writer.add_page(reader.pages[idx])

        with open(output_path, "wb") as out_file:
            writer.write(out_file)

    @staticmethod
    def split_by_range(
        file_path: str, start_page: int, end_page: int, output_path: str
    ) -> None:
        """
        범위 분할: start_page ~ end_page (사용자 기준 1부터 시작)
        """
        reader = PDFProcessor.open_reader(file_path)
        total = len(reader.pages)

        if start_page < 1 or end_page < 1:
            raise ValueError("페이지 번호는 1 이상이어야 합니다.")

        if start_page > end_page:
            raise ValueError("시작 페이지가 끝 페이지보다 클 수 없습니다.")

        if end_page > total:
            raise ValueError(
                f"페이지 번호가 전체 페이지 수({total})를 초과했습니다."
            )

        indices = list(range(start_page - 1, end_page))
        PDFProcessor.save_pages(reader, indices, output_path)

    @staticmethod
    def split_by_pages(file_path: str, page_numbers: List[int], output_path: str) -> None:
        """
        페이지 입력 분할: 지정한 페이지 번호들만 추출 (사용자 기준 1부터 시작)
        """
        reader = PDFProcessor.open_reader(file_path)
        total = len(reader.pages)

        # 중복 제거 (입력 순서 유지)
        seen = set()
        unique_pages = []
        for num in page_numbers:
            if num not in seen:
                seen.add(num)
                unique_pages.append(num)

        for num in unique_pages:
            if num < 1:
                raise ValueError("페이지 번호는 1 이상이어야 합니다.")
            if num > total:
                raise ValueError(
                    f"페이지 번호 {num}이(가) 전체 페이지 수({total})를 초과했습니다."
                )

        indices = [num - 1 for num in unique_pages]
        PDFProcessor.save_pages(reader, indices, output_path)

    @staticmethod
    def split_by_fixed_size(
        file_path: str, chunk_size: int, output_dir: str
    ) -> List[str]:
        """
        고정 페이지 단위 분할
        파일명: 원본파일명_시작페이지_끝페이지.pdf
        """
        if chunk_size < 1:
            raise ValueError("분할 페이지 수는 1 이상이어야 합니다.")

        reader = PDFProcessor.open_reader(file_path)
        total = len(reader.pages)

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        saved_files = []

        start = 1
        while start <= total:
            end = min(start + chunk_size - 1, total)
            output_name = f"{base_name}_{start}_{end}.pdf"
            output_path = os.path.join(output_dir, output_name)

            indices = list(range(start - 1, end))
            PDFProcessor.save_pages(reader, indices, output_path)
            saved_files.append(output_path)
            start = end + 1

        return saved_files

    @staticmethod
    def merge_pdfs(file_paths: List[str], output_path: str) -> None:
        """여러 PDF를 선택 순서대로 병합"""
        if len(file_paths) < 2:
            raise ValueError("병합하려면 PDF 파일이 2개 이상 필요합니다.")

        merger = PdfMerger()

        try:
            for path in file_paths:
                if not os.path.isfile(path):
                    raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
                if not PDFProcessor.is_pdf_file(path):
                    raise ValueError(f"PDF 파일이 아닙니다: {path}")

                # 각 파일이 열리는지 사전 확인
                PDFProcessor.open_reader(path)
                merger.append(path)

            with open(output_path, "wb") as out_file:
                merger.write(out_file)
        except Exception:
            raise
        finally:
            merger.close()


# ---------------------------------------------------------------------------
# 입력값 파싱
# ---------------------------------------------------------------------------
def parse_range_input(text: str) -> Tuple[int, int]:
    """
    '1-3' 형식의 범위 입력을 파싱합니다.
    반환: (시작페이지, 끝페이지) - 사용자 기준 1부터 시작
    """
    text = text.strip()
    if not text:
        raise ValueError("페이지 범위를 입력해주세요.")

    if "-" not in text:
        raise ValueError("페이지 범위는 '시작페이지-끝페이지' 형식이어야 합니다. (예: 1-3)")

    parts = text.split("-")
    if len(parts) != 2:
        raise ValueError("페이지 범위 형식이 올바르지 않습니다. (예: 1-3)")

    try:
        start = int(parts[0].strip())
        end = int(parts[1].strip())
    except ValueError as exc:
        raise ValueError("페이지 번호는 숫자여야 합니다.") from exc

    return start, end


def parse_pages_input(text: str) -> List[int]:
    """
    '1,3,5' 형식의 페이지 번호 입력을 파싱합니다.
    """
    text = text.strip()
    if not text:
        raise ValueError("페이지 번호를 입력해주세요.")

    parts = [p.strip() for p in text.split(",") if p.strip()]
    if not parts:
        raise ValueError("페이지 번호를 입력해주세요.")

    page_numbers = []
    for part in parts:
        try:
            page_numbers.append(int(part))
        except ValueError as exc:
            raise ValueError(
                f"페이지 번호 형식이 올바르지 않습니다: '{part}'"
            ) from exc

    return page_numbers


def parse_fixed_size_input(text: str) -> int:
    """고정 페이지 단위 분할용 숫자 입력 파싱"""
    text = text.strip()
    if not text:
        raise ValueError("분할 페이지 수를 입력해주세요.")

    try:
        size = int(text)
    except ValueError as exc:
        raise ValueError("분할 페이지 수는 숫자여야 합니다.") from exc

    if size < 1:
        raise ValueError("분할 페이지 수는 1 이상이어야 합니다.")

    return size


# ---------------------------------------------------------------------------
# 썸네일 생성 워커 (백그라운드 스레드)
# ---------------------------------------------------------------------------
class ThumbnailWorker(QThread):
    """
    PDF 페이지 썸네일을 백그라운드에서 생성합니다.
    UI가 멈추지 않도록 QThread를 사용합니다.
    """

    # (페이지번호, QPixmap) 또는 (페이지번호, None) - 실패 시
    thumbnail_ready = pyqtSignal(int, object)
    progress = pyqtSignal(int, int)       # (현재, 전체)
    finished_all = pyqtSignal(list)       # 실패한 페이지 번호 목록
    error = pyqtSignal(str)

    def __init__(self, pdf_path: str, parent=None):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        failed_pages = []

        try:
            doc = fitz.open(self.pdf_path)
        except Exception as exc:
            self.error.emit(
                f"PDF 미리보기를 생성할 수 없습니다.\n"
                f"암호화된 PDF이거나 읽기 어려운 PDF일 수 있습니다.\n\n{exc}"
            )
            return

        total = len(doc)

        try:
            for page_num in range(total):
                if self._is_cancelled:
                    break

                user_page = page_num + 1  # 사용자 기준 1부터 시작
                self.progress.emit(user_page, total)

                try:
                    page = doc.load_page(page_num)
                    pixmap = self._render_page_to_qpixmap(page)
                    self.thumbnail_ready.emit(user_page, pixmap)
                except Exception:
                    failed_pages.append(user_page)
                    self.thumbnail_ready.emit(user_page, None)

        finally:
            doc.close()

        if not self._is_cancelled:
            self.finished_all.emit(failed_pages)

    def _render_page_to_qpixmap(self, page) -> QPixmap:
        """PyMuPDF 페이지를 QPixmap 썸네일로 변환 (가로 150px 기준)"""
        rect = page.rect
        if rect.width <= 0:
            raise ValueError("페이지 크기를 읽을 수 없습니다.")

        zoom = THUMBNAIL_WIDTH / rect.width
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        # PyMuPDF pixmap -> QImage -> QPixmap
        image = QImage(
            pix.samples,
            pix.width,
            pix.height,
            pix.stride,
            QImage.Format_RGB888,
        )
        return QPixmap.fromImage(image.copy())


# ---------------------------------------------------------------------------
# 메인 윈도우
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    """PDF 분할/병합 프로그램 메인 화면"""

    def __init__(self):
        super().__init__()
        self.current_pdf_path: Optional[str] = None
        self.page_count: int = 0
        self.thumbnail_worker: Optional[ThumbnailWorker] = None
        self.merge_files: List[str] = []

        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1000, 650)
        self.resize(1100, 720)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # 왼쪽: 업로드 및 미리보기
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel, stretch=3)

        # 오른쪽: 분할/병합 탭
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, stretch=2)

    # ------------------------------------------------------------------
    # 왼쪽 패널
    # ------------------------------------------------------------------
    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title_label = QLabel(f"<h2>{APP_TITLE}</h2>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        upload_btn = QPushButton("PDF 업로드")
        upload_btn.clicked.connect(self.upload_pdf)
        layout.addWidget(upload_btn)

        self.path_label = QLabel("선택된 파일: (없음)")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #333;")
        layout.addWidget(self.path_label)

        self.page_count_label = QLabel("전체 페이지 수: -")
        layout.addWidget(self.page_count_label)

        preview_group = QGroupBox("페이지 미리보기")
        preview_layout = QVBoxLayout(preview_group)

        self.thumbnail_scroll = QScrollArea()
        self.thumbnail_scroll.setWidgetResizable(True)
        self.thumbnail_scroll.setMinimumHeight(400)

        self.thumbnail_container = QWidget()
        self.thumbnail_layout = QVBoxLayout(self.thumbnail_container)
        self.thumbnail_layout.setAlignment(Qt.AlignTop)

        placeholder = QLabel("PDF를 업로드하면 페이지 썸네일이 표시됩니다.")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("color: #888; padding: 40px;")
        self.thumbnail_layout.addWidget(placeholder)
        self.thumbnail_placeholder = placeholder

        self.thumbnail_scroll.setWidget(self.thumbnail_container)
        preview_layout.addWidget(self.thumbnail_scroll)

        self.preview_status_label = QLabel("")
        self.preview_status_label.setStyleSheet("color: #666;")
        preview_layout.addWidget(self.preview_status_label)

        layout.addWidget(preview_group)
        return panel

    # ------------------------------------------------------------------
    # 오른쪽 패널 (탭)
    # ------------------------------------------------------------------
    def _create_right_panel(self) -> QWidget:
        tabs = QTabWidget()

        tabs.addTab(self._create_split_tab(), "PDF 분할")
        tabs.addTab(self._create_merge_tab(), "PDF 병합")

        return tabs

    def _create_split_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # --- 범위 입력 분할 ---
        range_group = QGroupBox("범위 입력 분할 (예: 1-3)")
        range_layout = QVBoxLayout(range_group)

        self.range_input = QLineEdit()
        self.range_input.setPlaceholderText("1-3")
        range_layout.addWidget(self.range_input)

        range_btn = QPushButton("범위 분할 실행")
        range_btn.clicked.connect(self.split_by_range)
        range_layout.addWidget(range_btn)

        layout.addWidget(range_group)

        # --- 페이지 입력 분할 ---
        pages_group = QGroupBox("페이지 입력 분할 (예: 1,3,5)")
        pages_layout = QVBoxLayout(pages_group)

        self.pages_input = QLineEdit()
        self.pages_input.setPlaceholderText("1,3,5")
        pages_layout.addWidget(self.pages_input)

        pages_btn = QPushButton("페이지 분할 실행")
        pages_btn.clicked.connect(self.split_by_pages)
        pages_layout.addWidget(pages_btn)

        layout.addWidget(pages_group)

        # --- 고정 페이지 단위 분할 ---
        fixed_group = QGroupBox("고정 페이지 단위 분할 (예: 2)")
        fixed_layout = QVBoxLayout(fixed_group)

        self.fixed_input = QLineEdit()
        self.fixed_input.setPlaceholderText("2")
        fixed_layout.addWidget(self.fixed_input)

        fixed_btn = QPushButton("고정 단위 분할 실행")
        fixed_btn.clicked.connect(self.split_by_fixed_size)
        fixed_layout.addWidget(fixed_btn)

        layout.addWidget(fixed_group)
        layout.addStretch()

        return tab

    def _create_merge_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        select_btn = QPushButton("병합할 PDF 파일 선택")
        select_btn.clicked.connect(self.select_merge_files)
        layout.addWidget(select_btn)

        layout.addWidget(QLabel("선택된 파일 목록 (위에서 아래 순서로 병합):"))

        self.merge_list = QListWidget()
        self.merge_list.setMinimumHeight(250)
        layout.addWidget(self.merge_list)

        btn_row1 = QHBoxLayout()
        up_btn = QPushButton("위로 이동")
        up_btn.clicked.connect(self.move_merge_item_up)
        down_btn = QPushButton("아래로 이동")
        down_btn.clicked.connect(self.move_merge_item_down)
        btn_row1.addWidget(up_btn)
        btn_row1.addWidget(down_btn)
        layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        remove_btn = QPushButton("선택 파일 제거")
        remove_btn.clicked.connect(self.remove_merge_item)
        clear_btn = QPushButton("전체 목록 초기화")
        clear_btn.clicked.connect(self.clear_merge_list)
        btn_row2.addWidget(remove_btn)
        btn_row2.addWidget(clear_btn)
        layout.addLayout(btn_row2)

        merge_btn = QPushButton("병합하기")
        merge_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        merge_btn.clicked.connect(self.merge_pdfs)
        layout.addWidget(merge_btn)

        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # PDF 업로드 및 미리보기
    # ------------------------------------------------------------------
    def upload_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "PDF 파일 선택",
            "",
            "PDF 파일 (*.pdf);;모든 파일 (*.*)",
        )

        if not file_path:
            return

        if not PDFProcessor.is_pdf_file(file_path):
            QMessageBox.warning(self, "오류", "PDF 파일만 선택할 수 있습니다.")
            return

        try:
            self.page_count = PDFProcessor.get_page_count(file_path)
        except ValueError as exc:
            QMessageBox.warning(self, "PDF 열기 오류", str(exc))
            return
        except Exception as exc:
            QMessageBox.warning(
                self,
                "오류",
                f"PDF 파일을 처리하는 중 오류가 발생했습니다.\n\n{exc}",
            )
            return

        self.current_pdf_path = file_path
        self.path_label.setText(f"선택된 파일: {file_path}")
        self.page_count_label.setText(f"전체 페이지 수: {self.page_count}")

        self._clear_thumbnails()
        self._start_thumbnail_generation(file_path)

    def _clear_thumbnails(self):
        """썸네일 영역 초기화"""
        if self.thumbnail_worker and self.thumbnail_worker.isRunning():
            self.thumbnail_worker.cancel()
            self.thumbnail_worker.wait()

        while self.thumbnail_layout.count():
            item = self.thumbnail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.thumbnail_placeholder = None
        self.preview_status_label.setText("")

    def _start_thumbnail_generation(self, file_path: str):
        """백그라운드에서 썸네일 생성 시작"""
        self.preview_status_label.setText("썸네일 생성 중...")

        self.thumbnail_worker = ThumbnailWorker(file_path, self)
        self.thumbnail_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumbnail_worker.progress.connect(self._on_thumbnail_progress)
        self.thumbnail_worker.finished_all.connect(self._on_thumbnails_finished)
        self.thumbnail_worker.error.connect(self._on_thumbnail_error)
        self.thumbnail_worker.start()

    def _on_thumbnail_ready(self, page_num: int, pixmap: Optional[QPixmap]):
        """썸네일 한 장이 준비되면 화면에 추가"""
        item_widget = QWidget()
        item_layout = QVBoxLayout(item_widget)
        item_layout.setAlignment(Qt.AlignCenter)

        if pixmap is not None:
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setAlignment(Qt.AlignCenter)
            img_label.setFixedWidth(THUMBNAIL_WIDTH + 10)
            item_layout.addWidget(img_label)
        else:
            error_label = QLabel("[미리보기 실패]")
            error_label.setAlignment(Qt.AlignCenter)
            error_label.setStyleSheet("color: red;")
            item_layout.addWidget(error_label)

        page_label = QLabel(f"{page_num}페이지")
        page_label.setAlignment(Qt.AlignCenter)
        item_layout.addWidget(page_label)

        self.thumbnail_layout.addWidget(item_widget)

    def _on_thumbnail_progress(self, current: int, total: int):
        self.preview_status_label.setText(
            f"썸네일 생성 중... ({current}/{total})"
        )

    def _on_thumbnails_finished(self, failed_pages: List[int]):
        if failed_pages:
            failed_text = ", ".join(str(p) for p in failed_pages)
            self.preview_status_label.setText(
                f"미리보기 완료 (일부 페이지 실패: {failed_text})"
            )
            QMessageBox.information(
                self,
                "미리보기 안내",
                f"다음 페이지의 썸네일 생성에 실패했습니다:\n{failed_text}\n\n"
                "해당 페이지는 건너뛰었습니다.",
            )
        else:
            self.preview_status_label.setText(
                f"미리보기 완료 (총 {self.page_count}페이지)"
            )

    def _on_thumbnail_error(self, message: str):
        self.preview_status_label.setText("미리보기 생성 실패")
        QMessageBox.warning(self, "미리보기 오류", message)

    # ------------------------------------------------------------------
    # 분할 기능
    # ------------------------------------------------------------------
    def _require_pdf_loaded(self) -> bool:
        """PDF가 업로드되었는지 확인"""
        if not self.current_pdf_path:
            QMessageBox.warning(
                self,
                "알림",
                "먼저 PDF 파일을 업로드해주세요.",
            )
            return False
        return True

    def split_by_range(self):
        if not self._require_pdf_loaded():
            return

        try:
            start, end = parse_range_input(self.range_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "분할 PDF 저장",
            f"split_{start}_{end}.pdf",
            "PDF 파일 (*.pdf)",
        )

        if not save_path:
            QMessageBox.information(self, "알림", "저장 위치를 선택하지 않았습니다.")
            return

        if not save_path.lower().endswith(".pdf"):
            save_path += ".pdf"

        try:
            PDFProcessor.split_by_range(
                self.current_pdf_path, start, end, save_path
            )
            QMessageBox.information(
                self,
                "완료",
                f"범위 분할이 완료되었습니다.\n\n저장 위치:\n{save_path}",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "분할 오류", str(exc))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "오류",
                f"분할 중 오류가 발생했습니다.\n\n{exc}",
            )

    def split_by_pages(self):
        if not self._require_pdf_loaded():
            return

        try:
            page_numbers = parse_pages_input(self.pages_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "분할 PDF 저장",
            "split_pages.pdf",
            "PDF 파일 (*.pdf)",
        )

        if not save_path:
            QMessageBox.information(self, "알림", "저장 위치를 선택하지 않았습니다.")
            return

        if not save_path.lower().endswith(".pdf"):
            save_path += ".pdf"

        try:
            PDFProcessor.split_by_pages(
                self.current_pdf_path, page_numbers, save_path
            )
            QMessageBox.information(
                self,
                "완료",
                f"페이지 분할이 완료되었습니다.\n\n저장 위치:\n{save_path}",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "분할 오류", str(exc))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "오류",
                f"분할 중 오류가 발생했습니다.\n\n{exc}",
            )

    def split_by_fixed_size(self):
        if not self._require_pdf_loaded():
            return

        try:
            chunk_size = parse_fixed_size_input(self.fixed_input.text())
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
            return

        output_dir = QFileDialog.getExistingDirectory(
            self,
            "분할 PDF 저장 폴더 선택",
            os.path.dirname(self.current_pdf_path),
        )

        if not output_dir:
            QMessageBox.information(self, "알림", "저장 폴더를 선택하지 않았습니다.")
            return

        try:
            saved_files = PDFProcessor.split_by_fixed_size(
                self.current_pdf_path, chunk_size, output_dir
            )
            file_list = "\n".join(os.path.basename(f) for f in saved_files)
            QMessageBox.information(
                self,
                "완료",
                f"고정 단위 분할이 완료되었습니다.\n\n"
                f"저장 폴더:\n{output_dir}\n\n"
                f"생성된 파일 ({len(saved_files)}개):\n{file_list}",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "분할 오류", str(exc))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "오류",
                f"분할 중 오류가 발생했습니다.\n\n{exc}",
            )

    # ------------------------------------------------------------------
    # 병합 기능
    # ------------------------------------------------------------------
    def select_merge_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "병합할 PDF 파일 선택",
            "",
            "PDF 파일 (*.pdf);;모든 파일 (*.*)",
        )

        if not file_paths:
            return

        for path in file_paths:
            if not PDFProcessor.is_pdf_file(path):
                QMessageBox.warning(
                    self,
                    "오류",
                    f"PDF 파일이 아닙니다:\n{path}",
                )
                continue

            if path not in self.merge_files:
                self.merge_files.append(path)
                self._add_merge_list_item(path)

    def _add_merge_list_item(self, file_path: str):
        """병합 목록에 파일 추가 (파일명 + 전체 경로 표시)"""
        file_name = os.path.basename(file_path)
        item = QListWidgetItem(f"{file_name}\n{file_path}")
        item.setData(Qt.UserRole, file_path)
        self.merge_list.addItem(item)

    def _sync_merge_files_from_list(self):
        """리스트 위젯 순서에 맞게 merge_files 동기화"""
        self.merge_files = []
        for i in range(self.merge_list.count()):
            item = self.merge_list.item(i)
            self.merge_files.append(item.data(Qt.UserRole))

    def move_merge_item_up(self):
        row = self.merge_list.currentRow()
        if row <= 0:
            return

        item = self.merge_list.takeItem(row)
        self.merge_list.insertItem(row - 1, item)
        self.merge_list.setCurrentRow(row - 1)
        self._sync_merge_files_from_list()

    def move_merge_item_down(self):
        row = self.merge_list.currentRow()
        if row < 0 or row >= self.merge_list.count() - 1:
            return

        item = self.merge_list.takeItem(row)
        self.merge_list.insertItem(row + 1, item)
        self.merge_list.setCurrentRow(row + 1)
        self._sync_merge_files_from_list()

    def remove_merge_item(self):
        row = self.merge_list.currentRow()
        if row < 0:
            QMessageBox.information(self, "알림", "제거할 파일을 선택해주세요.")
            return

        self.merge_list.takeItem(row)
        self._sync_merge_files_from_list()

    def clear_merge_list(self):
        self.merge_list.clear()
        self.merge_files.clear()

    def merge_pdfs(self):
        self._sync_merge_files_from_list()

        if not self.merge_files:
            QMessageBox.warning(
                self,
                "알림",
                "병합할 PDF 파일을 선택해주세요.",
            )
            return

        if len(self.merge_files) < 2:
            QMessageBox.warning(
                self,
                "알림",
                "병합하려면 PDF 파일이 2개 이상 필요합니다.",
            )
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "병합 PDF 저장",
            "merged.pdf",
            "PDF 파일 (*.pdf)",
        )

        if not save_path:
            QMessageBox.information(self, "알림", "저장 위치를 선택하지 않았습니다.")
            return

        if not save_path.lower().endswith(".pdf"):
            save_path += ".pdf"

        try:
            PDFProcessor.merge_pdfs(self.merge_files, save_path)
            QMessageBox.information(
                self,
                "완료",
                f"PDF 병합이 완료되었습니다.\n\n저장 위치:\n{save_path}",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "병합 오류", str(exc))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "병합 오류",
                f"병합 중 오류가 발생했습니다.\n\n{exc}",
            )


# ---------------------------------------------------------------------------
# 프로그램 진입점
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

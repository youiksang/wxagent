"""
PDF → 편집 가능 PPTX 변환 Worker (QThread).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal

from font_utils import ResolvedFont, resolve_pptx_font
from image_cleaner import remove_text_from_image
from ocr_utils import OcrEngine, sort_ocr_boxes_reading_order
from pdf_renderer import PdfRenderer
from pptx_builder import PptxBuilder


@dataclass
class ConversionSettings:
    """변환 옵션."""

    pdf_path: str
    output_pptx_path: str
    font_name: str
    render_scale: float = 2.0
    min_confidence: float = 0.35
    use_gpu: bool = False
    mask_expand_px: int = 4
    inpaint_radius: int = 3
    font_size_scale: float = 0.8
    keep_temp_files: bool = False


class ConverterWorker(QThread):
    """백그라운드에서 PDF → PPTX 변환을 수행하는 Worker Thread."""

    progress_changed = pyqtSignal(int)
    page_status_changed = pyqtSignal(str)
    log_message = pyqtSignal(str)
    conversion_finished = pyqtSignal(str)
    conversion_failed = pyqtSignal(str)

    def __init__(self, settings: ConversionSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """변환 취소를 요청합니다."""
        self._cancel_requested = True

    def _log(self, message: str) -> None:
        self.log_message.emit(message)

    def _check_cancelled(self) -> None:
        if self._cancel_requested:
            raise InterruptedError("사용자에 의해 변환이 취소되었습니다.")

    def run(self) -> None:
        temp_dir: Optional[str] = None
        renderer: Optional[PdfRenderer] = None

        try:
            settings = self.settings
            pdf_path = settings.pdf_path
            output_path = settings.output_pptx_path

            if not pdf_path:
                raise ValueError("PDF 파일을 선택하지 않았습니다.")
            if not output_path:
                raise ValueError("저장 경로를 지정하지 않았습니다.")
            if not os.path.isfile(pdf_path):
                raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

            if not output_path.lower().endswith(".pptx"):
                output_path = output_path + ".pptx"

            project_root = os.path.dirname(os.path.abspath(__file__))
            temp_base = os.path.join(project_root, "temp")
            os.makedirs(temp_base, exist_ok=True)
            temp_dir = tempfile.mkdtemp(prefix="conv_", dir=temp_base)

            self._log(f"임시 작업 폴더: {temp_dir}")
            self._log("EasyOCR 초기화 중... (최초 실행 시 모델 다운로드가 필요할 수 있습니다)")

            ocr_engine = OcrEngine(gpu=settings.use_gpu)
            ocr_engine.initialize()
            self._log("EasyOCR 초기화 완료")

            resolved_font = resolve_pptx_font(settings.font_name, log_callback=self._log)
            if resolved_font.warning_message:
                self._log(resolved_font.warning_message)

            renderer = PdfRenderer(pdf_path)
            doc_info = renderer.open()
            total_pages = doc_info.page_count
            self._log(f"PDF 페이지 수: {total_pages}")

            builder = PptxBuilder()

            for page_index in range(total_pages):
                self._check_cancelled()
                page_num = page_index + 1

                self.page_status_changed.emit(
                    f"페이지 {page_num} / {total_pages} 처리 중..."
                )
                self._log(f"{page_num}페이지 렌더링 중...")
                rendered = renderer.render_page(
                    page_index=page_index,
                    output_dir=temp_dir,
                    scale=settings.render_scale,
                )
                self._check_cancelled()

                self._log(f"{page_num}페이지 OCR 처리 중...")
                ocr_boxes = ocr_engine.read_image(
                    rendered.image_path,
                    min_confidence=settings.min_confidence,
                )
                ocr_boxes = sort_ocr_boxes_reading_order(ocr_boxes)

                if not ocr_boxes:
                    self._log(
                        f"{page_num}페이지: OCR 결과가 없습니다. "
                        "배경 이미지만 슬라이드에 추가합니다."
                    )
                else:
                    self._log(
                        f"{page_num}페이지: OCR 텍스트 {len(ocr_boxes)}개 인식"
                    )

                self._check_cancelled()
                self._log(f"{page_num}페이지 텍스트 제거 중...")
                cleaned_path = os.path.join(temp_dir, f"page_{page_num:04d}_cleaned.png")
                cleaned_image_path = remove_text_from_image(
                    image_path=rendered.image_path,
                    boxes=ocr_boxes,
                    output_path=cleaned_path,
                    mask_expand_px=settings.mask_expand_px,
                    inpaint_radius=settings.inpaint_radius,
                )
                self._check_cancelled()

                self._log(f"{page_num}페이지 PPT 슬라이드 생성 중...")
                builder.add_slide(
                    background_image_path=cleaned_image_path,
                    ocr_boxes=ocr_boxes,
                    image_width_px=rendered.width_px,
                    image_height_px=rendered.height_px,
                    resolved_font=resolved_font,
                    source_image_for_color=rendered.image_path,
                    font_size_scale=settings.font_size_scale,
                    log_callback=self._log,
                )
                self._log(f"{page_num}페이지 완료")

                progress = int((page_num / total_pages) * 100)
                self.progress_changed.emit(progress)

            self._log("PPTX 파일 저장 중...")
            saved_path = builder.save(output_path)
            self.progress_changed.emit(100)
            self._log(f"변환 완료: {saved_path}")
            self.conversion_finished.emit(saved_path)

        except InterruptedError as exc:
            self.conversion_failed.emit(str(exc))
        except Exception as exc:
            self.conversion_failed.emit(str(exc))
        finally:
            if renderer is not None:
                renderer.close()
            if temp_dir and os.path.isdir(temp_dir):
                if self.settings.keep_temp_files:
                    self._log(f"임시 파일 유지: {temp_dir}")
                else:
                    try:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self._log("임시 파일을 삭제했습니다.")
                    except Exception as exc:
                        self._log(f"임시 파일 삭제 실패: {exc}")

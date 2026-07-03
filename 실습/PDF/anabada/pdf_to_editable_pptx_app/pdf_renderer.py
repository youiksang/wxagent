"""
PyMuPDF(fitz)를 사용해 PDF 페이지를 고해상도 이미지로 렌더링합니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

try:
    import fitz
except ImportError as exc:
    raise ImportError(
        "PyMuPDF 패키지가 설치되어 있지 않습니다. "
        "터미널에서 'pip install PyMuPDF' 명령으로 설치해 주세요."
    ) from exc

from PIL import Image


PPT_ASPECT_RATIO = 16 / 9
DEFAULT_RENDER_SCALE = 2.0


@dataclass
class RenderedPage:
    """렌더링된 PDF 페이지 정보."""

    page_index: int
    image_path: str
    width_px: int
    height_px: int
    scale: float


@dataclass
class PdfDocumentInfo:
    """PDF 문서 기본 정보."""

    path: str
    page_count: int


class PdfRenderer:
    """PDF 페이지를 이미지 파일로 렌더링하는 클래스."""

    def __init__(self, pdf_path: str):
        if not pdf_path or not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

        self.pdf_path = pdf_path
        self._doc: Optional[fitz.Document] = None

    def open(self) -> PdfDocumentInfo:
        """PDF 문서를 열고 페이지 수를 반환합니다."""
        try:
            self._doc = fitz.open(self.pdf_path)
        except Exception as exc:
            raise RuntimeError(f"PDF 파일을 열 수 없습니다: {self.pdf_path}") from exc

        page_count = len(self._doc)
        if page_count == 0:
            self.close()
            raise ValueError("PDF에 페이지가 없습니다.")

        return PdfDocumentInfo(path=self.pdf_path, page_count=page_count)

    def close(self) -> None:
        """PDF 문서를 닫습니다."""
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    def __enter__(self) -> "PdfRenderer":
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def render_page(
        self,
        page_index: int,
        output_dir: str,
        scale: float = DEFAULT_RENDER_SCALE,
    ) -> RenderedPage:
        """
        단일 PDF 페이지를 PNG 이미지로 렌더링합니다.

        Parameters
        ----------
        page_index : int
            0부터 시작하는 페이지 인덱스
        output_dir : str
            렌더링 이미지 저장 폴더
        scale : float
            렌더링 배율 (기본 2.0)
        """
        if self._doc is None:
            raise RuntimeError("PDF가 열려 있지 않습니다. open()을 먼저 호출하세요.")

        if page_index < 0 or page_index >= len(self._doc):
            raise IndexError(f"유효하지 않은 페이지 번호입니다: {page_index + 1}")

        os.makedirs(output_dir, exist_ok=True)

        page = self._doc.load_page(page_index)
        matrix = fitz.Matrix(scale, scale)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        image_path = os.path.join(output_dir, f"page_{page_index + 1:04d}.png")
        try:
            pixmap.save(image_path)
        except Exception as exc:
            raise RuntimeError(
                f"{page_index + 1}페이지 이미지 렌더링에 실패했습니다."
            ) from exc

        width_px = pixmap.width
        height_px = pixmap.height

        return RenderedPage(
            page_index=page_index,
            image_path=image_path,
            width_px=width_px,
            height_px=height_px,
            scale=scale,
        )

    def render_all_pages(
        self,
        output_dir: str,
        scale: float = DEFAULT_RENDER_SCALE,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[RenderedPage]:
        """모든 PDF 페이지를 순차적으로 렌더링합니다."""
        if self._doc is None:
            raise RuntimeError("PDF가 열려 있지 않습니다. open()을 먼저 호출하세요.")

        results: List[RenderedPage] = []
        total = len(self._doc)

        for page_index in range(total):
            rendered = self.render_page(page_index, output_dir, scale=scale)
            results.append(rendered)
            if progress_callback:
                progress_callback(page_index + 1, total)

        return results


def validate_image_file(image_path: str) -> Tuple[int, int]:
    """렌더링된 이미지 파일이 정상인지 확인하고 (width, height)를 반환합니다."""
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"렌더링 이미지를 찾을 수 없습니다: {image_path}")

    try:
        with Image.open(image_path) as img:
            return img.size
    except Exception as exc:
        raise RuntimeError(f"렌더링 이미지를 읽을 수 없습니다: {image_path}") from exc


def is_approximately_16_9(width: int, height: int, tolerance: float = 0.05) -> bool:
    """이미지 비율이 16:9에 가까운지 확인합니다."""
    if height <= 0:
        return False
    ratio = width / height
    return abs(ratio - PPT_ASPECT_RATIO) <= tolerance

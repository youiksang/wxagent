"""
EasyOCR을 사용한 텍스트 인식 유틸리티.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

try:
    import easyocr
except ImportError as exc:
    raise ImportError(
        "easyocr 패키지가 설치되어 있지 않습니다. "
        "터미널에서 'pip install easyocr' 명령으로 설치해 주세요."
    ) from exc

try:
    import cv2
except ImportError as exc:
    raise ImportError(
        "opencv-python 패키지가 설치되어 있지 않습니다. "
        "터미널에서 'pip install opencv-python' 명령으로 설치해 주세요."
    ) from exc

DEFAULT_MIN_CONFIDENCE = 0.35
DEFAULT_OCR_LANGUAGES = ["ko", "en"]


@dataclass
class OcrBox:
    """OCR로 인식된 텍스트 영역 정보."""

    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    x2: int
    y2: int
    bbox: Tuple[Tuple[int, int], ...]


class OcrEngine:
    """EasyOCR Reader 래퍼."""

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        gpu: bool = False,
    ):
        self.languages = languages or list(DEFAULT_OCR_LANGUAGES)
        self.gpu = gpu
        self._reader: Optional[easyocr.Reader] = None

    def initialize(self) -> None:
        """EasyOCR Reader를 초기화합니다. 최초 실행 시 모델 다운로드가 필요합니다."""
        if self._reader is not None:
            return
        try:
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        except Exception as exc:
            raise RuntimeError(
                "EasyOCR 초기화에 실패했습니다. "
                "인터넷 연결 및 torch/easyocr 설치 상태를 확인해 주세요."
            ) from exc

    @property
    def reader(self) -> easyocr.Reader:
        if self._reader is None:
            self.initialize()
        assert self._reader is not None
        return self._reader

    def read_image(
        self,
        image_path: str,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ) -> List[OcrBox]:
        """
        이미지에서 텍스트를 OCR로 인식합니다.

        Parameters
        ----------
        image_path : str
            OCR 대상 이미지 경로
        min_confidence : float
            최소 신뢰도 (기본 0.35)
        """
        image = cv2.imread(image_path)
        if image is None:
            raise RuntimeError(f"OCR용 이미지를 읽을 수 없습니다: {image_path}")

        try:
            raw_results = self.reader.readtext(image)
        except Exception as exc:
            raise RuntimeError(f"OCR 처리 중 오류가 발생했습니다: {image_path}") from exc

        boxes: List[OcrBox] = []
        for item in raw_results:
            if len(item) < 3:
                continue

            polygon, text, confidence = item[0], item[1], float(item[2])
            if confidence < min_confidence:
                continue

            text = str(text).strip()
            if not text:
                continue

            ocr_box = polygon_to_ocr_box(polygon, text, confidence)
            boxes.append(ocr_box)

        return boxes


def polygon_to_ocr_box(
    polygon,
    text: str,
    confidence: float,
) -> OcrBox:
    """
    EasyOCR polygon 결과를 정리된 bounding box로 변환합니다.

    EasyOCR polygon: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    """
    points = np.array(polygon, dtype=np.float32)
    xs = points[:, 0]
    ys = points[:, 1]

    x = int(np.floor(xs.min()))
    y = int(np.floor(ys.min()))
    x2 = int(np.ceil(xs.max()))
    y2 = int(np.ceil(ys.max()))
    width = max(1, x2 - x)
    height = max(1, y2 - y)

    bbox_tuple = tuple((int(p[0]), int(p[1])) for p in points)

    return OcrBox(
        text=text,
        confidence=confidence,
        x=x,
        y=y,
        width=width,
        height=height,
        x2=x2,
        y2=y2,
        bbox=bbox_tuple,
    )


def run_ocr_on_image(
    image_path: str,
    reader: easyocr.Reader,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> List[OcrBox]:
    """이미 초기화된 Reader로 OCR을 실행합니다."""
    engine = OcrEngine()
    engine._reader = reader
    return engine.read_image(image_path, min_confidence=min_confidence)


def sort_ocr_boxes_reading_order(boxes: List[OcrBox]) -> List[OcrBox]:
    """위에서 아래, 왼쪽에서 오른쪽 순으로 OCR 박스를 정렬합니다."""
    return sorted(boxes, key=lambda b: (b.y, b.x))

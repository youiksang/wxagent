"""
OCR bounding box 기반 OpenCV inpaint 텍스트 제거.

주의: 복잡한 배경 위의 텍스트는 완벽하게 제거되지 않을 수 있습니다.
inpaint 알고리즘은 주변 픽셀을 보간해 채우므로, 그라데이션·패턴·이미지 위
글자는 잔상이 남거나 주변 영역이 약간 변형될 수 있습니다.
"""

from __future__ import annotations

import os
from typing import List, Optional

import cv2
import numpy as np

from ocr_utils import OcrBox

DEFAULT_MASK_EXPAND_PX = 4
DEFAULT_INPAINT_RADIUS = 3


def create_text_mask(
    image_shape: tuple,
    boxes: List[OcrBox],
    expand_px: int = DEFAULT_MASK_EXPAND_PX,
) -> np.ndarray:
    """
    OCR bounding box 영역을 기준으로 inpaint용 mask를 생성합니다.

    mask는 흰색(255) 영역이 수정 대상(텍스트)입니다.
    """
    height, width = image_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    for box in boxes:
        x1 = max(0, box.x - expand_px)
        y1 = max(0, box.y - expand_px)
        x2 = min(width, box.x2 + expand_px)
        y2 = min(height, box.y2 + expand_px)
        cv2.rectangle(mask, (x1, y1), (x2, y2), color=255, thickness=-1)

    return mask


def remove_text_from_image(
    image_path: str,
    boxes: List[OcrBox],
    output_path: Optional[str] = None,
    mask_expand_px: int = DEFAULT_MASK_EXPAND_PX,
    inpaint_radius: int = DEFAULT_INPAINT_RADIUS,
) -> str:
    """
    OCR 영역의 텍스트를 OpenCV inpaint로 제거합니다.

    Parameters
    ----------
    image_path : str
        원본 이미지 경로
    boxes : List[OcrBox]
        OCR bounding box 목록
    output_path : str, optional
        저장 경로. None이면 원본 경로에 _cleaned 접미사 추가
    mask_expand_px : int
        mask 확장 픽셀 (기본 4px)
    inpaint_radius : int
        inpaint 반경/강도 (기본 3)
    """
    image = cv2.imread(image_path)
    if image is None:
        raise RuntimeError(f"텍스트 제거용 이미지를 읽을 수 없습니다: {image_path}")

    if not boxes:
        if output_path is None:
            base, ext = os.path.splitext(image_path)
            output_path = f"{base}_cleaned{ext}"
        cv2.imwrite(output_path, image)
        return output_path

    mask = create_text_mask(image.shape, boxes, expand_px=mask_expand_px)

    try:
        cleaned = cv2.inpaint(
            image,
            mask,
            inpaintRadius=max(1, inpaint_radius),
            flags=cv2.INPAINT_TELEA,
        )
    except Exception as exc:
        raise RuntimeError(
            f"텍스트 제거(inpainting) 처리에 실패했습니다: {image_path}"
        ) from exc

    if output_path is None:
        base, ext = os.path.splitext(image_path)
        output_path = f"{base}_cleaned{ext}"

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if not cv2.imwrite(output_path, cleaned):
        raise RuntimeError(f"텍스트 제거 이미지 저장에 실패했습니다: {output_path}")

    return output_path

"""
시스템 폰트 확인 및 PPTX용 폰트 설정 유틸리티.

UI에서 선택한 한글 폰트(나눔고딕, 맑은 고딕, 나눔스퀘어 Bold)가
시스템에 설치되어 있는지 확인하고, python-pptx에 적용할 실제 폰트명과
굵기(bold) 정보를 반환합니다.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

# UI ComboBox에 표시되는 폰트 옵션 (기본값: 나눔고딕)
FONT_OPTIONS: Tuple[str, ...] = ("나눔고딕", "맑은 고딕", "나눔스퀘어 Bold")
DEFAULT_FONT_OPTION = "나눔고딕"

# PPTX fallback 폰트 (한글/영문 혼용 시 비교적 안전한 기본값)
FALLBACK_PPTX_FONT = "Malgun Gothic"
FALLBACK_PPTX_FONT_KO = "맑은 고딕"

# Windows Fonts 폴더에서 찾을 파일명 (소문자 비교)
WINDOWS_FONT_FILES: Dict[str, Tuple[str, ...]] = {
    "나눔고딕": (
        "nanumgothic.ttf",
        "nanumgothicbold.ttf",
        "nanumgothicextrabold.ttf",
    ),
    "맑은 고딕": (
        "malgun.ttf",
        "malgunbd.ttf",
        "malgunsl.ttf",
    ),
    "나눔스퀘어 Bold": (
        "nanumsquareb.ttf",
        "nanumsquarebold.ttf",
        "nanumsquare_acb.ttf",
        "nanumsquare_acb.otf",
    ),
}

# QFontDatabase / PPTX에서 매칭할 후보 이름
FONT_CANDIDATE_NAMES: Dict[str, Tuple[str, ...]] = {
    "나눔고딕": (
        "나눔고딕",
        "NanumGothic",
        "Nanum Gothic",
        "NanumGothic Regular",
    ),
    "맑은 고딕": (
        "맑은 고딕",
        "Malgun Gothic",
        "MalgunGothic",
    ),
    "나눔스퀘어 Bold": (
        "나눔스퀘어 Bold",
        "NanumSquare Bold",
        "NanumSquareB",
        "NanumSquare B",
        "NanumSquare ExtraBold",
        "NanumSquareEB",
    ),
}

# PPTX run.font.name에 넣을 표준 이름
PPTX_FONT_NAMES: Dict[str, str] = {
    "나눔고딕": "NanumGothic",
    "맑은 고딕": "Malgun Gothic",
    "나눔스퀘어 Bold": "NanumSquare Bold",
}


@dataclass(frozen=True)
class ResolvedFont:
    """PPTX 텍스트박스에 적용할 최종 폰트 정보."""

    ui_name: str
    pptx_name: str
    bold: bool
    used_fallback: bool
    warning_message: Optional[str] = None


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "")


def get_windows_fonts_dir() -> Optional[str]:
    """Windows 시스템 폰트 디렉터리 경로를 반환합니다."""
    if platform.system() != "Windows":
        return None
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = os.path.join(windir, "Fonts")
    if os.path.isdir(fonts_dir):
        return fonts_dir
    return None


def scan_font_files_in_directory(directory: str) -> Set[str]:
    """지정 폴더 내 폰트 파일명(소문자) 집합을 반환합니다."""
    found: Set[str] = set()
    if not os.path.isdir(directory):
        return found
    try:
        for entry in os.listdir(directory):
            lower = entry.lower()
            if lower.endswith((".ttf", ".otf", ".ttc", ".fon")):
                found.add(lower)
    except OSError:
        pass
    return found


def get_qt_font_families() -> Set[str]:
    """
    PyQt5 QFontDatabase를 통해 시스템에 등록된 폰트 패밀리 목록을 반환합니다.
    PyQt5가 없으면 빈 집합을 반환합니다.
    """
    try:
        from PyQt5.QtGui import QFontDatabase

        db = QFontDatabase()
        return set(db.families())
    except Exception:
        return set()


def _match_candidate_in_families(
    candidates: Tuple[str, ...],
    families: Set[str],
) -> Optional[str]:
    """후보 이름 중 시스템 폰트 목록과 일치하는 첫 항목을 반환합니다."""
    normalized_families = {_normalize(f): f for f in families}
    for candidate in candidates:
        key = _normalize(candidate)
        if key in normalized_families:
            return normalized_families[key]
    for candidate in candidates:
        key = _normalize(candidate)
        for norm, original in normalized_families.items():
            if key in norm or norm in key:
                return original
    return None


def is_font_file_present(option_name: str, font_files: Set[str]) -> bool:
    """Windows Fonts 폴더 파일명 기준으로 폰트 설치 여부를 확인합니다."""
    expected = WINDOWS_FONT_FILES.get(option_name, ())
    return any(name in font_files for name in expected)


def is_font_available(option_name: str) -> bool:
    """
    UI 폰트 옵션이 시스템에서 사용 가능한지 확인합니다.
    QFontDatabase와 Windows Fonts 폴더를 모두 참고합니다.
    """
    if option_name not in FONT_OPTIONS:
        return False

    families = get_qt_font_families()
    candidates = FONT_CANDIDATE_NAMES.get(option_name, ())
    if _match_candidate_in_families(candidates, families):
        return True

    fonts_dir = get_windows_fonts_dir()
    if fonts_dir:
        font_files = scan_font_files_in_directory(fonts_dir)
        if is_font_file_present(option_name, font_files):
            return True

    return False


def get_font_availability_report() -> Dict[str, bool]:
    """모든 UI 폰트 옵션의 사용 가능 여부를 반환합니다."""
    return {name: is_font_available(name) for name in FONT_OPTIONS}


def resolve_pptx_font(
    ui_font_name: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> ResolvedFont:
    """
    UI에서 선택한 폰트명을 PPTX 적용용 정보로 변환합니다.

    시스템에 해당 폰트가 없으면 맑은 고딕(Malgun Gothic)으로 대체하고
    경고 메시지를 반환합니다.
    """
    if ui_font_name not in FONT_OPTIONS:
        ui_font_name = DEFAULT_FONT_OPTION

    bold = ui_font_name == "나눔스퀘어 Bold"
    preferred_pptx_name = PPTX_FONT_NAMES.get(ui_font_name, FALLBACK_PPTX_FONT)

    if is_font_available(ui_font_name):
        return ResolvedFont(
            ui_name=ui_font_name,
            pptx_name=preferred_pptx_name,
            bold=bold,
            used_fallback=False,
            warning_message=None,
        )

    warning = (
        f"선택한 폰트 '{ui_font_name}'이(가) 시스템에 없어 "
        f"기본 폰트 '{FALLBACK_PPTX_FONT_KO}'({FALLBACK_PPTX_FONT})로 대체합니다."
    )
    if log_callback:
        log_callback(warning)

    fallback_bold = False
    if is_font_available("맑은 고딕"):
        fallback_name = PPTX_FONT_NAMES["맑은 고딕"]
    else:
        fallback_name = FALLBACK_PPTX_FONT

    return ResolvedFont(
        ui_name=ui_font_name,
        pptx_name=fallback_name,
        bold=fallback_bold,
        used_fallback=True,
        warning_message=warning,
    )


def apply_font_to_run(run, resolved: ResolvedFont) -> None:
    """
    python-pptx Run 객체에 폰트 이름과 굵기를 적용합니다.

    Parameters
    ----------
    run : pptx.text.text.Run
        텍스트 run 객체
    resolved : ResolvedFont
        resolve_pptx_font() 결과
    """
    run.font.name = resolved.pptx_name
    run.font.bold = resolved.bold


def apply_font_to_text_frame(text_frame, resolved: ResolvedFont) -> None:
    """
    텍스트 프레임의 모든 paragraph/run에 폰트를 적용합니다.
    빈 paragraph가 있어도 안전하게 처리합니다.
    """
    for paragraph in text_frame.paragraphs:
        if paragraph.runs:
            for run in paragraph.runs:
                apply_font_to_run(run, resolved)
        else:
            run = paragraph.add_run()
            apply_font_to_run(run, resolved)


def get_font_combo_items() -> List[str]:
    """UI ComboBox에 넣을 폰트 옵션 목록을 반환합니다."""
    return list(FONT_OPTIONS)


def get_default_font_combo_index() -> int:
    """기본 폰트(나눔고딕)의 ComboBox 인덱스를 반환합니다."""
    try:
        return FONT_OPTIONS.index(DEFAULT_FONT_OPTION)
    except ValueError:
        return 0


def format_font_status_for_log() -> str:
    """앱 시작 시 로그에 출력할 폰트 설치 상태 문자열을 생성합니다."""
    lines = ["[폰트 설치 상태]"]
    for name in FONT_OPTIONS:
        status = "사용 가능" if is_font_available(name) else "미설치"
        lines.append(f"  - {name}: {status}")
    lines.append(f"  - 기본값: {DEFAULT_FONT_OPTION}")
    return "\n".join(lines)

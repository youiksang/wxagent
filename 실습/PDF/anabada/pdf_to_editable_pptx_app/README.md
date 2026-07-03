# 이미지 PDF 슬라이드 → 편집 가능한 PPTX 변환기

구글 NotebookLM 등에서 생성된 **이미지 기반 슬라이드 PDF**를 불러와, 각 페이지를 **16:9 편집 가능 PPTX**로 변환하는 PyQt5 데스크톱 앱입니다.

OCR로 텍스트를 인식한 뒤 원본 이미지에서 글자 영역을 제거하고, 같은 위치에 **편집 가능한 텍스트박스**를 다시 삽입합니다.

---

## 주요 기능

- PDF 각 페이지를 고해상도 이미지로 렌더링 (PyMuPDF)
- EasyOCR로 한글/영어 텍스트 인식
- OpenCV inpaint로 기존 글자 영역 제거
- python-pptx로 16:9 (10 × 5.625 inch) PPTX 생성
- OCR 텍스트를 원래 위치에 편집 가능 텍스트박스로 삽입
- PyQt5 GUI, QThread 기반 비동기 변환

---

## 프로젝트 구조

```text
pdf_to_editable_pptx_app/
│
├── app.py                 # PyQt5 메인 UI
├── converter_worker.py    # QThread 변환 Worker
├── pdf_renderer.py        # PDF → 이미지 렌더링
├── ocr_utils.py           # EasyOCR 처리
├── image_cleaner.py       # 텍스트 제거 (OpenCV inpaint)
├── pptx_builder.py        # PPTX 생성
├── font_utils.py          # 폰트 확인 및 적용
├── requirements.txt
├── README.md
│
├── temp/                  # 임시 렌더링 파일
├── output/                # (선택) 출력 예시 폴더
└── assets/
```

---

## 설치 방법

### 1. 가상환경 생성 (권장)

**Windows (PowerShell)**

```powershell
cd pdf_to_editable_pptx_app
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD)**

```cmd
cd pdf_to_editable_pptx_app
python -m venv venv
venv\Scripts\activate.bat
```

**macOS / Linux**

```bash
cd pdf_to_editable_pptx_app
python3 -m venv venv
source venv/bin/activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

포함 패키지:

- PyQt5
- easyocr
- PyMuPDF
- python-pptx
- Pillow
- opencv-python
- numpy
- torch
- torchvision

### 3. EasyOCR 최초 실행 안내

EasyOCR은 **최초 실행 시 OCR 모델 파일을 인터넷에서 다운로드**합니다.

- 변환 시작 후 `EasyOCR 초기화 중...` 로그가 표시될 수 있습니다.
- 네트워크 연결이 필요합니다.
- 다운로드에는 수 분이 걸릴 수 있습니다.
- 이후 실행부터는 캐시된 모델을 사용합니다.

---

## 앱 실행 방법

프로젝트 폴더에서 아래 명령을 실행합니다.

```bash
python app.py
```

필수 패키지가 없으면 앱 시작 시 **어떤 패키지를 설치해야 하는지** 안내 메시지가 표시됩니다.

---

## 사용 방법

### 1. PDF 선택

1. **PDF 파일 선택** 버튼 클릭
2. 변환할 PDF 파일 선택 (`.pdf`만 가능)
3. 선택한 PDF 경로가 화면에 표시됩니다.
4. 저장 PPTX 경로가 자동으로 설정됩니다.

예시:

```text
입력 PDF: C:/files/notebooklm_slide.pdf
자동 저장 PPTX: C:/files/notebooklm_slide.pptx
```

### 2. PPTX 저장 경로 지정

- **저장 경로 선택** 버튼으로 `QFileDialog.getSaveFileName()` 저장 대화상자를 엽니다.
- 기본 저장 폴더는 PDF와 같은 폴더입니다.
- 확장자가 `.pptx`가 아니면 자동으로 `.pptx`가 붙습니다.

### 3. 폰트 선택

ComboBox에서 아래 폰트 중 하나를 선택합니다.

- 나눔고딕 (기본값)
- 맑은 고딕
- 나눔스퀘어 Bold

시스템에 선택한 폰트가 없으면 **맑은 고딕**으로 대체되며 로그에 경고가 표시됩니다.

### 4. 옵션 조정 (선택)

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| PDF 렌더링 배율 | 2배 | OCR 정확도 향상 (1.5배 / 2배 / 3배) |
| OCR 장치 | CPU | GPU 사용 가능 시 GPU 선택 가능 |
| OCR 최소 신뢰도 | 0.35 | 낮은 confidence 텍스트 제외 |
| 텍스트 mask 확장 | 4px | inpaint 영역 확장 |
| 텍스트 제거 강도 | 3 | inpaint 반경 |
| 폰트 크기 보정 배율 | 0.8 | OCR 박스 높이 기반 글자 크기 조정 |
| 임시 파일 유지 | 해제 | 디버깅용 임시 이미지 유지 |

### 5. 변환 실행

1. **변환 시작** 버튼 클릭
2. 진행률, 현재 페이지, 로그 확인
3. 완료 메시지에서 저장된 PPTX 경로 확인

로그 예시:

```text
1페이지 렌더링 중...
1페이지 OCR 처리 중...
1페이지 텍스트 제거 중...
1페이지 PPT 슬라이드 생성 중...
1페이지 완료
```

### 6. 결과 PPTX 수정

생성된 PPTX를 PowerPoint 또는 LibreOffice Impress에서 엽니다.

- **편집 가능한 대상**: OCR로 추출된 텍스트박스
- **배경으로 유지**: 슬라이드 이미지, 도형, 차트 등 비텍스트 요소

OCR 오인식 텍스트는 PowerPoint에서 직접 수정하세요.

---

## 좌표 변환 기준

PPT 슬라이드 크기:

```text
가로: 10 inches
세로: 5.625 inches (16:9)
```

이미지 픽셀 → PPT inch 변환:

```python
ppt_x = image_x / image_width_px * 10
ppt_y = image_y / image_height_px * 5.625
ppt_w = image_w / image_width_px * 10
ppt_h = image_h / image_height_px * 5.625
```

---

## 한계 및 주의사항

### OCR 한계

- OCR 결과는 **원본 PDF 품질, 해상도, 글꼴**에 따라 달라질 수 있습니다.
- OCR이 잘못 인식한 텍스트는 PPT에서 **직접 수정**해야 합니다.
- confidence가 낮은 텍스트는 기본 설정에서 제외될 수 있습니다.

### 텍스트 제거 한계

- OpenCV `inpaint()`는 주변 픽셀을 보간해 텍스트를 덮습니다.
- **복잡한 배경, 그라데이션, 패턴, 사진 위 텍스트**는 완벽하게 제거되지 않을 수 있습니다.
- 텍스트 제거 과정에서 주변 영역이 약간 변형될 수 있습니다.
- mask 확장값과 inpaint 강도를 조절해 품질을 개선할 수 있지만 100% 복원은 어렵습니다.

### 레이아웃 재현 한계

- 원본의 **정확한 폰트, 줄간격, 자간, 굵기, 색상**을 100% 재현하기는 어렵습니다.
- **도형, 이미지, 차트**는 편집 가능 개체로 변환되지 않고 **배경 이미지**로 유지됩니다.
- 편집 가능한 대상은 **OCR로 추출된 텍스트박스**입니다.

---

## 자주 발생하는 오류와 해결 방법

### 1. `필수 패키지가 설치되어 있지 않습니다`

```bash
pip install -r requirements.txt
```

가상환경을 사용 중이면 활성화 후 다시 설치하세요.

### 2. EasyOCR 초기화 실패

- 인터넷 연결 확인
- `pip install easyocr torch torchvision` 재설치
- 방화벽/프록시로 모델 다운로드 차단 여부 확인

### 3. PDF 파일을 열 수 없습니다

- 파일 경로에 한글/공백이 있어도 일반적으로 동작하지만, 파일이 손상되지 않았는지 확인
- PDF가 암호로 보호되어 있지 않은지 확인

### 4. OCR 결과가 없습니다

- 렌더링 배율을 **3배**로 올려 재시도
- OCR 최소 신뢰도를 **0.2~0.3**으로 낮춰 재시도
- PDF가 실제 텍스트가 아닌 순수 이미지인지, 해상도가 충분한지 확인

### 5. 텍스트 제거 품질이 낮습니다

- mask 확장값을 3~6px 범위에서 조정
- inpaint 강도를 2~5 범위에서 조정
- 복잡한 배경 위 텍스트는 완벽 제거가 어렵다는 점 참고

### 6. 폰트가 깨집니다

- Windows에 **나눔고딕 / 맑은 고딕 / 나눔스퀘어** 설치
- 앱 로그의 `[폰트 설치 상태]` 확인
- PowerPoint에서도 동일 폰트가 설치되어 있어야 정상 표시됩니다.

### 7. GPU 사용 오류

- CUDA 미설치 환경에서는 **CPU 사용** 선택
- GPU 옵션은 CUDA 지원 PyTorch가 설치된 경우에만 사용

### 8. 변환 중 앱 종료

- 변환 중 창을 닫으면 확인 대화상자가 표시됩니다.
- 종료 시 진행 중인 작업이 취소됩니다.

---

## 기술 스택

| 용도 | 패키지 |
|------|--------|
| UI | PyQt5 |
| PDF 렌더링 | PyMuPDF (fitz) |
| OCR | EasyOCR |
| PPTX 생성 | python-pptx |
| 이미지 처리 | OpenCV, Pillow, numpy |
| 딥러닝 백엔드 | torch, torchvision |

---

## 라이선스

이 프로젝트는 학습/실습 목적으로 작성되었습니다.
EasyOCR, PyMuPDF, python-pptx 등 사용 패키지의 라이선스를 각각 확인하세요.

# 예측 시스템

Python Flask 기반의 순차형 데이터 분석·예측 웹 애플리케이션입니다.  
파일 업로드부터 변수 선택, 결측치/이상치 처리, 탐색적 분석, 회귀분석, 모델 검증, 시뮬레이션까지 단계별로 진행됩니다.

## 주요 기능

- CSV/Excel 파일 업로드
- 종속·독립 변수 선택
- 결측치 및 이상치(3σ) 처리
- 히스토그램, 산점도, 상관관계 히트맵
- 전진선택법, 후진제거법, 릿지, 라쏘 회귀분석
- 잔차분석 및 적합도 검정
- Plotly/Dash 기반 인터랙티브 시뮬레이션
- SQLite3 세션 상태 저장 및 단계별 진행 관리

## 프로젝트 구조

```text
prediction_system/
├── app.py
├── models.py
├── analysis_utils.py
├── regression_utils.py
├── simulation_utils.py
├── generate_sample_data.py
├── requirements.txt
├── instance/prediction_system.sqlite3
├── data/raw|processed|models|metadata/
├── static/css|plots|uploads/
└── templates/
```

## 설치 및 실행

### 1. 가상환경 생성

```bash
cd prediction_system
python -m venv venv
```

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. 데이터베이스 초기화

Flask 앱을 처음 실행하면 `instance/prediction_system.sqlite3`가 자동 생성됩니다.

```bash
python app.py
```

### 4. 샘플 데이터 생성 (선택)

```bash
python generate_sample_data.py
```

생성 파일: `data/raw/sample_sales_data.csv`

### 5. 브라우저 접속

```
http://127.0.0.1:5000
```

## 단계별 사용 방법

1. **파일 업로드** – CSV 또는 Excel 업로드
2. **변수 선택** – 종속변수 1개, 독립변수 1개 이상 선택
3. **결측치 제거** – 분석 변수 기준 결측 행 제거
4. **이상치 탐색** – 3σ 기준 탐색 후 선택 변수 이상치 제거
5. **탐색적 분석** – 히스토그램/산점도/히트맵 또는 '완료' 버튼
6. **회귀분석** – 4가지 방법 실행 후 최종 모델 선택
7. **모델 검증** – 잔차분석 및 적합도 검정
8. **시뮬레이션** – 슬라이더로 예측값 확인

## 샘플 데이터 사용 예시

| 항목 | 권장 설정 |
|------|-----------|
| 종속변수 | 매출 |
| 독립변수 | 광고비, 인력수, 생산량, 원가, 지역, 제품군 |

## 초기화

좌측 하단 **초기화** 버튼을 클릭하면 세션, 업로드 파일, 그래프, 모델 파일이 모두 삭제됩니다.

## 다운로드

- 현재 분석 데이터 (CSV/Excel)
- 회귀분석 결과 (CSV)
- 모델 검증 결과 (CSV)

## 자주 발생하는 오류

| 오류 | 해결 방법 |
|------|-----------|
| `ModuleNotFoundError` | `pip install -r requirements.txt` 재실행 |
| 한글 그래프 깨짐 | Windows: 맑은 고딕 설치 확인 |
| Excel 업로드 실패 | `openpyxl`, `xlrd` 설치 확인 |
| 이전 단계 접근 불가 | 좌측 메뉴 순서대로 진행 |
| 회귀분석 실패 | 종속변수가 숫자형인지, 데이터 행 수 확인 |
| Dash 시뮬레이션 오류 | 최종 모델 선택 및 모델 검증 완료 후 접속 |

## 기술 스택

Python, Flask, SQLite3, SQLAlchemy, pandas, numpy, matplotlib, seaborn, statsmodels, scikit-learn, plotly, dash, Bootstrap 5

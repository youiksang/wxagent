# 아나바다 - 물품 공유 및 중고 거래 플랫폼

이웃과 함께 물품을 공유하거나 판매/무료 나눔할 수 있는 Flask 웹 애플리케이션입니다.

## 프로젝트 폴더 구조

```
anabada/
├── app.py                  # Flask 메인 앱, 라우팅, 인증
├── models.py               # User, Item 데이터베이스 모델
├── seed_data.py            # 테스트용 예시 데이터 추가 스크립트
├── requirements.txt        # 필요 패키지 목록
├── README.md               # 실행 방법 (이 파일)
├── anabada.db              # SQLite DB (실행 후 자동 생성)
├── templates/
│   ├── base.html           # 공통 레이아웃
│   ├── index.html          # 물품 목록 (메인)
│   ├── item_detail.html    # 물품 상세
│   ├── item_form.html      # 물품 등록/수정 폼
│   ├── login.html          # 로그인
│   └── register.html       # 회원가입
└── static/
    ├── css/
    │   └── style.css       # 커스텀 스타일
    ├── img/
    │   └── default_item.svg  # 기본 이미지
    └── uploads/            # 업로드된 물품 사진 저장 폴더
```

## 설치할 패키지

| 패키지 | 용도 |
|--------|------|
| flask | 웹 프레임워크 |
| flask-sqlalchemy | ORM (데이터베이스) |
| flask-login | 사용자 인증 (로그인/로그아웃) |

## 설치 및 실행 방법

### 1. 프로젝트 폴더로 이동

```bash
cd anabada
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

### 3. (기존 DB가 있다면) 삭제 후 재생성

스키마가 변경되었으므로 기존 `anabada.db`가 있으면 삭제합니다.

```bash
rm -f anabada.db
```

### 4. 서버 실행

```bash
python app.py
```

### 5. 브라우저 접속

```
http://localhost:5001
```

> 상위 폴더 PDF 번역 앱(`app.py`)과 포트가 겹치지 않도록 **5001** 포트를 사용합니다. 두 앱을 동시에 실행하려면 한쪽 포트를 변경하세요.

## 데이터베이스 초기화

앱을 처음 실행하면 `anabada.db` 파일과 `users`, `items` 테이블이 **자동으로 생성**됩니다.

수동으로 초기화하려면:

```bash
python -c "from app import app, db; app.app_context().push(); db.create_all(); print('DB 초기화 완료')"
```

## 테스트용 예시 데이터 추가

```bash
python seed_data.py
```

- 사용자 2명: `kimminsoo` / `test1234`, `leejieun` / `test1234`
- 물품 6개 (무료 나눔, 유료 판매, 거래완료 등)

## 주요 기능

- **회원 관리**: 회원가입, 로그인, 로그아웃 (Flask-Login)
- **물품 CRUD**: 등록(사진 업로드), 조회, 수정, 삭제 (작성자만 수정/삭제 가능)
- **무료 나눔**: 가격 0원 또는 체크박스 선택 시 무료 나눔으로 표시
- **거래 상태**: 거래가능 / 거래완료 (상세 페이지에서 토글)
- **검색**: 제목 또는 내용으로 검색
- **필터**: 무료 나눔만 보기

## API 라우트

| 메서드 | URL | 설명 | 권한 |
|--------|-----|------|------|
| GET/POST | `/register` | 회원가입 | 비로그인 |
| GET/POST | `/login` | 로그인 | 비로그인 |
| GET | `/logout` | 로그아웃 | 로그인 |
| GET | `/` | 물품 목록 (검색, 필터) | 전체 |
| GET/POST | `/items/new` | 등록 | 로그인 |
| GET | `/items/<id>` | 상세 | 전체 |
| GET/POST | `/items/<id>/edit` | 수정 | 로그인 + 작성자 |
| POST | `/items/<id>/delete` | 삭제 | 로그인 + 작성자 |
| POST | `/items/<id>/toggle_status` | 상태 토글 | 로그인 + 작성자 |

## 이미지 업로드 규칙

- 저장 위치: `static/uploads/`
- 허용 확장자: png, jpg, jpeg, gif
- 파일명: UUID로 중복 방지
- 이미지 없을 때: `static/img/default_item.svg` 표시

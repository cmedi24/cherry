# 새로운 농원 체리 주문장부

새로운 농원에서 체리 주문을 받고 관리하기 위한 1차 MVP 웹앱입니다.

구매자는 모바일에서 상품 사진과 상세 설명을 보고 주문할 수 있고, 관리자는 주문, 입금, 포장, 배달 상태를 관리할 수 있습니다.

## 구매자 화면 구성

- 새로운 농원 브랜드 배너
- 오늘 주문 마감, 배달 가능 지역, 택배 가능 여부 안내
- 상품 목록 카드
- 상품 상세 화면
- 주문하기
- 주문 완료 안내
- 주문번호와 연락처로 주문 조회

구매 흐름은 단순하게 구성했습니다.

1. 상품 선택
2. 수령 정보 입력
3. 주문 상태 확인

## 관리자 기능

- 관리자 로그인
- 대시보드
- 상품 추가, 수정, 삭제
- 상품 대표 이미지와 추가 이미지 등록
- 주문 목록 확인
- 주문 상태 변경
- 입금 대기 주문 관리
- 배달중 주문 관리
- CSV 다운로드

## 로컬 실행 방법

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 127.0.0.1
```

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8501
```

주의: 이 주소는 내 컴퓨터에서만 열리는 로컬 주소입니다. 카카오톡이나 문자로 고객에게 공유하려면 배포 후 생기는 공개 주소가 필요합니다.

## 배포 추천 방법

가장 쉬운 방법은 Streamlit Community Cloud입니다.

배포 후 `https://...streamlit.app` 형태의 주소가 생기고, 이 주소를 카카오톡, 문자, 인스타그램, 블로그, QR 코드로 공유할 수 있습니다.

## Streamlit Community Cloud 배포 순서

1. GitHub에 새 저장소를 만듭니다.
2. 이 프로젝트 파일을 GitHub 저장소에 올립니다.
3. [Streamlit Community Cloud](https://share.streamlit.io/)에 접속합니다.
4. GitHub 계정으로 로그인합니다.
5. `New app`을 누릅니다.
6. Repository에서 방금 올린 저장소를 선택합니다.
7. Branch는 보통 `main`을 선택합니다.
8. Main file path에 아래 값을 입력합니다.

```text
app.py
```

9. Advanced settings 또는 Secrets에 아래 내용을 넣습니다.

```toml
CHERRY_ADMIN_PASSWORD = "원하는관리자비밀번호"
CHERRY_BANK_ACCOUNT = "농협 000-0000-0000-00 홍길동"
CHERRY_DB_PATH = "cherry_orders.db"
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
```

10. `Deploy`를 누릅니다.
11. 배포가 끝나면 공개 주소가 나옵니다.

## 카카오톡으로 공유하는 방법

배포 주소가 생기면 아래처럼 보내면 됩니다.

```text
새로운 농원 체리 주문하기
https://배포된주소
```

추천 공유 위치:

- 카카오톡 채팅방 공지
- 카카오톡 채널 프로필 링크
- 단골 고객 단체 메시지
- 인스타그램 프로필 링크
- 블로그 또는 스마트스토어 공지
- QR 코드로 만들어 박스, 전단, 명함에 인쇄

## Render 배포 방법

Render를 사용할 경우 이 프로젝트에 포함된 `Procfile`과 `render.yaml`을 사용할 수 있습니다.

Render에서 Web Service를 만들고 GitHub 저장소를 연결한 뒤 아래처럼 설정합니다.

```text
Build Command: pip install -r requirements.txt
Start Command: streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
```

환경변수에는 아래 값을 넣습니다.

```text
CHERRY_ADMIN_PASSWORD=원하는관리자비밀번호
CHERRY_BANK_ACCOUNT=농협 000-0000-0000-00 홍길동
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 배포 후 확인할 것

1. 휴대폰에서 공개 주소가 열리는지 확인합니다.
2. 새로운 농원 브랜드 배너가 보이는지 확인합니다.
3. 상품 목록과 상세 화면 이미지가 보이는지 확인합니다.
4. 테스트 주문을 넣고 주문번호가 표시되는지 확인합니다.
5. 주문번호와 연락처로 주문 조회가 되는지 확인합니다.
6. 관리자 화면에 로그인되는지 확인합니다.
7. 입금 완료, 포장중, 배달중, 완료 상태 변경이 되는지 확인합니다.
8. CSV 다운로드가 되는지 확인합니다.

## 중요한 데이터 저장 안내

현재 앱은 SQLite 파일(`cherry_orders.db`)에 주문 데이터를 저장합니다.

1차 테스트와 화면 확인에는 충분하지만, 무료 배포 환경에서는 파일 저장이 영구적이지 않을 수 있습니다. 실제 주문을 장기 운영하려면 Supabase, PostgreSQL, Google Sheets 같은 외부 저장소로 옮기는 것을 권장합니다.

`cherry_orders.db`에는 실제 주문 정보가 들어갈 수 있으므로 GitHub에 올리지 마세요. `.gitignore`에 DB 파일 제외 설정을 넣어두었습니다.

## 프로젝트 구조

```text
New project/
├─ app.py
├─ requirements.txt
├─ runtime.txt
├─ Procfile
├─ render.yaml
├─ .env.example
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.toml.example
├─ assets/
│  └─ product_images/
└─ README.md
```

## 환경변수

| 이름 | 설명 |
| --- | --- |
| `CHERRY_ADMIN_PASSWORD` | 관리자 로그인 비밀번호 |
| `CHERRY_BANK_ACCOUNT` | 구매자에게 보여줄 입금 계좌 |
| `CHERRY_DB_PATH` | SQLite DB 파일 경로 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 텔레그램 채팅 ID |

## 다음 개선 추천

- 주문 데이터 영구 저장용 외부 DB 연결
- 관리자 비밀번호 보안 강화
- 개인정보 보관 정책 정리
- 카카오톡 채널 링크와 QR 코드 제작
- 텔레그램 알림 실제 연결

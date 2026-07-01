# 구글시트 연동 설정 가이드

`sheets_sync.py`를 실행하려면 Google Cloud Platform(GCP) 서비스 계정 키 파일(`credentials.json`)이 필요합니다.
아래 순서대로 따라하면 10~15분 안에 완료됩니다.

---

## 1단계 — GCP 프로젝트 만들기

1. [Google Cloud Console](https://console.cloud.google.com/) 접속 (구글 계정으로 로그인)
2. 상단 프로젝트 선택창 클릭 → **새 프로젝트**
3. 이름: `voc-pipeline` (아무 이름이나 가능) → **만들기**
4. 방금 만든 프로젝트가 선택된 상태인지 확인

---

## 2단계 — API 두 개 활성화

좌측 메뉴 **API 및 서비스 > 라이브러리**로 이동 후 다음 두 가지를 검색해서 각각 **사용 설정** 클릭:

| API 이름 | 검색어 |
|----------|--------|
| Google Sheets API | `Google Sheets API` |
| Google Drive API  | `Google Drive API`  |

> Drive API가 필요한 이유: 새 스프레드시트 생성 시 Drive 권한이 필요합니다.

---

## 3단계 — 서비스 계정 만들기

1. **API 및 서비스 > 사용자 인증 정보** 이동
2. **+ 사용자 인증 정보 만들기 > 서비스 계정** 클릭
3. 서비스 계정 이름: `voc-sync` → **만들기 및 계속**
4. 역할 선택: **편집자** (또는 **뷰어** + 개별 파일 권한) → **계속 > 완료**

---

## 4단계 — JSON 키 다운로드

1. 방금 만든 서비스 계정(`voc-sync@...`) 클릭
2. **키** 탭 → **키 추가 > 새 키 만들기 > JSON** → **만들기**
3. 파일이 자동으로 다운로드됩니다 (예: `voc-pipeline-xxxxxxxx.json`)
4. 이 파일을 **`credentials.json`** 으로 이름 바꾸고 아래 위치에 놓으세요:

```
[01] 리뉴어스랩/
├── classify_voc.py
├── sheets_sync.py
├── credentials.json   ← 여기!
└── ...
```

> ⚠️ credentials.json은 비밀 키입니다. git에 커밋하지 마세요. (.gitignore에 이미 추가됨)

---

## 5단계 — 구글시트에 서비스 계정 공유

서비스 계정이 시트를 수정하려면 **편집자 권한**이 필요합니다.

**방법 A — 새 시트를 자동 생성하는 경우 (권장)**:
`sheets_sync.py`가 시트를 자동으로 만들지만, 서비스 계정 소유로 생성됩니다.
내 구글 계정으로 보려면 시트 URL을 복사한 후 공유:

```
# 실행 후 출력되는 URL을 복사해서 브라우저에서 열면 됩니다
python sheets_sync.py output/classified_voc.csv
```

출력 예시:
```
  새 스프레드시트 생성: 리뉴어스랩 VoC 리포트 — ...
  URL: https://docs.google.com/spreadsheets/d/1BxiMVs0...
```

이 URL을 브라우저에 붙여넣기 → 상단 **공유** → 내 이메일 추가 → **편집자**로 설정

**방법 B — 기존 시트에 기입하는 경우**:
구글시트를 열고 → 우측 상단 **공유** 버튼 → 서비스 계정 이메일 추가 (credentials.json 안의 `client_email` 필드값) → **편집자** 권한 부여

---

## 설정 완료 후 실행

```bash
# 5~6월 데이터 기입 (새 스프레드시트 자동 생성)
python sheets_sync.py output/classified_voc.csv

# 7월 데이터도 같은 시트에 기입 (--sheet-id는 위에서 출력된 ID)
python sheets_sync.py output/classified_voc_july2026.csv --sheet-id <sheet-id>
```

---

## 생성되는 시트 구조

| 탭 이름 | 내용 |
|---------|------|
| 분류결과 | 전체 분류 데이터 (유형별 배경색, 헤더 고정) |
| 집계요약 | 유형별·소분류별·Cause Tag별 건수·비율 집계표 |
| URGENT  | 긴급 에스컬레이션 대상 건만 별도 분리 (분홍 배경) |

---

## 문제 해결

| 오류 | 원인 | 해결 |
|------|------|------|
| `credentials.json 파일이 없습니다` | 파일 위치가 잘못됨 | 파일을 `[01] 리뉴어스랩/` 폴더에 두세요 |
| `403 PERMISSION_DENIED` | API 미활성화 | 2단계 재확인 |
| `APIError: RESOURCE_EXHAUSTED` | 무료 할당량 초과 | 잠시 후 재시도 |
| `SpreadsheetNotFound` | sheet-id 잘못됨 | URL의 `/d/` 와 `/edit` 사이 문자열이 ID |

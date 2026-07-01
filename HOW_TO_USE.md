# VoC 파이프라인 사용 가이드

## 페르소나별 파이프라인

```
【CS팀 실무자】          【PM (카본링크)】         【경영진·대표】
      │                        │                        │
  VoC 수집                     │                        │
  (이메일·채널톡·미팅)           │                        │
      │                        │                        │
  CSV 정리 ─────────────→ 파이프라인 실행               │
  data/voc_YYYYMM.csv     classify_voc.py               │
                          sheets_sync.py                │
                               │                        │
                          규제 변경 시                   │
                          reg-calendar.md 업데이트       │
                               │                        │
                ┌──────────────┴──────────────┐         │
                ↓                             ↓         │
          Google Sheets               HTML 리포트        │
          (공유 링크)                  report_voc.html   │
                │                             │         │
                ↓                             ↓         ↓
        URGENT 탭 확인           인사이트 3개        Google Sheets
        당일 에스컬레이션          기획안 2건          집계요약 탭
        분류결과 탭 필터링         → 스프린트 후보      → 전략 의사결정
        담당 건 처리              → 로드맵 우선순위
```

---

### CS팀 실무자가 하는 일

| 시점       | 작업                               | 도구          |
| ---------- | ---------------------------------- | ------------- |
| 매달 월말  | VoC 수집·CSV 정리                 | 엑셀          |
| PM 실행 후 | Google Sheets URGENT 탭 확인       | Google Sheets |
| 즉시       | URGENT 건 당일 에스컬레이션        | -             |
| 필요 시    | 분류결과 탭 필터링 → 담당 건 처리 | Google Sheets |

### PM이 하는 일

| 시점         | 작업                        | 도구              |
| ------------ | --------------------------- | ----------------- |
| 매달 월초    | 파이프라인 실행 (2줄)       | 터미널            |
| 규제 변경 시 | reg-calendar.md 업데이트    | AI 또는 직접 편집 |
| 실행 후      | HTML 인사이트·기획안 검토  | 브라우저          |
| 월간 회의    | Google Sheets 집계요약 공유 | Google Sheets     |

### 경영진·대표가 하는 일

| 시점       | 작업                                     | 도구          |
| ---------- | ---------------------------------------- | ------------- |
| PM 공유 후 | Google Sheets 링크 접근                  | Google Sheets |
| -          | 집계요약 탭 → 유형 분포·Cause Tag 파악 | -             |
| -          | 기획안 우선순위 승인                     | -             |

> 경영진은 파이프라인을 직접 실행하지 않습니다. Google Sheets 공유 링크만 있으면 됩니다.

---

## 사전 준비 (처음 한 번만)

- 시작 메뉴에서 `Anaconda Prompt` 를 검색해서 설치되어 있는지 확인한다
- `credentials.json` 파일이 이 폴더 안에 있는지 확인한다
  - 없으면 `SETUP_SHEETS.md` 를 보고 GCP 설정을 먼저 완료한다
- 구글시트 URL을 메모해둔다 (Sheet ID: `1PCUbNBXRvvaItiVaE24RscyuX3f7Frzye5SBkxNGiD4`)

---

## 매달 하는 작업

### ① VoC 데이터 정리

- 이달 수집된 고객 피드백(이메일, 채널톡, 미팅 메모)을 한데 모은다
- `data/voc.csv` 파일을 엑셀이나 메모장으로 열고 기존 형식에 맞게 행을 추가한다
  - 컬럼 순서: `id, date, channel, customer_type, content, keyword_hint`
  - `id`: 순서대로 번호 (001, 002, ...)
  - `date`: 날짜 (`2026-07-01` 형식, 섞여 있어도 자동 정제됨)
  - `channel`: 이메일 / 채널톡 / 미팅메모
  - `customer_type`: OEM / 1차 협력사 / 2차 협력사 / 기타
  - `content`: 고객이 남긴 원문
  - `keyword_hint`: 핵심 키워드 2~3개 쉼표 구분 (비워도 됨)
- 저장한다

### ② 터미널 열기

- 시작 메뉴 → `Anaconda Prompt` 실행
- 아래 명령어로 프로젝트 폴더로 이동한다

```powershell
Set-Location -LiteralPath "C:\Users\Minsoo\.claude\skills\AX해커톤\[01] 리뉴어스랩"
```

> ⚠️ 일반 `cd` 명령은 폴더명의 `[01]` 대괄호를 잘못 해석하므로 반드시 위 명령어를 사용한다

### ③ 분류 실행

```
c:/Users/Minsoo/anaconda3/python.exe classify_voc.py data/voc.csv
```

- `[4/4] 출력 완료` 가 뜨면 성공
- 결과물: `output/classified_voc.csv`, `output/report_voc.html`

### ④ 구글시트 동기화

```
c:/Users/Minsoo/anaconda3/python.exe sheets_sync.py output/classified_voc.csv --sheet-id 1PCUbNBXRvvaItiVaE24RscyuX3f7Frzye5SBkxNGiD4
```

- `완료!` 가 뜨면 구글시트에 데이터가 기입된 것

### ⑤ 결과 확인

- `output/report_voc.html` 파일을 더블클릭 → 브라우저로 열린다
  - 인사이트 3개, 제품 개선 기획안 2개, 전체 분류표 확인
- 구글시트를 열어 팀원과 공유한다
  - **분류결과** 탭: 전체 데이터 (유형별 색상)
  - **집계요약** 탭: 건수·비율 집계표
  - **URGENT** 탭: 긴급 건만 분리 → 있으면 CS팀에 당일 전달

---

## 다음 달 반복

파일명만 바꾸면 된다:

```
c:/Users/Minsoo/anaconda3/python.exe classify_voc.py data/voc_august2026.csv
c:/Users/Minsoo/anaconda3/python.exe sheets_sync.py output/classified_voc_august2026.csv --sheet-id 1PCUbNBXRvvaItiVaE24RscyuX3f7Frzye5SBkxNGiD4
```

---

## 오류 대처

| 오류 메시지                          | 원인                                                | 해결                                                      |
| ------------------------------------ | --------------------------------------------------- | --------------------------------------------------------- |
| `경로를 찾을 수 없습니다`          | `cd` 대신 `Set-Location -LiteralPath` 사용 필요 | 위 ② 명령어로 이동                                       |
| `No module named 'gspread'`        | Python 경로가 다름                                  | `c:/Users/Minsoo/anaconda3/python.exe` 경로 정확히 확인 |
| `credentials.json 파일이 없습니다` | 파일 위치 오류                                      | `[01] 리뉴어스랩` 폴더 바로 안에 파일이 있는지 확인     |
| 구글시트가 안 열린다                 | 공개 링크 미설정                                    | 시트 → 공유 → "링크가 있는 모든 사용자" → 뷰어 설정    |

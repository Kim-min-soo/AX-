# /generate

VoC CSV를 파이프라인에 통과시켜 분류 CSV와 HTML 리포트를 자동 생성합니다.

## 사용법

```
/generate data/voc.csv
/generate data/voc_july2026.csv
/generate              ← 기본값: data/voc.csv
```

## 실행 절차

1. 아래 명령을 터미널에서 실행한다:
   ```
   python classify_voc.py <csv_path> --out-dir output/
   ```
2. 실행 로그(날짜 정제·중복 제거·분류 결과)를 사용자에게 보여준다.
3. 생성된 파일 경로를 알린다:
   - `output/classified_{name}.csv`
   - `output/report_{name}.html`
4. 유형별 건수·비율 요약을 표로 출력한다.
5. URGENT 건이 있으면 별도로 강조 표시한다.

## 파이프라인 단계 (자동 수행)

| 단계 | 작업 |
|------|------|
| 정제 | 날짜 3형식 → YYYY-MM-DD 통일, 중복 제거, 결측 표시 |
| 분류 | keyword_hint + content 신호어 기반 4유형 결정론적 분류 |
| 집계 | 유형별·소분류별·Cause Tag별 건수·비율 산출 |
| 출력 | CSV + HTML 리포트 자동 생성 |

## 분류 기준 (decisions.md 참조)

- 분류 기준·경계 케이스 판단 원칙은 `decisions.md` D-04, D-05 참조
- 새 경계 케이스 발생 시 `decisions.md`에 추가 후 재실행

# /analyze

VoC CSV 파일을 읽어 데이터 품질을 점검하고 분류 준비 상태를 보고합니다.

## 사용법

```
/analyze data/voc.csv
/analyze data/voc_july2026.csv
```

## 실행 절차

1. 지정된 CSV 파일을 읽는다 (`data/voc.csv` 기본값).
2. 다음 항목을 점검하고 결과를 출력한다:
   - **총 행수**: 원본 건수 확인
   - **날짜 형식**: YYYY-MM-DD / YYYY/MM/DD / N월 M일 혼용 여부 + 해당 id 목록
   - **채널 결측**: channel 필드가 비어있는 행 id
   - **내용 결측**: content 필드가 비어있는 행 id
   - **중복 행**: content + date가 동일한 행 쌍 (id 명시)
   - **유형 오입력 의심**: keyword_hint와 내용이 불일치하는 행 (선택)
3. 정제 후 예상 건수를 알린다.
4. `python classify_voc.py <csv_path>` 실행을 제안한다.

## 출력 예시

```
[분석 결과] data/voc.csv
──────────────────────────────
원본 건수    : 45건
날짜 혼용    : 17건 (id 003, 005, 008 ...)
채널 결측    : 2건  (id 032, 035)
내용 결측    : 0건
중복 행      : 1쌍  (id 031 = id 001)
──────────────────────────────
정제 후 예상 : 44건

다음 명령으로 분류를 시작하세요:
  python classify_voc.py data/voc.csv
```

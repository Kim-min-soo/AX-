#!/usr/bin/env python3
"""
sheets_sync.py — 리뉴어스랩 VoC 분류 결과 → 구글시트 자동 기입

사전 준비:
    1. credentials.json 파일을 이 스크립트와 같은 폴더에 두세요.
       (GCP 서비스 계정 JSON 키 — SETUP_SHEETS.md 참고)
    2. 구글시트를 만들고 서비스 계정 이메일에 '편집자' 권한을 부여하세요.

Usage:
    # 새 스프레드시트 자동 생성
    python sheets_sync.py output/classified_voc.csv

    # 기존 스프레드시트에 기입 (URL의 /d/XXXX/ 부분이 ID)
    python sheets_sync.py output/classified_voc.csv --sheet-id 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms

    # 7월 데이터를 같은 시트에 추가 탭으로 기입
    python sheets_sync.py output/classified_voc_july2026.csv --sheet-id <ID>
"""

import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("[오류] 패키지 없음. 아래 명령 실행 후 재시도하세요:")
    print("  pip install gspread google-auth")
    sys.exit(1)

# Google API 권한 범위
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CRED_PATH = Path(__file__).parent / "credentials.json"

# ──────────────────────────────────────────────────────────────
# 스타일 상수 (구글시트 컬러)
# ──────────────────────────────────────────────────────────────

TYPE_COLORS = {
    "불만":    {"red": 0.99, "green": 0.91, "blue": 0.91},
    "기능 요청": {"red": 0.86, "green": 0.93, "blue": 1.0},
    "칭찬":    {"red": 0.86, "green": 0.97, "blue": 0.89},
    "일반 문의": {"red": 0.95, "green": 0.95, "blue": 0.97},
}

URGENT_COLOR = {"red": 0.99, "green": 0.80, "blue": 0.80}

HEADER_COLOR = {"red": 0.10, "green": 0.28, "blue": 0.19}  # #1a4731 (리뉴어스랩 그린)

# ──────────────────────────────────────────────────────────────
# 인증
# ──────────────────────────────────────────────────────────────

def get_client():
    if not CRED_PATH.exists():
        print(f"[오류] {CRED_PATH} 파일이 없습니다.")
        print("  SETUP_SHEETS.md 의 1~3단계를 완료한 후 재실행하세요.")
        sys.exit(1)
    creds = Credentials.from_service_account_file(str(CRED_PATH), scopes=SCOPES)
    client = gspread.authorize(creds)
    return client, creds

# ──────────────────────────────────────────────────────────────
# CSV 읽기
# ──────────────────────────────────────────────────────────────

def load_classified(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

# ──────────────────────────────────────────────────────────────
# 시트 쓰기
# ──────────────────────────────────────────────────────────────

COLS = ["id", "date", "channel", "customer_type", "content",
        "type", "subcategory", "cause_tag", "urgent", "keyword_hint"]

COL_HEADERS = ["ID", "날짜", "채널", "고객유형", "VoC 내용",
               "분류", "소분류", "원인태그", "긴급", "키워드힌트"]

def write_raw_sheet(ws, rows: list[dict]) -> None:
    """'분류결과' 시트: 전체 분류 데이터."""
    ws.clear()

    # 헤더 행
    ws.append_row(COL_HEADERS)

    # 데이터 행
    data = [[r.get(c, "") for c in COLS] for r in rows]
    if data:
        ws.append_rows(data, value_input_option="RAW")

    total_rows = len(rows) + 1  # 헤더 포함

    # ── 배치 서식 (한 번의 API 호출) ─────────────────────────────
    requests = []

    # 헤더 배경색 + 볼드
    requests.append({
        "repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": len(COLS)},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": HEADER_COLOR,
                    "textFormat": {"bold": True, "foregroundColor": {"red":1,"green":1,"blue":1}},
                    "horizontalAlignment": "CENTER",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    })

    # 유형별 행 배경색 + URGENT 강조
    type_col_idx = COLS.index("type")
    urgent_col_idx = COLS.index("urgent")

    for i, row in enumerate(rows):
        row_idx = i + 1  # 0-indexed, 헤더는 0
        vtype = row.get("type", "")
        is_urg = row.get("urgent", "") == "Y"

        bg = URGENT_COLOR if is_urg else TYPE_COLORS.get(vtype, {"red":1,"green":1,"blue":1})

        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id,
                          "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                          "startColumnIndex": 0, "endColumnIndex": len(COLS)},
                "cell": {"userEnteredFormat": {"backgroundColor": bg}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    # 컬럼 너비 조정
    col_widths = [50, 100, 80, 100, 350, 80, 100, 90, 60, 200]
    for ci, w in enumerate(col_widths):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })

    # 헤더 행 고정
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # API 일괄 실행
    ws.spreadsheet.batch_update({"requests": requests})
    print(f"  '분류결과' 시트: {len(rows)}건 기입 완료")


def write_summary_sheet(ws, rows: list[dict]) -> None:
    """'집계요약' 시트: 유형별·소분류별 집계표."""
    from collections import Counter
    ws.clear()

    total = len(rows)
    by_type = Counter(r["type"] for r in rows)
    by_subcat = Counter(r["subcategory"] for r in rows)
    by_cause = Counter(r["cause_tag"] for r in rows)
    urgent_count = sum(1 for r in rows if r.get("urgent") == "Y")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 섹션 1: 메타
    ws.append_row(["리뉴어스랩 VoC 분류 리포트 — 집계 요약"])
    ws.append_row(["생성일시", generated_at, "", "총 건수", total])
    ws.append_row([])

    # 섹션 2: 유형별
    ws.append_row(["유형", "건수", "비율(%)"])
    for t in ["불만", "기능 요청", "칭찬", "일반 문의"]:
        n = by_type.get(t, 0)
        ws.append_row([t, n, round(n / total * 100, 1) if total else 0])
    ws.append_row(["합계", total, 100])
    ws.append_row([])

    # 섹션 3: 소분류별
    ws.append_row(["소분류", "건수", "비율(%)"])
    for sc, cnt in by_subcat.most_common():
        ws.append_row([sc, cnt, round(cnt / total * 100, 1) if total else 0])
    ws.append_row([])

    # 섹션 4: Cause Tag
    ws.append_row(["Cause Tag", "건수", "비율(%)"])
    for cause, cnt in by_cause.most_common():
        ws.append_row([cause, cnt, round(cnt / total * 100, 1) if total else 0])
    ws.append_row([])

    # 섹션 5: URGENT
    ws.append_row(["URGENT 건", urgent_count, ""])
    urg_rows = [r for r in rows if r.get("urgent") == "Y"]
    for r in urg_rows:
        ws.append_row([r["id"], r["customer_type"], r["content"][:80]])

    print(f"  '집계요약' 시트: 기입 완료")


def write_urgent_sheet(ws, rows: list[dict]) -> None:
    """'URGENT' 시트: 에스컬레이션 대상만 분리."""
    ws.clear()
    urg = [r for r in rows if r.get("urgent") == "Y"]

    if not urg:
        ws.append_row(["URGENT 건 없음"])
        print(f"  'URGENT' 시트: 해당 건 없음")
        return

    ws.append_row(["ID", "날짜", "고객유형", "분류", "VoC 내용 (전문)", "키워드"])
    for r in urg:
        ws.append_row([
            r["id"], r["date"], r["customer_type"], r["type"],
            r["content"], r["keyword_hint"]
        ])

    # URGENT 시트 전체 배경 분홍
    requests = [{
        "repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 1,
                      "endRowIndex": len(urg) + 1,
                      "startColumnIndex": 0, "endColumnIndex": 6},
            "cell": {"userEnteredFormat": {"backgroundColor": URGENT_COLOR}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }]
    ws.spreadsheet.batch_update({"requests": requests})
    print(f"  'URGENT' 시트: {len(urg)}건 기입 완료")

# ──────────────────────────────────────────────────────────────
# 시트 가져오기 or 생성
# ──────────────────────────────────────────────────────────────

def get_or_create_sheet(wb, title: str):
    """스프레드시트 안에서 탭(워크시트)을 가져오거나 새로 만든다."""
    try:
        ws = wb.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = wb.add_worksheet(title=title, rows=500, cols=20)
    return ws

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="VoC 분류 결과를 구글시트에 기입")
    ap.add_argument("csv", help="classified_*.csv 경로")
    ap.add_argument("--sheet-id", default=None,
                    help="기존 스프레드시트 ID (없으면 새로 생성)")
    args = ap.parse_args()

    src = Path(args.csv)
    if not src.exists():
        print(f"[오류] 파일 없음: {src}")
        sys.exit(1)

    print(f"\n[1/4] 인증 중...")
    client, creds = get_client()
    svc_email = creds.service_account_email
    print(f"  서비스 계정: {svc_email}")

    print(f"[2/4] 데이터 로드: {src}")
    rows = load_classified(src)
    print(f"  {len(rows)}건 로드")

    print(f"[3/4] 스프레드시트 준비...")
    if args.sheet_id:
        wb = client.open_by_key(args.sheet_id)
        print(f"  기존 시트 열기: {wb.title}")
    else:
        stem = src.stem  # e.g. "classified_voc_july2026"
        title = f"리뉴어스랩 VoC 리포트 — {stem} ({datetime.now().strftime('%Y-%m-%d')})"
        wb = client.create(title)
        # 서비스 계정만 소유자로 만들어지므로 내 계정에도 공유
        print(f"  새 스프레드시트 생성: {title}")
        print(f"  URL: https://docs.google.com/spreadsheets/d/{wb.id}")
        print(f"  ※ 이 URL을 열려면 아래 명령으로 내 이메일에 공유 권한을 주세요:")
        print(f"     python sheets_sync.py {args.csv} --sheet-id {wb.id} --share <your@email.com>")

    print(f"[4/4] 시트 기입 중...")
    ws_raw    = get_or_create_sheet(wb, "분류결과")
    ws_sum    = get_or_create_sheet(wb, "집계요약")
    ws_urgent = get_or_create_sheet(wb, "URGENT")

    write_raw_sheet(ws_raw, rows)
    write_summary_sheet(ws_sum, rows)
    write_urgent_sheet(ws_urgent, rows)

    # 기본 빈 시트 삭제 (3개 탭 생성 후에 삭제해야 오류 없음)
    for default_name in ["시트1", "Sheet1"]:
        try:
            wb.del_worksheet(wb.worksheet(default_name))
            print(f"  '{default_name}' 빈 시트 삭제 완료")
        except gspread.WorksheetNotFound:
            pass

    print(f"\n완료!")
    print(f"  스프레드시트 URL:")
    print(f"  https://docs.google.com/spreadsheets/d/{wb.id}")
    print()

if __name__ == "__main__":
    main()

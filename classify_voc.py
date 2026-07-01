#!/usr/bin/env python3
"""
classify_voc.py — 리뉴어스랩 VoC 자동 분류 파이프라인

Usage:
    python classify_voc.py data/voc.csv
    python classify_voc.py data/voc_july2026.csv --out-dir output/

Output (output/ 기본):
    classified_{name}.csv    분류 결과 CSV
    report_{name}.html       주간 VoC 리포트 HTML
"""

import csv, re, sys, argparse
from pathlib import Path
from collections import Counter
from datetime import datetime

# ──────────────────────────────────────────────────────────────
# Regulatory calendar  (context/reg-calendar.md)
# ──────────────────────────────────────────────────────────────

def load_reg_calendar(base_dir: Path) -> list[dict]:
    """context/reg-calendar.md 파싱 → 규제 목록 반환. 파일 없으면 빈 리스트."""
    path = base_dir / "context" / "reg-calendar.md"
    if not path.exists():
        return []
    regs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or "규제명" in line or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) < 5 or not parts[0]:
                continue
            regs.append({
                "name":     parts[0],
                "start":    parts[1],
                "deadline": parts[2],
                "subcats":  [s.strip() for s in parts[3].split(",") if s.strip()],
                "desc":     parts[4],
            })
    return regs


# ──────────────────────────────────────────────────────────────
# Signal lists  (decisions.md D-04, D-05)
# ──────────────────────────────────────────────────────────────

COMPLAINT = [
    "안됩니다", "안 됩니다", "오류가", "오류", "끊깁니다", "끊겨",
    "날아갔", "반려됐", "반려됩니", "차이납니다", "차이가 납니다",
    "불편합니다", "불편합니", "말이됩니까", "낚인", "복구해주세요",
    "틀린", "잘못됐", "문제가 있", "멈추는", "로딩만", "실패",
    "안 들어오", "다르게 나옵니다", "낮게 나옵니다", "전송 실패",
    "작동하지 않습니다", "처리가 안", "소수점 오류", "수치가 다르",
    "지속적으로 차이", "다르게 표시", "이상이 있", "수정이 안",
]

FEATURE_REQ = [
    "추가해주세요", "추가해 주세요", "요청드립니다", "있으면 좋겠",
    "필요합니다", "해주시면 좋겠", "제공해주세요", "개발해주세요",
    "만들어 주시면", "만들어주시면", "만들어 주세요", "지원해줄 수 있나요",
    "기능을 추가", "기능이 있으면", "기능을 요청", "기능 개선 요청",
    "요청드립", "있었으면", "해주실 수 있나요", "포함해주세요",
    "넣어주세요", "완화를 요청", "늘려주세요", "추가되면",
]

PRAISE = [
    "감사합니다", "감사해요", "감사드립니다", "덕분에",
    "만족스럽습니다", "인상적이었습니다",
    "큰 도움", "편해졌습니다", "잘 쓰고", "편하게 쓰고", "좋았습니다",
    "무사히", "정말 좋", "도움이 됩니다", "도움이 됐습니다",
    "수월해졌", "줄었습니다", "줄었어요", "해결해주셨",
    "시간이 절반", "업무에 지장이 없", "편리합니다", "편리해요",
    "크게 줄었", "절반으로", "40% 줄었", "직관적",
]

INQUIRY = [
    "언제인가요", "어떻게 되나요", "있나요", "맞나요", "알고 싶습니다",
    "가능한가요", "궁금합니다", "확인하고 싶습니다", "문의드립니다",
    "문의 드립니다", "알 수 있을까요", "알려주세요", "안내 부탁드립니다",
    "확인 부탁드립니다", "해당되는지", "어떻게 해야", "어떤 방식이",
    "어떻게 활용", "어떻게 계산", "어디서 가져와야", "있는지 확인",
    "어떻게 되는지", "가능한지 문의", "어떤 데이터를", "어떤 형식으로",
    "적합한지 알고", "내장되어 있나요", "활용 가능한지",
]

URGENT_KW = [
    "긴급합니다", "긴급 대응", "긴급 처리", "마감일이 지났",
    "수출 계약이 위험", "수출 계약", "반려됐습니다", "위험합니다",
    "즉시", "계약이 위험", "긴급",
]

# ──────────────────────────────────────────────────────────────
# Date normalization  (decisions.md D-02)
# ──────────────────────────────────────────────────────────────

def normalize_date(raw: str, year: int = 2026) -> str:
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{1,2})월\s*(\d{1,2})일$", raw)
    if m:
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return raw

# ──────────────────────────────────────────────────────────────
# Classification  (decisions.md D-04, D-05)
# ──────────────────────────────────────────────────────────────

def _score(signals: list, text: str) -> int:
    """Count distinct signal matches, avoiding double-counting overlapping substrings."""
    matched: set[str] = set()
    for s in signals:
        if s in text:
            if not any(s in m or m in s for m in matched):
                matched.add(s)
    return len(matched)

def classify_type(content: str, keyword_hint: str) -> str:
    ps = _score(PRAISE,       content)
    cs = _score(COMPLAINT,    content)
    fs = _score(FEATURE_REQ,  content)
    qs = _score(INQUIRY,      content)

    # Unambiguous praise
    if ps > 0 and cs == 0 and fs == 0:
        return "칭찬"

    # Boundary: complaint + feature request → primary-action principle (D-05 케이스 A)
    if cs > 0 and fs > 0:
        new_feat_kw = [
            "추가해주세요", "추가해 주세요", "있으면 좋겠",
            "기능을 추가", "기능이 있으면", "요청드립니다",
            "해주실 수 있나요", "필요합니다", "늘려주세요",
        ]
        fix_kw = ["복구해주세요", "수정해주세요", "해결해주세요", "고쳐주세요",
                  "확인이 필요", "확인 부탁드립니다", "확인해주세요"]
        nf = sum(1 for s in new_feat_kw if s in content)
        fx = sum(1 for s in fix_kw      if s in content)
        return "기능 요청" if nf > fx else "불만"

    scores = {"불만": cs, "기능 요청": fs, "칭찬": ps, "일반 문의": qs}
    best = max(scores.values())
    if best == 0:
        return "일반 문의"
    for t in ["불만", "기능 요청", "일반 문의", "칭찬"]:
        if scores[t] == best:
            return t

def is_urgent(content: str, keyword_hint: str) -> bool:
    return any(k in content or k in keyword_hint for k in URGENT_KW)

def get_subcategory(vtype: str, kh: str, ct: str) -> str:
    kh, ct = kh.lower(), ct.lower()
    if vtype == "불만":
        if any(k in kh or k in ct for k in ["로그인", "세션", "로딩", "전송실패", "작동하지", "멈추는", "전송 실패"]):
            return "시스템오류"
        if any(k in kh or k in ct for k in ["계산오류", "gwp", "ipcc", "배출계수", "소수점", "수치가 다", "차이가 납"]):
            return "계산오류"
        if any(k in kh or k in ct for k in ["api", "erp", "연동오류", "연동"]):
            return "연동오류"
        return "기능제한"

    if vtype == "기능 요청":
        if any(k in kh or k in ct for k in ["보고서자동화", "pdf", "분기", "통합보고", "자동 출력", "자동 생성", "월별추이", "그룹보고", "자동리포트"]):
            return "보고서자동화"
        if any(k in kh or k in ct for k in ["데이터공유", "공유", "공문템플릿", "실시간", "접근권한", "외부검증", "내보내기"]):
            return "데이터공유"
        if any(k in kh or k in ct for k in ["대시보드", "차트", "현황판", "모니터링", "경영진보고"]):
            return "대시보드"
        return "규제가이드"

    if vtype == "칭찬":
        if any(k in kh or k in ct for k in ["cs대응", "온보딩", "화상미팅", "고객만족", "담당자", "cs", "만족"]):
            return "CS대응"
        if any(k in kh or k in ct for k in ["자동화", "업무효율", "시간단축", "절반", "줄었", "40%", "시간이"]):
            return "플랫폼효과"
        return "UI개선"

    # 일반 문의
    if any(k in kh or k in ct for k in ["cbam", "인증서", "신고기한", "신고일정", "전환기간", "신고마감"]):
        return "CBAM절차"
    if any(k in kh or k in ct for k in ["csrd", "이중중요성", "dma", "esrs", "공시범위"]):
        return "CSRD해석"
    if any(k in kh or k in ct for k in ["scope", "lca", "pcf", "gwp", "배출계수", "계산방법", "단위", "입력방법", "입력가이드"]):
        return "계산방법"
    return "기타규제"

def get_cause_tag(vtype: str, kh: str, ct: str) -> str:
    combined = (kh + " " + ct).lower()
    if any(k in combined for k in ["긴급", "마감", "기한", "반려", "위험", "계약이"]):
        return "기한임박"
    if vtype == "불만":
        return "제품결함"
    if vtype in ("일반 문의", "기능 요청"):
        if any(k in combined for k in ["cbam", "csrd", "tcfd", "gri", "규제", "의무", "공시", "인증서", "신고"]):
            return "규제불안"
        if any(k in combined for k in ["어떻게", "방법", "모르겠", "어디서", "입력방법"]):
            return "사용법미숙"
    return "원인불명"

# ──────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────

def process(path: Path) -> tuple[list[dict], list[str]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    log, result = [], []
    seen: dict[tuple, str] = {}

    for r in rows:
        rid     = r.get("id", "").strip()
        content = r.get("content", "").strip()
        date_r  = r.get("date", "").strip()
        channel = r.get("channel", "").strip() or "(결측)"
        ctype   = r.get("customer_type", "").strip()
        kh      = r.get("keyword_hint", "").strip()

        date_n = normalize_date(date_r)
        if date_n != date_r:
            log.append(f"날짜정제  id {rid}: {date_r!r} → {date_n!r}")

        dup_key = (content, date_r)
        if dup_key in seen:
            log.append(f"중복제거  id {rid} 제거 (id {seen[dup_key]}와 동일)")
            continue
        if content:
            seen[dup_key] = rid
        if not content:
            log.append(f"결측건너뜀 id {rid}: content 없음")
            continue

        vtype  = classify_type(content, kh)
        subcat = get_subcategory(vtype, kh, content)
        cause  = get_cause_tag(vtype, kh, content)
        urg    = is_urgent(content, kh)

        result.append({
            "id": rid, "date": date_n, "channel": channel,
            "customer_type": ctype, "content": content, "keyword_hint": kh,
            "type": vtype, "subcategory": subcat,
            "cause_tag": cause, "urgent": "Y" if urg else "",
        })

    return result, log

# ──────────────────────────────────────────────────────────────
# CSV output
# ──────────────────────────────────────────────────────────────

def write_csv(rows: list[dict], path: Path) -> None:
    fields = ["id","date","channel","customer_type","content","keyword_hint",
              "type","subcategory","cause_tag","urgent"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

# ──────────────────────────────────────────────────────────────
# HTML generation
# ──────────────────────────────────────────────────────────────

TYPE_STYLE = {
    "불만":    ("fde8e8","b91c1c"),
    "기능 요청": ("dbeafe","1d4ed8"),
    "칭찬":    ("dcfce7","166534"),
    "일반 문의": ("f1f5f9","475569"),
}
CTYPE_STYLE = {
    "OEM":      ("fef3c7","92400e"),
    "1차 협력사": ("dbeafe","1e40af"),
    "2차 협력사": ("ede9fe","6d28d9"),
}
CAUSE_COLOR = {
    "규제불안": ("fff7ed","c2410c"),
    "제품결함": ("fef2f2","991b1b"),
    "사용법미숙":("f0fdf4","166534"),
    "기한임박": ("fffbeb","b45309"),
    "원인불명": ("f8fafc","64748b"),
}

def badge(text: str, bg: str, fg: str) -> str:
    return (f'<span style="display:inline-block;background:#{bg};color:#{fg};'
            f'font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:5px;'
            f'white-space:nowrap">{text}</span>')

def type_badge(t: str) -> str:
    bg, fg = TYPE_STYLE.get(t, ("eee","333"))
    return badge(t, bg, fg)

def ctype_badge(ct: str) -> str:
    bg, fg = CTYPE_STYLE.get(ct, ("f1f5f9","475569"))
    return badge(ct, bg, fg)

def cause_badge(c: str) -> str:
    bg, fg = CAUSE_COLOR.get(c, ("f1f5f9","475569"))
    return badge(c, bg, fg)

def bar_chart(items: list[tuple[str,int,int]], bar_colors: dict[str,str]) -> str:
    total = sum(v for _,v,_ in items) or 1
    lines = []
    for label, count, pct in items:
        color = bar_colors.get(label, "94a3b8")
        w = max(3, round(count / total * 100))
        lines.append(f"""
      <div style="margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;font-size:12px;font-weight:600;margin-bottom:4px">
          <span>{label}</span><span style="color:#555">{count}건 ({pct}%)</span>
        </div>
        <div style="background:#f0f3f7;border-radius:6px;height:24px;overflow:hidden">
          <div style="width:{w}%;height:100%;background:#{color};border-radius:6px;
                      display:flex;align-items:center;padding-left:8px;
                      color:#fff;font-size:11px;font-weight:700">{count}</div>
        </div>
      </div>""")
    return "".join(lines)

def _gen_insights_html(rows, by_type, by_subcat, by_cause, urgent_rows, total,
                       reg_calendar=None):
    """데이터 패턴을 감지해 인사이트 카드 HTML을 동적 생성."""
    if total == 0:
        return ""

    cal = reg_calendar or []

    def regs_for(*subcats) -> str:
        """관련 소분류를 포함하는 규제명을 캘린더에서 뽑아 '·' 구분 문자열로 반환."""
        names = [r["name"] for r in cal if any(s in r["subcats"] for s in subcats)]
        return "·".join(names) if names else "·".join(subcats[:2])

    def card(color, num_label, title, sections):
        body = ""
        for lbl, txt, is_act in sections:
            cls = "ins-action" if is_act else "ins-row"
            body += (f'<div class="{cls}">'
                     f'<div class="ins-lbl">{lbl}</div>'
                     f'<div class="ins-body">{txt}</div></div>')
        return (f'<div class="ins-card" style="border-color:#{color}">'
                f'<div class="ins-num" style="color:#{color}">{num_label}</div>'
                f'<div class="ins-title">{title}</div>{body}</div>')

    cards = []

    # ── 인사이트 1: 규제 대응 문의 집중 ──────────────────────────
    inq_n   = by_type.get("일반 문의", 0)
    reg_n   = by_cause.get("규제불안", 0)
    urg_n   = len(urgent_rows)
    reg_subcats = ["CBAM절차","CSRD해석","기타규제","계산방법"]
    top_reg = max(reg_subcats, key=lambda s: by_subcat.get(s, 0))
    top_reg_n = by_subcat.get(top_reg, 0)
    if reg_n / total >= 0.28 or top_reg_n >= 5:
        urg_ids = ", ".join(f"id {r['id']}" for r in urgent_rows)
        obs = (f"전체 {total}건 중 규제불안 cause tag {reg_n}건"
               f"({round(reg_n/total*100,1)}%). "
               f"일반 문의 {inq_n}건의 상위 소분류: {top_reg} {top_reg_n}건.")
        cond = f"urgent=Y {urg_n}건" + (f" — {urg_ids}" if urg_ids else "") + "."
        active_regs = regs_for("CBAM절차", "CSRD해석", "기타규제")
        deadlines   = [r for r in cal if r["deadline"]]
        dl_str      = (f" {deadlines[0]['name']} 마감({deadlines[0]['deadline']}) 포함."
                       if deadlines else "")
        ctx  = (f"{active_regs} 규제 복잡도 증가로 절차·기한 문의가 집중.{dl_str} "
                f"플랫폼 내 안내 부재 시 고객이 마감을 놓치는 구조적 리스크.")
        act  = ("① 규제별 단계 체크리스트 플랫폼 내 구축<br>"
                "② 마감 30일·7일 전 자동 알림 개발<br>"
                "③ URGENT 건 CS 당일 에스컬레이션 배정")
        cards.append(card("c0392b", "인사이트 01 — 규제",
                          f"규제 대응 문의 집중: {top_reg} {top_reg_n}건 단일 최다",
                          [("관찰",obs,False),("조건",cond,False),
                           ("맥락",ctx,False),("행동",act,True)]))

    # ── 인사이트 2: 자동화 수요 급증 ─────────────────────────────
    feat_rows = [r for r in rows if r["type"] == "기능 요청"]
    feat_n    = len(feat_rows)
    auto_n    = sum(by_subcat.get(s,0) for s in ["보고서자동화","규제가이드"])
    if feat_n >= 5 and auto_n >= 3:
        auto_pct = round(auto_n / feat_n * 100, 1)
        feat_sub_cnt = Counter(r["subcategory"] for r in feat_rows)
        top_fsub, top_fsub_n = feat_sub_cnt.most_common(1)[0]
        obs = (f"기능 요청 {feat_n}건 중 보고서자동화·규제가이드 소분류에 "
               f"{auto_n}건({auto_pct}%) 집중.")
        auto_regs = regs_for("보고서자동화", "규제가이드")
        ctx  = (f"다중 규제 프레임워크({auto_regs}) 동시 대응으로 보고 자동화 수요 급증. "
                "수작업 보고는 규모 증가 시 오류 리스크 → 플랫폼 신뢰도 직결.")
        act  = (f"① 상위 기능요청 '{top_fsub}' {top_fsub_n}건 → 다음 스프린트 최우선<br>"
                "② 다중 프레임워크 데이터 자동 매핑 로드맵 포함<br>"
                "③ 규제가이드 기능 선제 개발 착수")
        cards.append(card("1a56a0", "인사이트 02 — 자동화",
                          f"자동화·규제가이드 수요 집중 ({auto_n}건, 기능요청의 {auto_pct}%)",
                          [("관찰",obs,False),("맥락",ctx,False),("행동",act,True)]))

    # ── 인사이트 3: 제품 품질 / 계산 신뢰 위기 ─────────────────
    complaint_n   = by_type.get("불만", 0)
    prod_fault_n  = by_cause.get("제품결함", 0)
    calc_err_n    = by_subcat.get("계산오류", 0)
    if calc_err_n >= 2 or (complaint_n > 0 and prod_fault_n >= complaint_n):
        obs = (f"불만 {complaint_n}건 중 제품결함 cause tag {prod_fault_n}건. "
               f"계산오류 소분류 {calc_err_n}건이 서로 다른 고객·채널에서 독립 발생.")
        quality_regs = regs_for("CBAM절차", "CSRD해석")
        ctx  = (f"{quality_regs} 보고 맥락에서 수치 오류 = 법적 책임 문제. "
                "동일 계산 로직 오류는 전체 고객에 확산 가능.")
        act  = ("① 계산 로직 긴급 QA — 영향 고객 범위 파악<br>"
                "② 배출계수 DB 버전 관리·변경 이력 공지 체계 도입<br>"
                "③ 외부 기준값 대비 검증 리포트 기능 검토")
        cards.append(card("d97706", "인사이트 03 — 품질 위기",
                          f"제품결함 {prod_fault_n}건 / 계산오류 {calc_err_n}건 독립 발생",
                          [("관찰",obs,False),("맥락",ctx,False),("행동",act,True)]))

    if not cards:
        return ""
    grid = "".join(cards)
    return f"""
<div style="margin-bottom:20px">
  <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
              color:#444;margin-bottom:12px">자동 인사이트 ({len(cards)}개)</div>
  <div class="ins-grid">{grid}</div>
</div>"""


def _gen_proposals_html(rows, by_type, by_subcat, total):
    """decisions.md D-15·D-16 기준: 기능요청·불만 상위 소분류 → 기획안 자동 생성."""
    if total == 0:
        return ""

    def score(sub_rows, all_n):
        n       = len(sub_rows)
        freq    = min(round(n / all_n * 10, 1), 5.0)
        has_oem = any(r["customer_type"] == "OEM"   for r in sub_rows)
        has_urg = any(r["urgent"] == "Y"             for r in sub_rows)
        has_pfn = any(r["cause_tag"] == "제품결함"   for r in sub_rows)
        has_reg = any(r["cause_tag"] == "규제불안"   for r in sub_rows)
        impact  = (3 if has_oem else 0) + (3 if has_urg else 0) + \
                  (2 if has_pfn else 0) + (1 if has_reg else 0)
        total_s = freq + impact
        grade   = "HIGH" if total_s >= 8 else "MEDIUM" if total_s >= 5 else "LOW"
        gcolor  = "dc2626" if grade == "HIGH" else "d97706" if grade == "MEDIUM" else "64748b"
        return freq, impact, total_s, grade, gcolor

    def make_card(num, voc_type, sub, sub_rows, all_n):
        freq, impact, total_s, grade, gc = score(sub_rows, all_n)
        kws = []
        for r in sub_rows:
            kws.extend(k.strip() for k in r.get("keyword_hint","").split(",") if k.strip())
        top_kw = [kw for kw,_ in Counter(kws).most_common(3)]
        kw_html = " ".join(
            f'<span style="background:#f3f4f6;border-radius:4px;padding:2px 8px;'
            f'font-size:11px">{k}</span>' for k in top_kw)
        ids = [r["id"] for r in sub_rows]
        ids_str = ", ".join(f"#{i}" for i in ids[:5])
        if len(ids) > 5:
            ids_str += f" 외 {len(ids)-5}건"
        return f"""
  <div style="background:#fff;border-radius:12px;padding:22px 24px;
              border-left:5px solid #{gc};margin-bottom:0">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div>
        <span style="font-size:11px;font-weight:700;color:#888;text-transform:uppercase;
                     letter-spacing:.5px">기획안 {num}</span>
        <span style="margin-left:8px;font-size:11px;background:#f3f4f6;
                     padding:2px 8px;border-radius:4px">{voc_type}</span>
      </div>
      <span style="font-size:12px;font-weight:800;color:#{gc};background:#fff8f8;
                   padding:4px 12px;border-radius:20px;border:1.5px solid #{gc}">
        {grade} {total_s:.1f}점
      </span>
    </div>
    <div style="font-size:16px;font-weight:800;margin-bottom:10px">
      {sub} 소분류 {len(sub_rows)}건 → 제품 개선
    </div>
    <div style="margin-bottom:8px;font-size:12px;color:#555">
      <span style="font-weight:700">근거 VoC:</span> {ids_str}
    </div>
    {f'<div style="margin-bottom:10px">{kw_html}</div>' if kw_html else ''}
    <div style="font-size:12px;color:#555">
      <span style="font-weight:700">우선순위:</span>
      빈도 {freq:.1f} + 임팩트 {impact:.0f} = {total_s:.1f}점
    </div>
  </div>"""

    # 불만·기능요청 소분류 전체를 점수로 순위 매겨 상위 2개 선정 (방식 A)
    candidates = [r for r in rows if r["type"] in ("기능 요청", "불만")]

    from collections import defaultdict
    sub_groups = defaultdict(list)
    for r in candidates:
        sub_groups[(r["type"], r["subcategory"])].append(r)

    ranked = sorted(
        sub_groups.items(),
        key=lambda item: score(item[1], total)[2],  # total_s 기준 내림차순
        reverse=True,
    )

    cards = []
    for idx, ((voc_type, sub), sub_rows) in enumerate(ranked[:2]):
        cards.append(make_card(f"0{idx+1}", voc_type, sub, sub_rows, total))

    if not cards:
        return ""
    grid = "".join(cards)
    return f"""
<div style="margin-bottom:20px">
  <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
              color:#444;margin-bottom:12px">제품 개선 기획안 (자동 생성)</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">{grid}</div>
</div>"""


def generate_html(rows: list[dict], source_file: str, base_dir: Path = None) -> str:
    total = len(rows)
    by_type   = Counter(r["type"] for r in rows)
    by_subcat = Counter(r["subcategory"] for r in rows)
    by_cause  = Counter(r["cause_tag"] for r in rows)
    urgent_rows = [r for r in rows if r["urgent"] == "Y"]
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── 인사이트 / 기획안 (새 섹션) ──────────────────────────────
    reg_calendar    = load_reg_calendar(base_dir) if base_dir else []
    insights_html   = _gen_insights_html(rows, by_type, by_subcat, by_cause,
                                         urgent_rows, total, reg_calendar)
    proposals_html  = _gen_proposals_html(rows, by_type, by_subcat, total)

    # ── Stat cards ──────────────────────────────────────────────
    def stat_card(n, lbl, pct_str, top_color, n_color):
        return f"""
    <div style="background:#fff;border-radius:12px;padding:18px 16px;text-align:center;
                border-top:4px solid #{top_color}">
      <div style="font-size:36px;font-weight:800;color:#{n_color};line-height:1">{n}</div>
      <div style="font-size:12px;color:#666;margin-top:4px">{lbl}</div>
      <div style="font-size:12px;font-weight:600;margin-top:4px;color:#{n_color}">{pct_str}</div>
    </div>"""

    def pct(t):
        return f"{round(by_type.get(t,0)/total*100,1)}%" if total else "0%"

    urg_card = stat_card(
        len(urgent_rows), "URGENT", f"{len(urgent_rows)}건 당일 에스컬레이션",
        "dc2626", "dc2626")
    complaint_card = stat_card(
        by_type.get("불만",0), "불만", pct("불만"), "c0392b","c0392b")
    feat_card = stat_card(
        by_type.get("기능 요청",0), "기능 요청", pct("기능 요청"), "1a56a0","1a56a0")
    praise_card = stat_card(
        by_type.get("칭찬",0), "칭찬", pct("칭찬"), "166534","166534")
    inq_card = stat_card(
        by_type.get("일반 문의",0), "일반 문의", pct("일반 문의"), "475569","475569")

    # ── URGENT alert ─────────────────────────────────────────────
    urg_alert = ""
    if urgent_rows:
        urg_items = "".join(
            f'<li style="margin-bottom:6px"><b>[{r["id"]}]</b> {r["customer_type"]} · '
            f'{r["date"]} — {r["content"]}</li>'
            for r in urgent_rows
        )
        urg_alert = f"""
  <div style="background:#fff5f5;border:2px solid #fca5a5;border-radius:10px;
              padding:16px 20px;margin-bottom:20px">
    <div style="font-size:11px;font-weight:800;color:#dc2626;letter-spacing:.5px;
                text-transform:uppercase;margin-bottom:8px">
      ⚠ URGENT — 당일 에스컬레이션 필요 ({len(urgent_rows)}건)
    </div>
    <ul style="list-style:none;font-size:13px;color:#7f1d1d">{urg_items}</ul>
  </div>"""

    # ── Type distribution chart ───────────────────────────────────
    type_items = [
        (t, by_type.get(t,0), round(by_type.get(t,0)/total*100,1) if total else 0)
        for t in ["일반 문의","기능 요청","불만","칭찬"]
    ]
    type_colors = {"불만":"c0392b","기능 요청":"1a56a0","칭찬":"166534","일반 문의":"475569"}
    type_chart_html = bar_chart(type_items, type_colors)

    # ── Cause tag chart ──────────────────────────────────────────
    cause_items = [
        (c, by_cause.get(c,0), round(by_cause.get(c,0)/total*100,1) if total else 0)
        for c in ["규제불안","원인불명","제품결함","사용법미숙","기한임박"]
        if by_cause.get(c,0) > 0
    ]
    cause_colors = {"규제불안":"c2410c","제품결함":"991b1b","사용법미숙":"166534",
                    "기한임박":"b45309","원인불명":"64748b"}
    cause_chart_html = bar_chart(cause_items, cause_colors)

    # ── Filter buttons ─────────────────────────────────────────────
    filter_btns = (
        '<button class="fb on" onclick="filter(\'all\')">전체</button>'
        '<button class="fb" onclick="filter(\'불만\')">불만</button>'
        '<button class="fb" onclick="filter(\'기능 요청\')">기능 요청</button>'
        '<button class="fb" onclick="filter(\'칭찬\')">칭찬</button>'
        '<button class="fb" onclick="filter(\'일반 문의\')">일반 문의</button>'
    )
    if urgent_rows:
        filter_btns += '<button class="fb" onclick="filter(\'urgent\')">⚠ URGENT</button>'

    # ── Table rows ─────────────────────────────────────────────────
    table_rows = ""
    for r in rows:
        urg_badge = ('<span style="display:inline-block;background:#dc2626;color:#fff;'
                     'font-size:9px;font-weight:800;padding:1px 5px;border-radius:3px;'
                     'margin-left:4px">URG</span>') if r["urgent"] == "Y" else ""
        table_rows += (
            f'<tr data-type="{r["type"]}" data-urgent="{r["urgent"]}">'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5;font-family:monospace;font-size:11px">{r["id"]}</td>'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5;font-size:11px;white-space:nowrap">{r["date"]}</td>'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5">{ctype_badge(r["customer_type"])}</td>'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5;font-size:12px;min-width:280px">{r["content"]}{urg_badge}</td>'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5">{type_badge(r["type"])}</td>'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5;font-size:11px;color:#666">{r["subcategory"]}</td>'
            f'<td style="padding:7px 8px;border-bottom:1px solid #f0f2f5">{cause_badge(r["cause_tag"])}</td>'
            f'</tr>\n'
        )

    # ── Final HTML ─────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>리뉴어스랩 VoC 리포트 — {source_file}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans KR',sans-serif;
     background:#eef1f6;color:#1c2333;font-size:14px;line-height:1.6}}
.wrap{{max-width:1080px;margin:0 auto;padding:32px 20px}}
.fb{{padding:5px 13px;border:1.5px solid #d1d5db;border-radius:20px;font-size:12px;
     font-weight:600;cursor:pointer;background:#fff;color:#555;margin-right:6px;margin-bottom:6px}}
.fb.on{{background:#1c2333;color:#fff;border-color:#1c2333}}
table{{width:100%;border-collapse:collapse}}
thead th{{background:#f8f9fb;font-size:10px;font-weight:700;text-transform:uppercase;
          letter-spacing:.4px;color:#6b7280;padding:8px 8px;text-align:left;
          border-bottom:2px solid #e5e7eb;white-space:nowrap}}
tbody tr:hover{{background:#fafbfc}}
.ins-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-bottom:4px}}
.ins-card{{background:#fff;border-radius:12px;padding:20px 22px;border-top:4px solid #ccc}}
.ins-num{{font-size:11px;font-weight:800;letter-spacing:.5px;text-transform:uppercase;margin-bottom:6px}}
.ins-title{{font-size:14px;font-weight:700;margin-bottom:12px;color:#1c2333}}
.ins-row{{display:flex;gap:10px;margin-bottom:8px;font-size:12px}}
.ins-action{{display:flex;gap:10px;margin-top:10px;padding-top:10px;
             border-top:1px solid #f0f2f5;font-size:12px}}
.ins-lbl{{flex-shrink:0;font-weight:700;color:#888;width:32px}}
.ins-body{{color:#444;line-height:1.55}}
</style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <div style="background:#1a4731;color:#fff;border-radius:14px;padding:26px 30px;margin-bottom:16px">
    <div style="display:inline-block;background:rgba(255,255,255,.18);font-size:11px;
                font-weight:700;letter-spacing:.8px;padding:3px 12px;border-radius:20px;
                margin-bottom:10px;text-transform:uppercase">Auto-generated · VoC Pipeline</div>
    <h1 style="font-size:20px;font-weight:800;margin-bottom:10px">
      리뉴어스랩 VoC 분류 리포트
    </h1>
    <div style="display:flex;gap:20px;font-size:12px;opacity:.82;flex-wrap:wrap">
      <span>📄 {source_file}</span>
      <span>📊 총 {total}건 분류</span>
      <span>🕐 생성: {generated_at}</span>
    </div>
  </div>

  {urg_alert}

  <!-- Stat cards -->
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:20px">
    {urg_card}{complaint_card}{feat_card}{praise_card}{inq_card}
  </div>

  <!-- Charts -->
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
    <div style="background:#fff;border-radius:12px;padding:22px 24px">
      <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
                  color:#444;padding-bottom:12px;margin-bottom:16px;border-bottom:1px solid #eee">
        유형 분포
      </div>
      {type_chart_html}
    </div>
    <div style="background:#fff;border-radius:12px;padding:22px 24px">
      <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
                  color:#444;padding-bottom:12px;margin-bottom:16px;border-bottom:1px solid #eee">
        Cause Tag 분포
      </div>
      {cause_chart_html}
    </div>
  </div>

  <!-- Full classification table -->
  <div style="background:#fff;border-radius:12px;padding:22px 24px;margin-bottom:20px">
    <div style="font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
                color:#444;padding-bottom:12px;margin-bottom:12px;border-bottom:1px solid #eee">
      전체 분류표 ({total}건)
    </div>
    <div style="margin-bottom:12px">{filter_btns}</div>
    <div id="count" style="font-size:12px;color:#9ca3af;margin-bottom:10px">
      <span id="cnt">{total}</span>건 표시 중
    </div>
    <div style="overflow-x:auto">
      <table id="tbl">
        <thead><tr>
          <th>ID</th><th>날짜</th><th>고객유형</th><th>내용 요약</th>
          <th>분류</th><th>소분류</th><th>Cause</th>
        </tr></thead>
        <tbody>{table_rows}</tbody>
      </table>
    </div>
  </div>

  {insights_html}

  {proposals_html}

  <div style="text-align:center;font-size:11px;color:#9ca3af;padding-bottom:20px">
    classify_voc.py · 리뉴어스랩 VoC 파이프라인 · {generated_at}
  </div>
</div>

<script>
function filter(type) {{
  document.querySelectorAll('.fb').forEach(b => b.classList.remove('on'));
  event.target.classList.add('on');
  let count = 0;
  document.querySelectorAll('#tbl tbody tr').forEach(tr => {{
    const match = type === 'all'
      || (type === 'urgent' && tr.dataset.urgent === 'Y')
      || tr.dataset.type === type;
    tr.style.display = match ? '' : 'none';
    if (match) count++;
  }});
  document.getElementById('cnt').textContent = count;
}}
</script>
</body>
</html>"""

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="리뉴어스랩 VoC 분류 파이프라인")
    ap.add_argument("csv", help="입력 CSV 파일 경로")
    ap.add_argument("--out-dir", default="output", help="출력 폴더 (default: output/)")
    args = ap.parse_args()

    src = Path(args.csv)
    if not src.exists():
        print(f"[오류] 파일 없음: {src}")
        sys.exit(1)

    out = Path(args.out_dir)
    out.mkdir(exist_ok=True)

    print(f"\n[1/4] 로드 중: {src}")
    rows, log = process(src)

    print(f"[2/4] 정제 로그:")
    for line in log:
        print(f"      {line}")
    if not log:
        print("      (정제 사항 없음)")

    print(f"[3/4] 분류 완료: {len(rows)}건")
    by_type = Counter(r["type"] for r in rows)
    total = len(rows)
    for t in ["불만","기능 요청","칭찬","일반 문의"]:
        n = by_type.get(t, 0)
        print(f"      {t}: {n}건 ({round(n/total*100,1) if total else 0}%)")
    urg = [r for r in rows if r["urgent"] == "Y"]
    if urg:
        ids = [r['id'] for r in urg]
        print(f"      [URGENT] {len(urg)}건 -> {ids}")

    stem = src.stem
    csv_out  = out / f"classified_{stem}.csv"
    html_out = out / f"report_{stem}.html"

    write_csv(rows, csv_out)
    html = generate_html(rows, src.name, base_dir=src.parent.parent)
    html_out.write_text(html, encoding="utf-8")

    print(f"[4/4] 출력 완료:")
    print(f"      CSV  → {csv_out}")
    print(f"      HTML → {html_out}")
    print()

if __name__ == "__main__":
    main()

"""매크로 payload 게이트 — LLM 호출 *전*에 상류 피드(yfinance) 오염을 잡는다.

2026-07-12 신설. 블라인드 감사에서 확인된 사고:
  - 07-03: 전일(07-02) 매크로 표를 그대로 싣고 당일 사건으로 서술(스테일).
  - 07-09: 전일 종가 대비 실제 -4.76%를 +0.62%로 표기(체인 브레이크).
  - 06-17: KOSPI +1.58% vs KOSPI200 +9.73% 물리 불가 괴리를 서사화.
주 오염원은 LLM이 아니라 매크로 피드다. 텍스트 검증기로는 못 막으므로 payload 단에서 막는다.

동작: gate_macro()가 직전 발행 스냅샷(history)과 대조해 이상을 반환한다.
이상이 있으면 호출부가 (a) LLM 프롬프트에 "매크로 서사 금지"를 주입하고
(b) 매크로 섹션에 고지를 붙인다. 표 자체는 계속 싣되(연속성) 서사만 봉인한다.
"""
from __future__ import annotations

import json
from pathlib import Path

# 지수 1일 등락률 물리 한계(pp). KOSPI vs KOSPI200 하루 괴리가 이 이상이면 데이터 오류.
DIVERGENCE_LIMIT_PP = 2.0
# 체인 검사 허용 오차(pp).
CHAIN_TOL_PP = 0.5


def _snapshot_key(macro) -> list:
    """비교용 정규화: [(label, round(latest,4), round(1d%,4)), ...]"""
    out = []
    for m in macro:
        d1 = m.change_pct_1d
        out.append([m.label, round(m.latest, 4), None if d1 is None else round(d1, 4)])
    return out


def gate_macro(macro, history_path: Path) -> list[str]:
    """직전 발행 스냅샷과 대조해 이상 목록을 반환(빈 리스트면 정상).

    부작용: 오늘 스냅샷을 history에 append(항상). 이상이어도 기록은 남긴다.
    """
    issues: list[str] = []
    today = _snapshot_key(macro)

    # 1) 직전 스냅샷 로드
    prev = None
    try:
        if history_path.exists():
            hist = json.loads(history_path.read_text())
            if hist:
                prev = hist[-1]
    except Exception:
        hist = []
        prev = None
    else:
        hist = json.loads(history_path.read_text()) if history_path.exists() else []

    # 2) M1 스테일: 오늘 == 직전(전 지표 소수점까지 동일) → 피드 미갱신
    if prev is not None and prev.get("snapshot") == today:
        issues.append(
            f"매크로 스테일: 오늘 스냅샷이 직전 발행({prev.get('date','?')})과 완전 동일 — 피드 미갱신 의심"
        )

    # 3) M2 체인 브레이크: 오늘 종가 vs 직전 종가로 계산한 1일% ≠ 표기 1일%
    if prev is not None and prev.get("snapshot"):
        prev_by_label = {row[0]: row for row in prev["snapshot"]}
        for m in macro:
            pr = prev_by_label.get(m.label)
            if not pr or m.change_pct_1d is None:
                continue
            prev_latest = pr[1]
            if prev_latest and prev_latest > 0:
                implied = (m.latest / prev_latest - 1) * 100
                if abs(implied - m.change_pct_1d) > CHAIN_TOL_PP:
                    issues.append(
                        f"체인 브레이크({m.label}): 직전 종가 {prev_latest} 대비 실제 {implied:+.2f}% "
                        f"인데 표기 {m.change_pct_1d:+.2f}%"
                    )

    # 4) M3 지수 괴리: KOSPI vs KOSPI200 1일 괴리 > 2pp → 물리 불가
    by_label = {m.label: m for m in macro}
    k = next((by_label[l] for l in by_label if l.replace(" ", "").upper() == "KOSPI"), None)
    k2 = next((by_label[l] for l in by_label if "KOSPI200" in l.replace(" ", "").upper()), None)
    if k and k2 and k.change_pct_1d is not None and k2.change_pct_1d is not None:
        div = abs(k.change_pct_1d - k2.change_pct_1d)
        if div > DIVERGENCE_LIMIT_PP:
            issues.append(
                f"지수 괴리: KOSPI {k.change_pct_1d:+.2f}% vs KOSPI200 {k2.change_pct_1d:+.2f}% "
                f"(괴리 {div:.1f}pp > {DIVERGENCE_LIMIT_PP}pp, 물리 불가 — 데이터 오류)"
            )

    # 5) 오늘 스냅샷 기록(항상)
    date = getattr(macro[0], "_date", None) if macro else None
    try:
        hist.append({"date": date, "snapshot": today, "issues": issues})
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(hist[-90:], ensure_ascii=False, indent=1))
    except Exception:
        pass

    return issues

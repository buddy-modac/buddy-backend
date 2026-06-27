"""
Option A measurement — BEHAVIORAL Block B for ALL 16 types vs the descriptive
baseline (phase2_eval_20260626.md: exact 12%, family 25%, axis E/I 90% T/F 63%
S/N 52% J/P 50%). Same setup: subscription backend, real-use probes, K=3.

Reports per-axis accuracy + exact + NERIS-family + P-registration, plus a
capability spot-check (behavioral vs 기본 모드) on one type per family.
Cache-backed (resumable). Append summary to RESULTS_LOG.

    python benchmarks/run_behavioral_all16.py
"""
import os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from personaforge import build_assistant_system_prompt, ModelClient, Cache, ClaudeCLIBackend, ALL_TYPES
from personaforge.identify import _MBTI_JUDGE_SYSTEM
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "curated_v2_all16_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
K = 5
PROBES = ["내일 비 온대, 우산 챙길까?", "와이파이가 자꾸 끊겨, 어떻게 고쳐?",
          "주말에 갈 만한 당일치기 여행지 추천해줘", "점심 뭐 먹을지 못 정하겠어"]
FAMILY = {**{t: "NT" for t in ["INTJ","INTP","ENTJ","ENTP"]},
          **{t: "NF" for t in ["INFJ","INFP","ENFJ","ENFP"]},
          **{t: "SJ" for t in ["ISTJ","ISFJ","ESTJ","ESFJ"]},
          **{t: "SP" for t in ["ISTP","ISFP","ESTP","ESFP"]}}
CAP_Q = "카페인 하루 권장 섭취량이랑 과다 섭취 시 증상, 줄이는 법 알려줘."
BASELINE = {"exact": 12, "family": 25, "EI": 90, "SN": 52, "TF": 63, "JP": 50, "Preg": "1/9*"}


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def judge(client, listing, k):
    try:
        raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], 150 + k)
        return str(extract_json(raw).get("type", "")).strip().upper()[:4]
    except Exception:
        return "?"


def cap(client, t, behavioral):
    sysp = (build_assistant_system_prompt(t, "Korean", include_style=True, behavioral=True)
            if behavioral else build_assistant_system_prompt(t, "Korean", include_style=False))
    ans = client.complete(sysp, [Message("user", CAP_Q)], 400)
    try:
        return int(extract_json(client.complete(
            "Rate ACCURACY and COMPLETENESS 1-5 (5=fully). JSON {\"score\":n}.",
            [Message("user", f"Q:{CAP_Q}\nA:{ans}")], 60)).get("score", 0))
    except Exception:
        return 0


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w(f"# Phase B-v2 — 큐레이션 누수방지 16유형 (실사용 probe, K={K})\n")
    w("| 유형 | 패밀리 | 정확 | 패밀리 | P등록 | 분포 |\n|---|---|---|---|---|---|")
    axis_ok = {"EI": 0, "SN": 0, "TF": 0, "JP": 0}
    exact_t = fam_t = preg_t = 0
    N = len(ALL_TYPES) * K
    for t in ALL_TYPES:
        sysp = build_assistant_system_prompt(t, "Korean", include_style=True, behavioral=True)
        ans = [client.complete(sysp, [Message("user", q)], 250) for q in PROBES]
        listing = "\n\n".join(f"Q:{q}\nA:{a}" for q, a in zip(PROBES, ans))
        g = [judge(client, listing, k) for k in range(K)]
        ex = sum(1 for x in g if x == t)
        fm = sum(1 for x in g if FAMILY.get(x) == FAMILY[t])
        pr = sum(1 for x in g if len(x) == 4 and x[3] == "P")
        exact_t += ex; fam_t += fm; preg_t += pr
        for x in g:
            if len(x) == 4:
                if x[0] == t[0]: axis_ok["EI"] += 1
                if x[1] == t[1]: axis_ok["SN"] += 1
                if x[2] == t[2]: axis_ok["TF"] += 1
                if x[3] == t[3]: axis_ok["JP"] += 1
        w(f"| {t} | {FAMILY[t]} | {ex}/{K} | {fm}/{K} | {pr}/{K} | "
          f"{', '.join(f'{x}×{n}' for x,n in Counter(g).most_common())} |")
        print(f"{t}: 정확{ex} 패밀리{fm} P{pr}", flush=True)

    w(f"\n## 축별 정확도 — 행동형 vs 묘사형 baseline (/{N})\n")
    w("| 지표 | 행동형 | 묘사형(baseline) | Δ |\n|---|---|---|---|")
    w(f"| 정확 16지 | {100*exact_t//N}% | {BASELINE['exact']}% | {100*exact_t//N-BASELINE['exact']:+d} |")
    w(f"| 패밀리 | {100*fam_t//N}% | {BASELINE['family']}% | {100*fam_t//N-BASELINE['family']:+d} |")
    for ax in ["EI","SN","TF","JP"]:
        v = 100*axis_ok[ax]//N
        w(f"| {ax} | {v}% | {BASELINE[ax]}% | {v-BASELINE[ax]:+d} |")
    w(f"| P등록 | {preg_t}/{N} | {BASELINE['Preg']} | (전멸→?) |")

    w(f"\n## 능력 — 행동형 vs 기본 모드 (패밀리별 1유형)\n")
    w("| 유형 | 행동형 | 기본 모드 |\n|---|---|---|")
    capfail = False
    for t in ["ISTJ", "ESTP", "INTP", "ENFP"]:
        b, p = cap(client, t, True), cap(client, t, False)
        if b < p: capfail = True
        w(f"| {t} | {b}/5 | {p}/5 |")
        print(f"[cap] {t}: 행동{b} 기본{p}", flush=True)
    w(f"\n- 능력 바닥(행동 ≥ 기본): **{'위반' if capfail else '통과'}**")
    w("\n<!-- DONE -->")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(HERE, "RESULTS_LOG.md"), "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"Option A 행동형 16유형\"\n- 정확 {100*exact_t//N}%(vs12) "
                f"패밀리 {100*fam_t//N}%(vs25) P등록 {preg_t}/{N} · 상세 curated_v2_all16_20260626.md\n")
    print(f"DONE: 정확 {100*exact_t//N}%, P등록 {preg_t}/{N}", flush=True)


if __name__ == "__main__":
    main()

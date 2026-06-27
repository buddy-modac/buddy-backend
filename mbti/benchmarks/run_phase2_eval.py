"""
Phase 2 canonical eval — current state, ALL 16 types, the PROPER way:
real-use probes + assistant mode (amp on, as shipped) + judge.

Reports per type: exact-16 hit, and FAMILY match (NERIS group: Analyst NT /
Diplomat NF / Sentinel SJ / Explorer SP) — the product-relevant metric ("did the
chosen vibe-family come through"). K=3, cache-backed, incremental.

    python benchmarks/run_phase2_eval.py
"""
import os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import build_assistant_system_prompt, ModelClient, Cache, ClaudeCLIBackend, ALL_TYPES
from personaforge.identify import _MBTI_JUDGE_SYSTEM
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "phase2_eval_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
K = 3
PROBES = ["내일 비 온대, 우산 챙길까?", "와이파이가 자꾸 끊겨, 어떻게 고쳐?",
          "주말에 갈 만한 당일치기 여행지 추천해줘", "점심 뭐 먹을지 못 정하겠어"]
FAMILY = {**{t: "분석가NT" for t in ["INTJ", "INTP", "ENTJ", "ENTP"]},
          **{t: "외교관NF" for t in ["INFJ", "INFP", "ENFJ", "ENFP"]},
          **{t: "관리자SJ" for t in ["ISTJ", "ISFJ", "ESTJ", "ESFJ"]},
          **{t: "탐험가SP" for t in ["ISTP", "ISFP", "ESTP", "ESFP"]}}


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w(f"# Phase 2 현재 상태 — 실사용 probe + 패밀리 매칭 (K={K}, amp 기본 on)\n")
    w("실제 질문(날씨·와이파이·여행·점심)에 어시스턴트로 답 → 라벨 숨기고 심판이 MBTI 추정.\n")
    w("| 유형 | 패밀리 | 정확(/3) | 패밀리매칭(/3) | 추측 분포 |\n|---|---|---|---|---|")
    exact_t = fam_t = 0
    for t in ALL_TYPES:
        sysp = build_assistant_system_prompt(t, "Korean", include_style=True, amplify=True)
        ans = [client.complete(sysp, [Message("user", q)], 250) for q in PROBES]
        listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(PROBES, ans))
        g = []
        for k in range(K):
            try:
                raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], 150 + k)
                g.append(str(extract_json(raw).get("type", "")).strip().upper()[:4])
            except Exception:
                g.append("?")
        ex = sum(1 for x in g if x == t)
        fm = sum(1 for x in g if FAMILY.get(x) == FAMILY[t])
        exact_t += ex
        fam_t += fm
        w(f"| {t} | {FAMILY[t]} | {ex}/{K} | {fm}/{K} | "
          f"{', '.join(f'{x}×{n}' for x,n in Counter(g).most_common())} |")
        print(f"{t} ({FAMILY[t]}): 정확 {ex}/{K}, 패밀리 {fm}/{K}", flush=True)
    n = len(ALL_TYPES) * K
    w(f"\n## 요약\n- 정확 16지: **{exact_t}/{n} = {exact_t/n:.0%}**\n"
      f"- **패밀리 매칭: {fam_t}/{n} = {fam_t/n:.0%}** (제품 관점 — 고른 vibe-패밀리가 전달됐나)\n")
    w("<!-- DONE -->")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(HERE, "RESULTS_LOG.md"), "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"Phase 2 현재상태 (실사용+패밀리, K={K})\"\n"
                f"- 정확16지 {exact_t}/{n}={exact_t/n:.0%} · 패밀리매칭 {fam_t}/{n}={fam_t/n:.0%}"
                f" — 상세 phase2_eval_20260626.md\n")
    print(f"DONE: 정확 {exact_t/n:.0%}, 패밀리 {fam_t/n:.0%}", flush=True)


if __name__ == "__main__":
    main()

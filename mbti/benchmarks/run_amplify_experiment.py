"""
P2.3 experiment — does concrete/sensory AMPLIFY make the Sensing(S) vibe survive,
WITHOUT hurting capability?

Part A (style): the 8 S types with amplify=True, judge guesses MBTI (K=3). Measure
  - S-recognition: how many guesses are *any* Sensing type (vs current 0/24)
  - exact hits. Compare to current (assistant_style: all S read as N).
Part B (capability): 2 S types answer a factual help question in (amplified style)
  vs (기본 모드/plain); a judge rates accuracy+completeness 1-5. Shows style strength
  doesn't cost capability. (기본 모드 is structurally amplify-immune — unit-tested.)

    python benchmarks/run_amplify_experiment.py
"""
import os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import build_assistant_system_prompt, ModelClient, Cache, ClaudeCLIBackend
from personaforge.identify import _MBTI_JUDGE_SYSTEM, DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "amplify_experiment_20260626.md")
LOG_MD = os.path.join(HERE, "RESULTS_LOG.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
S_TYPES = ["ISTJ", "ISFJ", "ISTP", "ISFP", "ESTP", "ESFP", "ESTJ", "ESFJ"]
K = 3
CAP_Q = "카페인 하루 권장 섭취량이랑 과다 섭취 시 증상, 줄이는 법 알려줘."
CAP_JUDGE = ("Rate the answer's ACCURACY and COMPLETENESS for the question, 1-5 "
             "(5 = fully accurate and complete, nothing important missing). "
             "Reply ONLY JSON: {\"score\": n}.")


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def style_measure(t, client):
    sysp = build_assistant_system_prompt(t, language="English", amplify=True)
    answers = [client.complete(sysp, [Message("user", q)], max_tokens=300) for q in DEFAULT_PROBES]
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(DEFAULT_PROBES, answers))
    guesses = []
    for k in range(K):
        try:
            raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], max_tokens=150 + k)
            guesses.append(str(extract_json(raw).get("type", "")).strip().upper()[:4])
        except Exception:
            guesses.append("?")
    s_hits = sum(1 for g in guesses if len(g) == 4 and g[1] == "S")   # read as Sensing
    exact = sum(1 for g in guesses if g == t)
    return s_hits, exact, ", ".join(f"{g}×{n}" for g, n in Counter(guesses).most_common())


def cap_score(t, client, amplify, language="Korean"):
    sysp = build_assistant_system_prompt(t, language=language, include_style=amplify is not None and amplify,
                                         amplify=bool(amplify)) if amplify is not None else \
           build_assistant_system_prompt(t, language=language, include_style=False)
    ans = client.complete(sysp, [Message("user", CAP_Q)], max_tokens=400)
    try:
        raw = client.complete(CAP_JUDGE, [Message("user", f"Q: {CAP_Q}\nA: {ans}")], max_tokens=60)
        return int(extract_json(raw).get("score", 0))
    except Exception:
        return 0


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w(f"# P2.3 실험 — Sensing 강화(amplify) 효과 (K={K})\n")
    w("## A. 스타일 — S vibe 살아나나 (현재는 8유형 전부 0/24가 S로 읽힘)\n")
    w("| 유형 | S로 읽힘(/3) | 정확(/3) | 분포 |\n|---|---|---|---|")
    tot_s = 0
    for t in S_TYPES:
        s_hits, exact, dist = style_measure(t, client)
        tot_s += s_hits
        w(f"| {t} | {s_hits}/{K} | {exact}/{K} | {dist} |")
        print(f"[A] {t}: S읽힘 {s_hits}/{K}, 정확 {exact}/{K} ({dist})", flush=True)
    w(f"\n- **S로 읽힌 비율: {tot_s}/{len(S_TYPES)*K}** (강화 전: 0/{len(S_TYPES)*K})\n")

    w("## B. 능력 — 강화 스타일 vs 기본 모드 (정확·완전성 1~5)\n")
    w("| 유형 | 강화 스타일 | 기본 모드 |\n|---|---|---|")
    for t in ["ISTJ", "ESFP"]:
        amp = cap_score(t, client, amplify=True)
        plain = cap_score(t, client, amplify=None)   # 기본 모드(style off)
        w(f"| {t} | {amp}/5 | {plain}/5 |")
        print(f"[B] {t}: 강화 {amp}/5, 기본 {plain}/5", flush=True)

    w("\n<!-- DONE -->")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_MD, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"P2.3 Sensing 강화 실험\"\n"
                f"- A(스타일): 8 S유형 amplify, S로 읽힌 비율 {tot_s}/{len(S_TYPES)*K} (강화 전 0)\n"
                f"- B(능력): 강화 스타일 vs 기본 모드 정확·완전성 — 상세 amplify_experiment_20260626.md\n")
    print(f"DONE: S읽힘 {tot_s}/{len(S_TYPES)*K}", flush=True)


if __name__ == "__main__":
    main()

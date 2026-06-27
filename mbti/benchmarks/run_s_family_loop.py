"""
P2.3 loop — target: S-family read >= 70% AND capability == 기본 모드 (no loss), K=5.

Metric = does each Sensing(S) type read as ANY Sensing type (family vibe), not
exact 16-way. Capability = factual-help score, styled(amplify) vs plain(기본 모드);
the styled score must not drop below plain (hard floor). K=5 for the style signal
(K=3 was too noisy). Append-only to RESULTS_LOG.

    python benchmarks/run_s_family_loop.py
"""
import os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import build_assistant_system_prompt, ModelClient, Cache, ClaudeCLIBackend
from personaforge.identify import _MBTI_JUDGE_SYSTEM, DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "s_family_loop_20260626.md")
LOG_MD = os.path.join(HERE, "RESULTS_LOG.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
S_TYPES = ["ISTJ", "ISFJ", "ISTP", "ISFP", "ESTP", "ESFP", "ESTJ", "ESFJ"]
SP_TYPES = ["ISTP", "ISFP", "ESTP", "ESFP"]
K = 5
CAP_Q = "카페인 하루 권장 섭취량이랑 과다 섭취 시 증상, 줄이는 법 알려줘."
CAP_JUDGE = ("Rate the answer's ACCURACY and COMPLETENESS for the question, 1-5 "
             "(5 = fully accurate and complete). Reply ONLY JSON: {\"score\": n}.")


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def s_family(t, client):
    sysp = build_assistant_system_prompt(t, language="English", amplify=True)
    answers = [client.complete(sysp, [Message("user", q)], max_tokens=300) for q in DEFAULT_PROBES]
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(DEFAULT_PROBES, answers))
    g = []
    for k in range(K):
        try:
            raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], max_tokens=150 + k)
            g.append(str(extract_json(raw).get("type", "")).strip().upper()[:4])
        except Exception:
            g.append("?")
    s_read = sum(1 for x in g if len(x) == 4 and x[1] == "S")
    return s_read, ", ".join(f"{x}×{n}" for x, n in Counter(g).most_common())


def cap(t, client, styled):
    sysp = (build_assistant_system_prompt(t, language="Korean", include_style=True, amplify=True)
            if styled else build_assistant_system_prompt(t, language="Korean", include_style=False))
    ans = client.complete(sysp, [Message("user", CAP_Q)], max_tokens=400)
    try:
        raw = client.complete(CAP_JUDGE, [Message("user", f"Q: {CAP_Q}\nA: {ans}")], max_tokens=60)
        return int(extract_json(raw).get("score", 0))
    except Exception:
        return 0


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w(f"# P2.3 루프 — S-family read (K={K}) + 능력 바닥\n")
    w("목표: S-family ≥ 70% AND 능력 = 기본 모드(무손실). Se amp는 능력-안전화 버전.\n")
    w("| 유형 | S-family read | 분포 |\n|---|---|---|")
    tot = 0
    for t in S_TYPES:
        s_read, dist = s_family(t, client)
        tot += s_read
        w(f"| {t} | {s_read}/{K} | {dist} |")
        print(f"[style] {t}: {s_read}/{K} ({dist})", flush=True)
    rate = tot / (len(S_TYPES) * K)
    w(f"\n- **S-family read율: {tot}/{len(S_TYPES)*K} = {rate:.0%}** (목표 70%)\n")

    w("## 능력 — Se amp(능력-안전화) vs 기본 모드 (SP유형)\n")
    w("| 유형 | 강화 스타일 | 기본 모드 |\n|---|---|---|")
    cap_ok = True
    for t in SP_TYPES:
        s, p = cap(t, client, True), cap(t, client, False)
        if s < p:
            cap_ok = False
        w(f"| {t} | {s}/5 | {p}/5 |")
        print(f"[cap] {t}: 강화 {s}/5 vs 기본 {p}/5", flush=True)
    w(f"\n- 능력 바닥(강화 ≥ 기본): **{'통과' if cap_ok else '위반'}**\n")
    w(f"\n## 판정: S-family {rate:.0%} (목표70%) · 능력바닥 {'OK' if cap_ok else 'FAIL'}\n")
    w("<!-- DONE -->")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(LOG_MD, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"P2.3 S-family 루프 (K={K})\"\n"
                f"- S-family read율 {tot}/{len(S_TYPES)*K} = {rate:.0%} (목표 70%) · 능력바닥 "
                f"{'OK' if cap_ok else 'FAIL'} — 상세 s_family_loop_20260626.md\n")
    print(f"DONE: S-family {rate:.0%}, 능력바닥 {'OK' if cap_ok else 'FAIL'}", flush=True)


if __name__ == "__main__":
    main()

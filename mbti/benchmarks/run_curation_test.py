"""
P2.3 curation test — can a HAND-WRITTEN vivid style (Phase-1 lever) break the wall
for SP types, WITHOUT cutting capability?

Tests ISTP & ESTP with curated Block B (vivid hands-on / action-first voice, but
NO "skip analysis" — keeps completeness). Measures S-family read (K=5) + capability
(styled vs 기본 모드, K=3). Compare to the generic amp result (both ~0/5 S; cap 4/5).

    python benchmarks/run_curation_test.py
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import (ModelClient, Cache, ClaudeCLIBackend, BASE_ASSISTANT,
                          PRIORITIES, build_assistant_system_prompt)
from personaforge.identify import _MBTI_JUDGE_SYSTEM, DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "curation_test_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
K, KCAP = 5, 3
CAP_Q = "카페인 하루 권장 섭취량이랑 과다 섭취 시 증상, 줄이는 법 알려줘."
CAP_JUDGE = ("Rate the answer's ACCURACY and COMPLETENESS, 1-5 (5=fully accurate "
             "and complete). Reply ONLY JSON: {\"score\": n}.")

# Hand-written vivid styles (capability-safe: vivid+concrete, NOT "skip analysis").
CURATED = {
    "ISTP": ("Your communication style is that of a hands-on troubleshooter. Ground "
             "every answer in the physical reality of the thing itself — what it "
             "actually looks like, what's really going on, what to physically check "
             "or try FIRST. Walk through it like you're working on it with your hands "
             "right there, naming concrete real specifics. Matter-of-fact, unfussy. "
             "(Stay fully accurate and COMPLETE — deliver the whole substance, just "
             "hands-on and concrete, not abstract or theoretical.)"),
    "ESTP": ("Your communication style is fast, punchy, and action-first. Cut straight "
             "to what to DO right now in the real situation in front of the user — "
             "concrete, physical, immediate, vivid to the moment. Energetic and direct, "
             "like someone who'd rather just show you by doing it. (Stay fully accurate "
             "and COMPLETE — give the whole answer, just lead with the concrete action.)"),
}


def prompt(t, style_block, language="English"):
    lang = f" Always answer in {language}." if language else ""
    return (f"[ASSISTANT]\n{BASE_ASSISTANT}{lang}\n\n"
            f"[COMMUNICATION STYLE]\n{style_block} This sets tone/structure/emphasis "
            f"only — it does not change what you can do.\n\n"
            f"[PRIORITIES & GUARDRAILS]\n{PRIORITIES}")


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def s_family(t, client):
    sysp = prompt(t, CURATED[t], "English")
    ans = [client.complete(sysp, [Message("user", q)], max_tokens=300) for q in DEFAULT_PROBES]
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(DEFAULT_PROBES, ans))
    g = []
    for k in range(K):
        try:
            raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], max_tokens=150 + k)
            g.append(str(extract_json(raw).get("type", "")).strip().upper()[:4])
        except Exception:
            g.append("?")
    return sum(1 for x in g if len(x) == 4 and x[1] == "S"), \
           ", ".join(f"{x}×{n}" for x, n in Counter(g).most_common())


def cap(t, client, curated):
    sysp = prompt(t, CURATED[t], "Korean") if curated else \
           build_assistant_system_prompt(t, language="Korean", include_style=False)
    scores = []
    for j in range(KCAP):
        ans = client.complete(sysp, [Message("user", CAP_Q)], max_tokens=400 + j)  # vary -> independent
        try:
            raw = client.complete(CAP_JUDGE, [Message("user", f"Q: {CAP_Q}\nA: {ans}")], max_tokens=60 + j)
            scores.append(int(extract_json(raw).get("score", 0)))
        except Exception:
            scores.append(0)
    return sum(scores) / len(scores)


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w(f"# P2.3 큐레이션 시범 — ISTP·ESTP (K={K} 스타일 / K={KCAP} 능력)\n")
    w("손작성 생생 스타일(능력-안전). amp 결과 대비: ISTP·ESTP는 amp서 S 0/5, 능력 4/5였음.\n")
    w("| 유형 | S-family read | 분포 | 능력(큐레이션) | 능력(기본모드) |\n|---|---|---|---|---|")
    for t in ["ISTP", "ESTP"]:
        s_read, dist = s_family(t, client)
        c_cur, c_plain = cap(t, client, True), cap(t, client, False)
        w(f"| {t} | {s_read}/{K} | {dist} | {c_cur:.1f}/5 | {c_plain:.1f}/5 |")
        print(f"{t}: S {s_read}/{K} ({dist}) | 능력 큐레{c_cur:.1f} vs 기본{c_plain:.1f}", flush=True)
    w("\n<!-- DONE -->")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

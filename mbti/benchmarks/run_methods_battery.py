"""
P2.3 methods battery — test several diverse approaches, produce a comparison table.

M1 vibe-dimension: does the STYLED answer score higher than 기본 모드 on the dimension
   that matters (S->concreteness, F->warmth, NT->analytical)? (Is the vibe landing
   even when 16-way ID fails?) — the most decisive reframe.
M2 concrete probes: S-family recognizability on REAL product questions (weather/how-to)
   instead of abstract probes.
M3 few-shot: does an in-context style example beat instruction-only for hard SP types?

Incremental + cache-backed (resumable). Append summary to RESULTS_LOG.
    python benchmarks/run_methods_battery.py
"""
import os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import (ModelClient, Cache, ClaudeCLIBackend, BASE_ASSISTANT,
                          PRIORITIES, build_assistant_system_prompt)
from personaforge.identify import _MBTI_JUDGE_SYSTEM, DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "methods_battery_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def gen(client, sysp, q, mt=350):
    return client.complete(sysp, [Message("user", q)], mt)


def rate(client, q, ans, dim_desc, mt=60):
    j = (f"Rate this answer on: {dim_desc}. 1-5. Reply ONLY JSON {{\"score\": n}}.")
    try:
        raw = client.complete(j, [Message("user", f"Q: {q}\nA: {ans}")], mt)
        return int(extract_json(raw).get("score", 0))
    except Exception:
        return 0


def judge_mbti(client, listing, mt):
    try:
        raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], mt)
        return str(extract_json(raw).get("type", "")).strip().upper()[:4]
    except Exception:
        return "?"


# ---- M1: vibe dimension (styled vs plain on the target dimension) ----
DIMS = {
    "concrete": "how CONCRETE/specific/physically-grounded it is (1=abstract, 5=vivid concrete)",
    "warm": "how WARM and emotionally caring it is (1=cold/detached, 5=very warm)",
    "analytical": "how ANALYTICAL/logically-structured it is (1=not, 5=highly)",
}
M1_SET = [("ISTP", "concrete"), ("ESFP", "concrete"), ("ISTJ", "concrete"),
          ("ESFJ", "warm"), ("INFP", "warm"), ("INTJ", "analytical")]
M1_Q = "스트레스를 자주 받는데 어떻게 관리하면 좋을까?"


def m1(client):
    w("## M1. vibe 차원 — 스타일 vs 기본 모드 (해당 차원 점수, K=2 평균)\n")
    w("| 유형 | 차원 | 스타일 | 기본 | Δ |\n|---|---|---|---|---|")
    wins = 0
    for t, dim in M1_SET:
        amp = t[1] == "S"
        styled = build_assistant_system_prompt(t, "Korean", include_style=True, amplify=amp)
        plain = build_assistant_system_prompt(t, "Korean", include_style=False)
        s = sum(rate(client, M1_Q, gen(client, styled, M1_Q, 350 + k), DIMS[dim]) for k in range(2)) / 2
        p = sum(rate(client, M1_Q, gen(client, plain, M1_Q, 350 + k), DIMS[dim]) for k in range(2)) / 2
        if s > p:
            wins += 1
        w(f"| {t} | {dim} | {s:.1f} | {p:.1f} | {s-p:+.1f} |")
        print(f"[M1] {t}/{dim}: styled {s:.1f} vs plain {p:.1f} ({s-p:+.1f})", flush=True)
    w(f"\n- **스타일이 해당 차원에서 기본보다 높은 유형: {wins}/{len(M1_SET)}**\n")


# ---- M2: concrete real-use probes ----
M2_PROBES = ["내일 비 온대, 우산 챙길까?", "와이파이가 자꾸 끊겨, 어떻게 고쳐?",
             "주말에 갈 만한 당일치기 여행지 추천해줘", "점심 뭐 먹을지 못 정하겠어"]
M2_TYPES = ["ISTP", "ISFP", "ESTP", "ESFP", "INTJ"]


def m2(client):
    w("## M2. 실사용 probe — S-family 인식도 (추상 probe서 S=0였음, K=3)\n")
    w("| 유형 | S-family | 분포 |\n|---|---|---|")
    for t in M2_TYPES:
        sysp = build_assistant_system_prompt(t, "Korean", include_style=True, amplify=(t[1] == "S"))
        ans = [gen(client, sysp, q, 250) for q in M2_PROBES]
        listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(M2_PROBES, ans))
        g = [judge_mbti(client, listing, 150 + k) for k in range(3)]
        s_read = sum(1 for x in g if len(x) == 4 and x[1] == "S")
        w(f"| {t} | {s_read}/3 | {', '.join(f'{x}×{n}' for x,n in Counter(g).most_common())} |")
        print(f"[M2] {t}: S {s_read}/3", flush=True)
    w("")


# ---- M3: few-shot style example ----
FEWSHOT = {
    "ISTP": "Q: 자전거 체인이 자꾸 빠져.\nA: 일단 뒤 변속기 쪽 봐. 체인 텐션이 풀렸을 거야 — "
            "손으로 체인 당겨보고 헐거우면 텐셔너 볼트 반 바퀴 조여. 그래도 빠지면 체인 링크가 "
            "휜 거니 그 마디만 펜치로 잡고 살짝 펴.",
}
M3_TYPES = ["ISTP", "ESTP"]


def m3(client):
    w("## M3. few-shot — 스타일 예시 1개 추가 (S-family K=3)\n")
    w("| 유형 | few-shot S-family | 분포 |\n|---|---|---|")
    for t in M3_TYPES:
        base = build_assistant_system_prompt(t, "English", include_style=True, amplify=(t[1] == "S"))
        ex = FEWSHOT.get(t, FEWSHOT["ISTP"])
        sysp = base + f"\n\n[STYLE EXAMPLE]\nMimic this voice:\n{ex}"
        ans = [gen(client, sysp, q, 300) for q in DEFAULT_PROBES]
        listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(DEFAULT_PROBES, ans))
        g = [judge_mbti(client, listing, 150 + k) for k in range(3)]
        s_read = sum(1 for x in g if len(x) == 4 and x[1] == "S")
        w(f"| {t} | {s_read}/3 | {', '.join(f'{x}×{n}' for x,n in Counter(g).most_common())} |")
        print(f"[M3] {t}: few-shot S {s_read}/3", flush=True)
    w("")


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w("# P2.3 방법 배터리 — 다양한 접근 비교\n")
    m1(client)
    m2(client)
    m3(client)
    w("<!-- DONE -->")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(HERE, "RESULTS_LOG.md"), "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"P2.3 방법 배터리\"\n- M1 vibe차원 / M2 실사용probe / "
                f"M3 few-shot 비교 — 상세 methods_battery_20260626.md\n")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

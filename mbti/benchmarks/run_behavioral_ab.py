"""
Decisive A/B: does BEHAVIORAL style encoding beat the current DESCRIPTIVE one on the
FAILED axes (J/P all-collapsed-to-J, S washed out)? And does it keep capability?

Current build_style_guide = descriptive ("precise, logical, measured tone..."). New
finding: behavioral encoding reads ~2x stronger. Test 3 P-types (ESTP/ENFP/ISTP)
descriptive vs behavioral on real-use probes: does P register at all + S-family + cap.

    python benchmarks/run_behavioral_ab.py
"""
import os, sys
from collections import Counter
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from personaforge import (BASE_ASSISTANT, PRIORITIES, build_assistant_system_prompt,
                          ModelClient, Cache, ClaudeCLIBackend)
from personaforge.identify import _MBTI_JUDGE_SYSTEM
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "behavioral_ab_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
K = 3
PROBES = ["내일 비 온대, 우산 챙길까?", "와이파이가 자꾸 끊겨, 어떻게 고쳐?",
          "주말에 갈 만한 당일치기 여행지 추천해줘", "점심 뭐 먹을지 못 정하겠어"]
CAP_Q = "카페인 하루 권장 섭취량이랑 과다 섭취 시 증상, 줄이는 법 알려줘."

# Behavioral Block B — concrete behaviors, foregrounding the type's weak axes (esp. P + S).
BEHAVIORAL = {
 "ESTP": ("Jump straight to what to DO right now, in concrete physical specifics (what to "
          "grab, press, try first). Be blunt, fast, punchy. React to the live moment and "
          "adjust on the fly — DON'T lay out a tidy step-by-step plan or over-organize; "
          "throw out a quick option, then 'or just try this'. Keep it short and energetic."),
 "ENFP": ("Riff with warmth and energy: toss out several possibilities and tangents, follow "
          "whatever's exciting, connect ideas loosely with 'ooh or—'. Be personal and "
          "encouraging. DON'T box it into one rigid organized plan — keep options open, "
          "think out loud, leave room to wander."),
 "ISTP": ("Hands-on troubleshooter: concrete physical specifics, what to actually check or "
          "try, spare and no fluff. Tinker and adjust as you go rather than laying out a "
          "fixed structured plan — 'try X; if not, poke at Y'. Let brevity stand."),
}
KEEP = "(Stay fully accurate and COMPLETE — cover everything useful; this is delivery only.)"


def beh_prompt(t):
    style = (f"Your communication STYLE for an {t}-flavoured assistant (HOW you speak only): "
             f"{BEHAVIORAL[t]} {KEEP}")
    return (f"[ASSISTANT]\n{BASE_ASSISTANT} Always answer in Korean.\n\n"
            f"[COMMUNICATION STYLE]\n{style}\n\n[PRIORITIES & GUARDRAILS]\n{PRIORITIES}")


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def judge(client, listing, k):
    try:
        raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], 150 + k)
        return str(extract_json(raw).get("type", "")).strip().upper()[:4]
    except Exception:
        return "?"


def measure(client, t, sysp):
    ans = [client.complete(sysp, [Message("user", q)], 250) for q in PROBES]
    listing = "\n\n".join(f"Q:{q}\nA:{a}" for q, a in zip(PROBES, ans))
    g = [judge(client, listing, k) for k in range(K)]
    p_reg = sum(1 for x in g if len(x) == 4 and x[3] == "P")
    s_fam = sum(1 for x in g if len(x) == 4 and x[1] == t[1])
    exact = sum(1 for x in g if x == t)
    return p_reg, s_fam, exact, ", ".join(f"{x}×{n}" for x, n in Counter(g).most_common())


def cap(client, sysp):
    ans = client.complete(sysp, [Message("user", CAP_Q)], 400)
    j = ("Rate ACCURACY and COMPLETENESS 1-5 (5=fully accurate/complete). JSON {\"score\":n}.")
    try:
        return int(extract_json(client.complete(j, [Message("user", f"Q:{CAP_Q}\nA:{ans}")], 60)).get("score", 0))
    except Exception:
        return 0


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w("# 묘사형 vs 행동형 A/B — P-types (실사용 probe, K=3)\n")
    w("질문: 행동형이 전멸한 P축을 등록시키나 + S 살리나 + 능력 유지하나?\n")
    w("| 유형 | 인코딩 | P등록 | S-family | 정확 | 능력 | 분포 |\n|---|---|---|---|---|---|---|")
    for t in ["ESTP", "ENFP", "ISTP"]:
        d_sys = build_assistant_system_prompt(t, "Korean", include_style=True, amplify=True)  # 묘사형(현재)
        b_sys = beh_prompt(t)                                                                  # 행동형
        dp, ds, de, dd = measure(client, t, d_sys)
        bp, bs, be, bd = measure(client, t, b_sys)
        dc, bc = cap(client, d_sys), cap(client, b_sys)
        w(f"| {t} | 묘사형 | {dp}/3 | {ds}/3 | {de}/3 | {dc}/5 | {dd} |")
        w(f"| {t} | **행동형** | **{bp}/3** | **{bs}/3** | {be}/3 | {bc}/5 | {bd} |")
        print(f"{t}: 묘사 P{dp} S{ds} cap{dc} | 행동 P{bp} S{bs} cap{bc}", flush=True)
    w("\n<!-- DONE -->")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

"""
Fairer test of "더 많이 갔다를 참고하면 낫지 않나?" — encode magnitude as BEHAVIOR
(not just an adverb), which is the strongest reasonable encoding.

INTP held constant (Ti-Ne logic); vary INTROVERSION intensity behaviorally:
 strong = short/guarded/deflects smalltalk ; mild = personable, chats a little.
Judge rates how strongly introverted (K=5). Strong >> mild = magnitude IS usable
when encoded as behavior (user's intuition right). Flat = even behavior washes out
under assistant gravity.

    python benchmarks/run_vector_intensity2.py
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from personaforge import BASE_ASSISTANT, PRIORITIES, ModelClient, Cache, ClaudeCLIBackend
from personaforge.identify import DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "vector_intensity2_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
K = 5
INTP_CORE = ("you communicate in precise, logical terms, exposing your reasoning and "
             "staying concise, and offer possibilities and unexpected connections")
LEVELS = {
 "강(행동)": ("you are MARKEDLY introverted and reserved: keep replies short and to the "
            "point, do NOT volunteer personal stories or feelings, steer small talk back "
            "to the actual question, let brevity stand."),
 "약(행동)": ("you are only MILDLY introverted: generally measured but personable and "
            "willing to chat a little, share a small aside, and warm up socially when natural."),
}


def prompt(level_text):
    style = (f"Your communication STYLE follows the INTP pattern (HOW you speak only): "
             f"{INTP_CORE}. Crucially, {level_text}")
    return (f"[ASSISTANT]\n{BASE_ASSISTANT} Always answer in Korean.\n\n"
            f"[COMMUNICATION STYLE]\n{style}\n\n[PRIORITIES & GUARDRAILS]\n{PRIORITIES}")


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rate(client, listing):
    j = ("Read this person's answers. Rate 1-5 how strongly INTROVERTED/reserved (vs "
         "outgoing/sociable) they come across. Reply ONLY JSON {\"score\": n}.")
    try:
        return int(extract_json(client.complete(j, [Message("user", listing)], 60)).get("score", 0))
    except Exception:
        return 0


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w("# 벡터 세기 재실험 — 행동(behavior) 인코딩 (INTP, 내향 강 vs 약, K=5)\n")
    w("부사 말고 '행동'으로 강/약 인코딩. 강>>약이면 세기는 (행동으로 쓰면) 쓸모 있음.\n")
    w("| 인코딩 | 내향 강도 | 개별 |\n|---|---|---|")
    probes = DEFAULT_PROBES[:3]
    res = {}
    for label, txt in LEVELS.items():
        sysp = prompt(txt)
        ans = [client.complete(sysp, [Message("user", q)], 250) for q in probes]
        listing = "\n\n".join(f"Q:{q}\nA:{a}" for q, a in zip(probes, ans))
        scores = [rate(client, listing) for _ in range(K)]
        avg = sum(scores) / K
        res[label] = avg
        w(f"| {label} | {avg:.1f}/5 | {scores} |")
        print(f"{label}: {avg:.1f} {scores}", flush=True)
    delta = res["강(행동)"] - res["약(행동)"]
    w(f"\n## 판정\n- 강−약 = **{delta:+.1f}**  → "
      f"{'세기 잡힘(행동으로 쓰면 쓸모 있음) — 유저 직관 맞음' if delta >= 1.0 else ('약하게 잡힘' if delta >= 0.4 else '여전히 안 잡힘(어시스턴트 중력)')}")
    w("\n<!-- DONE -->")
    print(f"DONE delta={delta:+.1f}", flush=True)


if __name__ == "__main__":
    main()

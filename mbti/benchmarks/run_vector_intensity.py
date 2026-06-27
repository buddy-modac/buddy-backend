"""
Does the VECTOR MAGNITUDE carry usable signal? (i.e. is it worth feeding the
numbers into the prose, not just the letters?)

Canonical type vectors are uniform ±0.8, so magnitude only matters if it VARIES.
Test: build magnitude-AWARE prose for INTP at 3 intensities (strong .95 / mid .6 /
mild .3) and check whether a judge detects the intensity difference on the relevant
axes (how strongly Introverted? how strongly logic-driven?). Monotonic strong>mid>
mild = magnitude is usable. Flat = numbers don't help even when used & varied.

    python benchmarks/run_vector_intensity.py
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import BASE_ASSISTANT, PRIORITIES, ModelClient, Cache, ClaudeCLIBackend
from personaforge.identify import DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
REPORT = os.path.join(HERE, "vector_intensity_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))
K = 3
# FUNC directives reused minimally for INTP (Ti dom, Ne aux)
DOM = "in precise, logical terms, exposing your reasoning and staying concise"
AUX = "offering possibilities, alternatives, and unexpected connections"
POLES = {  # (axis): (negative-pole word, positive-pole word)  signs per INTP = I,N,T(-),P
    "EI": ("reserved and inward", "outgoing and expressive"),
    "SN": ("concrete and practical", "abstract and conceptual"),
    "TF": ("warm and people-first", "logic-first, feelings secondary"),
    "JP": ("structured and decisive", "flexible and open-ended"),
}
INTP_SIGN = {"EI": -1, "SN": +1, "TF": -1, "JP": +1}   # I, N, T(neg=T), P


def adverb(mag):
    return "very" if mag >= 0.75 else ("moderately" if mag >= 0.45 else "only mildly")


def style_vec(mag):
    """magnitude-aware Block B for INTP at a given uniform magnitude."""
    parts = []
    for ax, sign in INTP_SIGN.items():
        word = POLES[ax][1] if sign > 0 else POLES[ax][0]
        parts.append(f"{adverb(mag)} {word}")
    axis_line = "; ".join(parts)
    return (f"Your communication STYLE follows the INTP pattern (HOW you speak only): "
            f"you primarily communicate {DOM}, and secondarily by {AUX}. "
            f"On each dimension you lean: {axis_line}.")


def prompt(mag):
    return (f"[ASSISTANT]\n{BASE_ASSISTANT} Always answer in Korean.\n\n"
            f"[COMMUNICATION STYLE]\n{style_vec(mag)}\n\n"
            f"[PRIORITIES & GUARDRAILS]\n{PRIORITIES}")


def w(line=""):
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rate(client, listing, dim):
    j = (f"Read this person's answers. Rate 1-5: {dim} "
         f"(1=not at all, 5=extremely). Reply ONLY JSON {{\"score\": n}}.")
    try:
        raw = client.complete(j, [Message("user", listing)], 60)
        return int(extract_json(raw).get("score", 0))
    except Exception:
        return 0


def main():
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())
    open(REPORT, "w").close()
    w("# 벡터 세기(magnitude)가 산문에 쓸모 있나 — INTP 강/중/약\n")
    w("세기-반영 산문. 심판이 '얼마나 강하게 내향적/논리적'인지 1~5로. 단조(강>중>약)면 쓸모 있음.\n")
    w("| 세기 | 내향(I) 강도 | 논리(T) 강도 |\n|---|---|---|")
    probes = DEFAULT_PROBES[:3]
    rows = {}
    for label, mag in [("강 0.95", 0.95), ("중 0.60", 0.60), ("약 0.30", 0.30)]:
        sysp = prompt(mag)
        ans = [client.complete(sysp, [Message("user", q)], 250) for q in probes]
        listing = "\n\n".join(f"Q:{q}\nA:{a}" for q, a in zip(probes, ans))
        i_scores = [rate(client, listing, "how strongly INTROVERTED/reserved (vs outgoing) they are") for _ in range(K)]
        t_scores = [rate(client, listing, "how strongly LOGIC-DRIVEN (vs warm/feelings-first) they are") for _ in range(K)]
        iA, tA = sum(i_scores)/K, sum(t_scores)/K
        rows[label] = (iA, tA)
        w(f"| {label} | {iA:.1f}/5 | {tA:.1f}/5 |")
        print(f"{label}: 내향 {iA:.1f}, 논리 {tA:.1f}", flush=True)
    # verdict: monotonic?
    labels = ["강 0.95", "중 0.60", "약 0.30"]
    i_seq = [rows[l][0] for l in labels]
    t_seq = [rows[l][1] for l in labels]
    mono_i = i_seq[0] >= i_seq[1] >= i_seq[2] and i_seq[0] > i_seq[2]
    mono_t = t_seq[0] >= t_seq[1] >= t_seq[2] and t_seq[0] > t_seq[2]
    w(f"\n## 판정\n- 내향 단조감소(강>약): {'예' if mono_i else '아니오'} ({i_seq[0]:.1f}→{i_seq[2]:.1f}, Δ{i_seq[0]-i_seq[2]:+.1f})")
    w(f"- 논리 단조감소(강>약): {'예' if mono_t else '아니오'} ({t_seq[0]:.1f}→{t_seq[2]:.1f}, Δ{t_seq[0]-t_seq[2]:+.1f})")
    w(f"- **벡터 세기가 쓸모 있나: {'예 — 세기가 답에 반영됨' if (mono_i or mono_t) else '아니오 — 세기 차이 안 잡힘'}**")
    w("\n<!-- DONE -->")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()

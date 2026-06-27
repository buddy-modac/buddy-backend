"""
Phase 2 eval — does the ASSISTANT (not roleplay) still read as its MBTI?

For each of the 16 types: build the assistant system prompt (A+B+C), have it
answer the same neutral probes, then a blind judge guesses the MBTI from those
answers (K independent samples). This measures whether the *communication style*
survives in transparent-assistant mode. Incremental + cache-backed (blind_cache),
so a token cutoff is resumable (re-run replays cached, continues the rest).

    python benchmarks/run_assistant_style.py            # K=3, all 16
    python benchmarks/run_assistant_style.py --K 5 --types INTP ESFJ
"""
import argparse, json, os, sys
from collections import Counter
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import (build_assistant_system_prompt, ModelClient, Cache,
                          ClaudeCLIBackend, ALL_TYPES)
from personaforge.identify import _MBTI_JUDGE_SYSTEM, DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
LOG_MD = os.path.join(HERE, "RESULTS_LOG.md")
LOG_JSONL = os.path.join(HERE, "results.jsonl")
REPORT = os.path.join(HERE, "assistant_style_20260626.md")
CACHE = os.path.abspath(os.path.join(HERE, "..", "personas", "local", "blind_cache.db"))


def measure(t, client, K):
    sysp = build_assistant_system_prompt(t, language="English")
    answers = [client.complete(sysp, [Message("user", q)], max_tokens=300)
               for q in DEFAULT_PROBES]
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(DEFAULT_PROBES, answers))
    guesses = []
    for k in range(K):
        try:
            raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)], max_tokens=150 + k)
            guesses.append(str(extract_json(raw).get("type", "")).strip().upper()[:4])
        except Exception:
            guesses.append("?")
    hits = sum(1 for g in guesses if g == t)
    return hits, ", ".join(f"{g}×{n}" for g, n in Counter(guesses).most_common())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--K", type=int, default=3)
    ap.add_argument("--types", nargs="*", default=list(ALL_TYPES))
    args = ap.parse_args()
    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE), backend=ClaudeCLIBackend())

    rows = []
    open(REPORT, "w").close()
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(f"# Phase 2 — 어시스턴트 모드 스타일 인식도 (K={args.K})\n\n"
                "어시스턴트(투명 AI, 능력 우선)가 중립 질문에 답한 걸 라벨 숨기고 심판이 MBTI 추정.\n"
                "스타일이 어시스턴트 모드에서도 읽히나? | 각 칸 = K회 중 적중 + 분포\n\n"
                "| 유형 | 적중 | 분포 |\n|---|---|---|\n")
    for i, t in enumerate(args.types, 1):
        hits, dist = measure(t, client, args.K)
        rows.append({"type": t, "hits": hits, "K": args.K, "dist": dist})
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(f"| {t} | {hits}/{args.K} | {dist} |\n")
        print(f"[{i}/{len(args.types)}] {t}: {hits}/{args.K} ({dist})", flush=True)

    n = len(rows); total = sum(r["hits"] for r in rows)
    rate = total / (n * args.K) if n else 0
    stable = sum(1 for r in rows if r["hits"] >= max(1, round(args.K * 0.8)))
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(f"\n## 요약\n- 평균 적중률: **{rate:.0%}** ({total}/{n*args.K})\n"
                f"- 안정(≥80%×K): **{stable}/{n}**\n\n<!-- DONE -->\n")
    # also append a one-line entry to the shared benchmark log
    with open(LOG_MD, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"Phase 2 어시스턴트 모드 스타일 인식도\"\n"
                f"condition=**assistant** · K={args.K} · 유형 {n}개\n\n"
                f"- 평균 적중률: **{rate:.0%}** ({total}/{n*args.K}) · 안정 {stable}/{n}\n"
                f"- (어시스턴트 모드에서도 MBTI 스타일이 식별되나 — 상세표 assistant_style_20260626.md)\n")
    with open(LOG_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": stamp, "label": "Phase 2 assistant style",
                            "condition": "assistant", "K": args.K, "mean_rate": round(rate, 4),
                            "stable": stable, "n": n, "rows": rows}, ensure_ascii=False) + "\n")
    print(f"DONE: 평균 {rate:.0%}, 안정 {stable}/{n}", flush=True)


if __name__ == "__main__":
    main()

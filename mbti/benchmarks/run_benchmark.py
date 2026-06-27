"""
Blind-identification benchmark — append-only history log.

Run this after a change to record how identification reliability moved. Results
are K-sampled (single-pass is too noisy to compare), and each run APPENDS a dated
entry to RESULTS_LOG.md + results.jsonl so you can see the trend over time.

    # baseline (default engine), all 16 types, K=5
    python benchmarks/run_benchmark.py --label "baseline 기준선"

    # after a change, with a condition:
    python benchmarks/run_benchmark.py --label "ISFP Se 산문 적용" --condition sign
    python benchmarks/run_benchmark.py --label "..." --types ISTP ISFP --K 10

Conditions:
  baseline  = build_mbti(t)                                   (default engine)
  enriched  = build_mbti(t, items=QUESTIONS, survey_client)
  sign      = build_mbti(t, items, survey_client, dichotomous_prose=True)

Uses the local claude subscription (ClaudeCLIBackend) + blind_cache.db, so
unchanged calls are free cache hits.
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from personaforge import (build_mbti, load_character, ModelClient, Cache,
                          ClaudeCLIBackend, ALL_TYPES)
from personaforge.identify import _collect_answers, _MBTI_JUDGE_SYSTEM, DEFAULT_PROBES
from personaforge.model import Message, extract_json

HERE = os.path.dirname(__file__)
LOG_MD = os.path.join(HERE, "RESULTS_LOG.md")
LOG_JSONL = os.path.join(HERE, "results.jsonl")
LOCAL = os.path.abspath(os.path.join(HERE, "..", "personas", "local"))
CURATED_DIR = os.path.abspath(os.path.join(HERE, "..", "personas", "curated"))
CACHE = os.path.join(LOCAL, "blind_cache.db")

# "curated" condition: types with a hand-written, distinguishing-function-forward
# prose (saved in personas/curated/{TYPE}.json) load from that file; every other
# type falls back to the default engine. Honest "engine + curated fixes" run.
# Rationale + sources for each curated prose: see README "수동(큐레이션) 산문".
CURATED = {"ISFP", "ISTP", "ENTJ"}


def build(t, condition, client):
    if condition == "baseline":
        return build_mbti(t)
    if condition == "curated":
        path = os.path.join(CURATED_DIR, f"{t}.json")
        if t in CURATED and os.path.exists(path):
            return load_character(path)
        return build_mbti(t)            # not curated -> default engine
    from personas.local.QUESTIONS import QUESTIONS
    dich = (condition == "sign")
    return build_mbti(t, items=QUESTIONS, survey_client=client, dichotomous_prose=dich)


def measure(t, condition, client, K):
    prof = build(t, condition, client)
    answers = _collect_answers(prof, client, DEFAULT_PROBES, "English")
    listing = "\n\n".join(f"Q: {q}\nA: {a}" for q, a in zip(DEFAULT_PROBES, answers))
    guesses = []
    for k in range(K):
        try:
            raw = client.complete(_MBTI_JUDGE_SYSTEM, [Message("user", listing)],
                                  max_tokens=150 + k)
            guesses.append(str(extract_json(raw).get("type", "")).strip().upper()[:4])
        except Exception:
            guesses.append("?")
    hits = sum(1 for g in guesses if g == t)
    dist = ", ".join(f"{g}×{n}" for g, n in Counter(guesses).most_common())
    return hits, dist


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="이번 실행에서 무엇이 바뀌었나")
    ap.add_argument("--condition", default="baseline",
                    choices=("baseline", "enriched", "sign", "curated"))
    ap.add_argument("--K", type=int, default=5)
    ap.add_argument("--types", nargs="*", default=list(ALL_TYPES))
    ap.add_argument("--date", default=None, help="YYYY-MM-DD HH:MM (생략 시 현재 시각)")
    args = ap.parse_args()

    client = ModelClient(model="claude-sonnet-4-6", cache=Cache(CACHE),
                         backend=ClaudeCLIBackend())

    rows = []
    for t in args.types:
        hits, dist = measure(t, args.condition, client, args.K)
        rows.append({"type": t, "hits": hits, "K": args.K, "dist": dist})
        print(f"{t}: {hits}/{args.K} ({dist})", flush=True)

    n = len(rows)
    total_hits = sum(r["hits"] for r in rows)
    mean_rate = total_hits / (n * args.K) if n else 0.0
    stable = sum(1 for r in rows if r["hits"] >= max(1, round(args.K * 0.8)))
    stamp = args.date or datetime.now().strftime("%Y-%m-%d %H:%M")

    # human-readable append
    if not os.path.exists(LOG_MD):
        with open(LOG_MD, "w", encoding="utf-8") as f:
            f.write("# PersonaForge 블라인드 식별 벤치마크 로그\n\n"
                    "변경할 때마다 `run_benchmark.py`로 K회 측정한 결과를 아래에 append합니다.\n"
                    "K-sampled라 단일 표본 노이즈에 흔들리지 않고 추세 비교가 가능합니다.\n"
                    "(평균 적중률 = 모든 유형의 hits 합 / (유형수×K), 안정 = hits ≥ 80%×K)\n")
    with open(LOG_MD, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n## {stamp} · \"{args.label}\"\n")
        f.write(f"condition=**{args.condition}** · K={args.K} · 유형 {n}개\n\n")
        f.write(f"- **평균 적중률: {mean_rate:.0%}** ({total_hits}/{n*args.K} draws)\n")
        f.write(f"- 안정 유형(hits≥{max(1,round(args.K*0.8))}/{args.K}): **{stable}/{n}**\n\n")
        f.write("| 유형 | 적중 | 분포 |\n|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['type']} | {r['hits']}/{r['K']} | {r['dist']} |\n")

    # machine-readable append
    with open(LOG_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": stamp, "label": args.label,
                            "condition": args.condition, "K": args.K,
                            "mean_rate": round(mean_rate, 4), "stable": stable,
                            "n": n, "rows": rows}, ensure_ascii=False) + "\n")

    print(f"\n→ 평균 적중률 {mean_rate:.0%} · 안정 {stable}/{n} · 기록: {LOG_MD}")


if __name__ == "__main__":
    main()

"""v2: Anthropic(Haiku) vs OpenAI(gpt-5.4-mini) — 시나리오×mode×detail 별 속도+정확도.

실제 서버 백엔드(server.ai_backend) 그대로 사용 → v2_params(모델·이미지정책·캡) 동일 적용.
정확도: 중립 심판(Sonnet)이 1~5 채점(번역=충실/자연, 설명=정확 전달). 프로바이더 블라인드.
ANTHROPIC_API_KEY + OPENAI_API_KEY 필요.
    set -a; source server/.env.local; set +a
    python benchmarks/run_provider_bench.py
"""
import os, sys, json, time, base64, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from server.ai_backend import APIVisionBackend, OpenAIBackend, v2_params

AK = os.getenv("ANTHROPIC_API_KEY", "").strip()
OK = os.getenv("OPENAI_API_KEY", "").strip()
SONNET = "claude-sonnet-4-6"
PERSONA = "ENFP"
K = int(os.getenv("BENCH_K", "3"))   # 셀당 반복 (시나리오당) — 노이즈 감소
# 시나리오: (이름, density, 줄들). light=짧은 안내문, dense=정보밀집(약관/대시보드, 노트북 풀스크린)
_TERMS = ["SERVICE TERMS & PRIVACY (excerpt)"] + [
    f"{i}. " + t for i, t in enumerate([
    "By using the service you agree to these terms and the privacy policy.",
    "We collect account info, usage logs, device identifiers, and cookies.",
    "Data is retained for up to 24 months unless deletion is requested.",
    "You may export or delete your data from Settings > Account > Data.",
    "Third-party processors: payments, analytics, email delivery, hosting.",
    "We do not sell personal data; we share only as described herein.",
    "Subscriptions renew automatically; cancel anytime before renewal.",
    "Refunds are issued within 14 days for unused subscription periods.",
    "You are responsible for maintaining the confidentiality of your account.",
    "Prohibited: scraping, reverse engineering, abuse, or unlawful use.",
    "We may suspend accounts that violate these terms without notice.",
    "Service is provided 'as is' without warranties of any kind.",
    "Liability is limited to the amount paid in the prior 12 months.",
    "We may update these terms; continued use means acceptance.",
    "Governing law is the jurisdiction stated in your billing country.",
    "Contact support@company.com for questions about these terms.",
    "Last updated: 2026-02-14. Version 3.2. Effective immediately.",
    "Notices will be sent to the email on file; keep it current.",
    "Beta features may change or be removed without prior notice.",
    "Accessibility requests: accessibility@company.com (response 5 days).",
    ], 1)]
_DASH = ["ADMIN DASHBOARD — Overview (last 24h)",
    "Active users: 12,481   New signups: 342   Churn: 1.8%",
    "Requests: 1,204,553   Errors: 0.42%   p95 latency: 318 ms",
    "Revenue today: $8,420   MRR: $214,300   ARPU: $17.2",
    "Top plan: Pro (58%)  ·  Team (27%)  ·  Free (15%)",
    "Region: US 41% · EU 33% · APAC 21% · Other 5%",
    "---- Recent incidents ----",
    "09:12  API 5xx spike on eu-west-1 (resolved, 7 min)",
    "07:48  Payment webhook retry backlog (auto-cleared)",
    "02:30  Scheduled DB maintenance completed",
    "---- Queue ----",
    "Email: 1,203 pending   Export jobs: 12   OCR: 4 running",
    "---- Support ----",
    "Open tickets: 37  ·  SLA breaches: 2  ·  CSAT: 4.6/5",
    "Oldest open: #8841 (refund) 2 days  ·  assignee: Jia",
    "---- Deploys ----",
    "v3.2.1 → prod 06:40 (canary 10%→100%, no rollback)",
    "Feature flags: new_editor ON(25%), v2_api ON(100%)",
    "---- Alerts ----",
    "⚠ disk usage db-2 at 82%   ⚠ cert renews in 9 days",
    "✓ backups OK   ✓ all health checks green",
    ]
SCEN = [
    ("교통 안내문", "light", ["CITY TRANSIT - SERVICE NOTICE", "Line 2 (Blue) skips Central/Park/Riverside (Mar1-Apr30)",
                  "Shuttle every 12 min from Gate C", "Elevators at Central out of service"]),
    ("카페 메뉴", "light", ["CAFE MENU", "Americano $4.5 / Latte $5.0", "Today: Pumpkin Spice $5.5", "10% off before 11AM"]),
    ("서비스 약관", "dense", _TERMS),
    ("관리자 대시보드", "dense", _DASH),
]


def img(lines, density):
    # light=작은 안내문, dense=노트북 풀스크린(1440x900) 정보밀집
    if density == "dense":
        W, H, fs, lh, x, y0 = 1440, 900, 22, 25, 28, 24
    else:
        W, H, fs, lh, x, y0 = 900, 360, 28, 52, 24, 24
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", fs)
    except: f = ImageFont.load_default()
    for i, ln in enumerate(lines): d.text((x, y0 + i*lh), ln, fill="black", font=f)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def judge(mode, ocr, answer):
    if not answer or not answer.strip():
        return 0, "빈 응답"
    if mode == "translate":
        q = (f"영어 원문:\n{ocr}\n\n한국어 번역:\n{answer}\n\n"
             "번역이 원문을 얼마나 정확하고 자연스럽게 옮겼는지 1~5점.")
    else:
        q = (f"원문(OCR):\n{ocr}\n\n설명:\n{answer}\n\n"
             "이 설명이 화면/내용을 얼마나 정확하고 유용하게 전달하는지 1~5점.")
    q += ' JSON만: {"score": n, "why": "짧게"}'
    payload = {"model": SONNET, "max_tokens": 150,
               "system": "너는 엄격한 평가자다. JSON만 출력.",
               "messages": [{"role": "user", "content": q}]}
    r = httpx.post("https://api.anthropic.com/v1/messages",
                   headers={"x-api-key": AK, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json=payload, timeout=60)
    raw = "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")
    s = raw[raw.find("{"):raw.rfind("}") + 1]
    try:
        d = json.loads(s); return float(d.get("score", 0)), str(d.get("why", ""))[:60]
    except Exception:
        return 0, "심판 파싱실패"


def main():
    if not AK or not OK:
        print(f"키 부족 — ANTHROPIC={bool(AK)} OPENAI={bool(OK)}"); return
    backends = {"Anthropic(Haiku)": APIVisionBackend(AK), "OpenAI(gpt-5.4-mini)": OpenAIBackend(OK)}
    imgs = {name: img(lines, dens) for name, dens, lines in SCEN}
    avg = lambda xs: sum(xs)/len(xs) if xs else 0
    print("이미지 크기(base64):")
    for name, dens, lines in SCEN:
        print(f"  {name:12} {dens:5} {len(imgs[name]):>9,}자  · OCR {len(' / '.join(lines))}자")
    # 집계: (density, provider, mode, detail) -> {ms,acc,len}
    agg = {}
    n_cells = len(SCEN)*2*2*2
    print(f"\n측정 중… (시나리오 {len(SCEN)} × mode 2 × detail 2 × provider 2 × K={K} = {n_cells*K} 생성 + {n_cells*K} 심판)\n")
    for name, dens, lines in SCEN:
        ocr = " / ".join(lines)
        for mode in ("translate", "explain"):
            for detail in ("brief", "full"):
                extra = v2_params(mode, detail, len(ocr))
                for pname, be in backends.items():
                    k = (dens, pname, mode, detail)
                    agg.setdefault(k, {"ms": [], "acc": [], "len": []})
                    cms, cacc, clen, errs = [], [], [], 0
                    for _ in range(K):
                        try:
                            t0 = time.perf_counter()
                            ans = be.interpret(PERSONA, mode, ocr, imgs[name], "image/png", "", "", **extra)
                            ms = (time.perf_counter() - t0) * 1000
                            acc, _ = judge(mode, ocr, ans)
                        except Exception:
                            ms, acc, ans, errs = 0, 0, "", errs+1
                        cms.append(ms); cacc.append(acc); clen.append(len(ans or ""))
                    agg[k]["ms"] += cms; agg[k]["acc"] += cacc; agg[k]["len"] += clen
                    flag = f" ⚠{errs}err" if errs else ""
                    print(f"  {name:12}{mode:9} {detail:5} {pname:20} avg {avg(cms):6.0f}ms acc {avg(cacc):.1f} ({avg(clen):.0f}자){flag}")
    for dens in ("light", "dense"):
        print(f"\n=== [{dens.upper()}] 종합 (mode×detail · provider 비교 · 평균) ===")
        print(f"{'mode':10}{'detail':7}{'provider':22}{'속도(ms)':>10}{'정확도/5':>9}{'출력자':>7}")
        print("-"*65)
        for mode in ("translate", "explain"):
            for detail in ("brief", "full"):
                for pname in backends:
                    a = agg.get((dens, pname, mode, detail))
                    if a:
                        print(f"{mode:10}{detail:7}{pname:22}{avg(a['ms']):>9.0f} {avg(a['acc']):>8.1f}{avg(a['len']):>7.0f}")
                print()


if __name__ == "__main__":
    main()

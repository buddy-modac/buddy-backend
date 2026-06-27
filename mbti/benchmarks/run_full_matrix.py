"""종합 매트릭스: 시나리오별 모델 매핑용.
Part A (작업 품질): 크기(light/dense) × mode × detail × 모델 → 속도 + 정확도(중립 심판 Sonnet)
Part B (페르소나 재현도): MBTI 8 × 모델 → 블라인드 MBTI 식별(축별 점수, Phase2 스타일)
모델: Anthropic(Haiku, 동적캡) vs OpenAI(gpt-5.4-mini). K=5(정밀). ANTHROPIC+OPENAI 키 필요.
    set -a; source server/.env.local; set +a
    python benchmarks/run_full_matrix.py
"""
import os, sys, json, time, base64, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt
from server.ai_backend import APIVisionBackend, OpenAIBackend, v2_params

AK = os.getenv("ANTHROPIC_API_KEY", "").strip()
OK = os.getenv("OPENAI_API_KEY", "").strip()
SONNET = "claude-sonnet-4-6"
HAIKU = "claude-haiku-4-5-20251001"
GPT = os.getenv("SERVER_OPENAI_MODEL", "gpt-5.4-mini")
K = int(os.getenv("BENCH_K", "5"))
A_URL = "https://api.anthropic.com/v1/messages"
O_URL = "https://api.openai.com/v1/chat/completions"
AH = {"x-api-key": AK, "anthropic-version": "2023-06-01", "content-type": "application/json"}
OH = {"Authorization": f"Bearer {OK}", "content-type": "application/json"}

PROVIDERS = ["Claude", "GPT"]
PERSONA_TASK = "ENFP"
FID_TYPES = ["INTJ", "INTP", "ENFP", "ENFJ", "ISTP", "ISFP", "ESTJ", "ESFJ"]
PROBES = ["완전히 자유로운 오후엔 뭘 해?", "친구가 큰 결정을 앞두고 조언을 구하면 어떻게 답해?",
          "여행 계획은 어떻게 짜?"]

_TERMS = ["SERVICE TERMS (excerpt)"] + [f"{i}. {t}" for i, t in enumerate([
    "By using the service you agree to these terms and the privacy policy.",
    "We collect account info, usage logs, device identifiers, and cookies.",
    "Data is retained up to 24 months unless deletion is requested.",
    "Subscriptions renew automatically; cancel anytime before renewal.",
    "Refunds are issued within 14 days for unused subscription periods.",
    "Prohibited: scraping, reverse engineering, abuse, or unlawful use.",
    "Service is provided 'as is' without warranties of any kind.",
    "Liability is limited to the amount paid in the prior 12 months.",
    "We may update these terms; continued use means acceptance.",
    "Governing law is the jurisdiction stated in your billing country.",
    "Third-party processors: payments, analytics, email, hosting.",
    "You may export or delete your data from Settings > Account.",
    "We may suspend accounts that violate these terms without notice.",
    "Beta features may change or be removed without prior notice.",
    "Last updated 2026-02-14. Version 3.2. Contact support@company.com.",
    ], 1)]
_DASH = ["ADMIN DASHBOARD — Overview (24h)", "Active users 12,481  Signups 342  Churn 1.8%",
    "Requests 1,204,553  Errors 0.42%  p95 318ms", "Revenue $8,420  MRR $214,300  ARPU $17.2",
    "Plans: Pro 58% Team 27% Free 15%", "Region US41 EU33 APAC21 Other5",
    "Incidents: 09:12 API 5xx eu-west-1 (resolved 7m)", "07:48 webhook retry backlog (cleared)",
    "Queue: email 1203, export 12, ocr 4", "Support: open 37, SLA breach 2, CSAT 4.6/5",
    "Deploy v3.2.1 prod 06:40 canary 10->100%", "Flags new_editor ON(25%) v2_api ON(100%)",
    "Alerts: disk db-2 82%, cert renews 9d", "Backups OK, health checks green"]
SCEN = [
    ("교통안내문", "light", ["CITY TRANSIT NOTICE", "Line 2 (Blue) skips Central/Park/Riverside (Mar1-Apr30)",
                  "Shuttle every 12 min from Gate C", "Elevators at Central out of service"]),
    ("카페메뉴", "light", ["CAFE MENU", "Americano $4.5 / Latte $5.0", "Pumpkin Spice $5.5", "10% off before 11AM"]),
    ("서비스약관", "dense", _TERMS),
    ("대시보드", "dense", _DASH),
]


def make_img(lines, dens):
    W, H, fs, lh = (1440, 900, 22, 25) if dens == "dense" else (900, 360, 28, 52)
    im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", fs)
    except: f = ImageFont.load_default()
    for i, ln in enumerate(lines): d.text((24, 24 + i*lh), ln, fill="black", font=f)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def a_call(system, user, model, max_tokens):
    p = {"model": model, "max_tokens": max_tokens, "system": system,
         "messages": [{"role": "user", "content": user}]}
    r = httpx.post(A_URL, headers=AH, json=p, timeout=90); r.raise_for_status()
    return "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")


def o_call(system, user, model, max_tokens):
    tk = "max_completion_tokens" if (model.startswith("gpt-5") or model.startswith("o")) else "max_tokens"
    p = {"model": model, tk: max_tokens,
         "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    r = httpx.post(O_URL, headers=OH, json=p, timeout=90); r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def judge_task(mode, ocr, ans):
    if not ans or not ans.strip(): return 0
    if mode == "translate":
        q = f"영어 원문:\n{ocr}\n\n한국어 번역:\n{ans}\n\n번역이 원문을 정확·자연스럽게 옮겼는지 1~5."
    else:
        q = f"원문(OCR):\n{ocr}\n\n설명:\n{ans}\n\n설명이 내용을 정확·유용하게 전달하는지 1~5."
    q += ' JSON만: {"score": n}'
    raw = a_call("엄격한 평가자. JSON만.", q, SONNET, 120)
    try: return float(json.loads(raw[raw.find("{"):raw.rfind("}")+1])["score"])
    except Exception: return 0


_MBTI_JUDGE = ('여러 답변은 한 사람이 쓴 것이다. MBTI 유형을 추론하라(E/I, S/N, T/F, J/P). '
               'JSON만: {"type":"XXXX"}')


def judge_mbti(answers, intended):
    listing = "\n\n".join(f"Q{i+1}: {a}" for i, a in enumerate(answers))
    raw = a_call(_MBTI_JUDGE, listing, SONNET, 80)
    try: g = str(json.loads(raw[raw.find("{"):raw.rfind("}")+1]).get("type", "")).strip().upper()[:4]
    except Exception: g = ""
    sc = sum(1 for x, y in zip(intended, g) if x == y)/4.0 if len(g) == 4 else 0
    return (g == intended), sc


def gen_task(provider, persona, mode, ocr, image, extra):
    be = APIVisionBackend(AK) if provider == "Claude" else OpenAIBackend(OK)
    return be.interpret(persona, mode, ocr, image, "image/png", "", "", **extra)


def gen_probe(provider, system, probe):
    if provider == "Claude":
        return a_call(system, probe, HAIKU, 280)
    return o_call(system, probe, GPT, 280)


def avg(xs): return sum(xs)/len(xs) if xs else 0


def main():
    if not AK or not OK:
        print(f"키 부족 ANTHROPIC={bool(AK)} OPENAI={bool(OK)}"); return
    imgs = {n: make_img(l, d) for n, d, l in SCEN}

    # ---------- Part A: 작업 품질 ----------
    print("=== Part A: 작업 속도/정확도 (size×mode×detail×모델, K=%d) ===" % K)
    taskA = {}   # (size, mode, detail, provider) -> {ms, acc}
    for n, dens, lines in SCEN:
        ocr = " / ".join(lines)
        for mode in ("translate", "explain"):
            for detail in ("brief", "full"):
                extra = v2_params(mode, detail, len(ocr))
                for prov in PROVIDERS:
                    k = (dens, mode, detail, prov)
                    taskA.setdefault(k, {"ms": [], "acc": []})
                    for _ in range(K):
                        try:
                            t0 = time.perf_counter()
                            ans = gen_task(prov, PERSONA_TASK, mode, ocr, imgs[n], extra)
                            ms = (time.perf_counter()-t0)*1000
                            acc = judge_task(mode, ocr, ans)
                        except Exception:
                            ms, acc = 0, 0
                        taskA[k]["ms"].append(ms); taskA[k]["acc"].append(acc)
                    a = taskA[k]
                    print(f"  {dens:5} {mode:9} {detail:5} {prov:6} {avg(a['ms'][-K:]):6.0f}ms acc {avg(a['acc'][-K:]):.1f}")

    # ---------- Part B: 페르소나 재현도 ----------
    print("\n=== Part B: MBTI 페르소나 재현도 (블라인드 식별, K=%d) ===" % K)
    fid = {(t, p): {"hit": 0, "score": 0.0, "n": 0} for t in FID_TYPES for p in PROVIDERS}
    for t in FID_TYPES:
        system = build_assistant_system_prompt(t, "Korean", amplify=True)
        for prov in PROVIDERS:
            for _ in range(K):
                try:
                    answers = [gen_probe(prov, system, pr) for pr in PROBES]
                    hit, sc = judge_mbti(answers, t)
                except Exception:
                    hit, sc = False, 0
                f = fid[(t, prov)]; f["hit"] += hit; f["score"] += sc; f["n"] += 1
            f = fid[(t, prov)]
            print(f"  {t} {prov:6} exact {f['hit']}/{f['n']} 축점수 {f['score']/max(1,f['n']):.2f}")

    # ---------- 종합표 ----------
    print("\n\n########## 종합 ##########")
    print("\n[A] 작업 품질 — size×mode×detail (속도ms / 정확도/5), ★=빠르고 정확한 쪽")
    print(f"{'size':6}{'mode':10}{'detail':7}{'Claude(ms/acc)':>18}{'GPT(ms/acc)':>16}{'추천':>8}")
    for dens in ("light", "dense"):
        for mode in ("translate", "explain"):
            for detail in ("brief", "full"):
                c = taskA[(dens, mode, detail, "Claude")]; g = taskA[(dens, mode, detail, "GPT")]
                cm, ca, gm, ga = avg(c["ms"]), avg(c["acc"]), avg(g["ms"]), avg(g["acc"])
                # 추천: 정확도 우선(차>=0.5), 동급이면 빠른 쪽
                if abs(ca-ga) >= 0.5: rec = "Claude" if ca > ga else "GPT"
                else: rec = "Claude" if cm <= gm else "GPT"
                print(f"{dens:6}{mode:10}{detail:7}{cm:8.0f}/{ca:<4.1f}{'':>4}{gm:8.0f}/{ga:<4.1f}{'':>2}{rec:>8}")
    print("\n[B] 페르소나 재현도 — MBTI별 (exact·축점수), 더 잘 담는 쪽")
    print(f"{'MBTI':6}{'Claude(exact/축)':>20}{'GPT(exact/축)':>18}{'우세':>8}")
    cwin = gwin = 0
    for t in FID_TYPES:
        c = fid[(t, 'Claude')]; g = fid[(t, 'GPT')]
        cs, gs = c['score']/max(1, c['n']), g['score']/max(1, g['n'])
        win = "Claude" if cs > gs else ("GPT" if gs > cs else "=")
        cwin += cs > gs; gwin += gs > cs
        print(f"{t:6}{c['hit']:>6}/{c['n']} {cs:>5.2f}{g['hit']:>8}/{g['n']} {gs:>5.2f}{win:>8}")
    print(f"\n페르소나 더 잘 담는 모델: Claude {cwin} vs GPT {gwin} (유형 수 기준)")


if __name__ == "__main__":
    main()

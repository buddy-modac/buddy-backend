"""explain mode · 시나리오별 · 4전략 체감 LLM 시간 비교 (한눈에).

전략(유저가 explain 답을 받기까지 '체감'하는 LLM 시간):
  기존 v1        : Sonnet · 비스트리밍 · 2000tok  → 완성까지 대기 (ms_total)
  v2 비스트리밍  : Haiku  · 비스트리밍 · 1200tok  → 완성까지 대기 (ms_total)
  v2 스트리밍    : Haiku  · 스트리밍           → 첫 토큰(TTFT) = 반응 시작
  v2 prefetch    : Haiku full을 미리 생성       → 체감 = max(0, full_total - dwell)
                   (dwell = 유저가 brief 읽는 시간, 기본 4s 가정)

ANTHROPIC_API_KEY 필요. set -a; source server/.env.local; set +a; python benchmarks/run_strategy_bench.py
"""
import os, sys, json, time, base64, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
SONNET, HAIKU = "claude-sonnet-4-6", "claude-haiku-4-5-20251001"
URL = "https://api.anthropic.com/v1/messages"
H = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
SYS = build_assistant_system_prompt("ENFP", "Korean", amplify=True)
K = 2
DWELL = 4000   # 유저가 brief 읽는 시간(ms) 가정 — prefetch 체감 계산용

SCENARIOS = [
    ("로그인 에러", ["Login Failed", "Error 401: invalid credentials", "[Retry]  [Forgot password?]"]),
    ("교통 안내문", ["CITY TRANSIT - SERVICE NOTICE", "Line 2 (Blue) skips Central/Park/Riverside (Mar1-Apr30)",
                  "Shuttle every 12 min from Gate C", "Elevators at Central out of service"]),
    ("카페 메뉴", ["CAFE MENU", "Americano $4.5 / Latte $5.0", "Today: Pumpkin Spice $5.5", "10% off before 11AM"]),
    ("회원가입 폼", ["Create your account", "Email / Password / Confirm password",
                  "[ ] I agree to the Terms & Privacy", "[ Sign up ]"]),
]


def make_img(lines):
    im = Image.new("RGB", (900, 360), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except: f = ImageFont.load_default()
    for i, ln in enumerate(lines): d.text((24, 24 + i*52), ln, fill="black", font=f)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def msg(ocr, detail):
    tip = "\n\n충분히 자세하게 설명." if detail == "full" else ""
    return f"요청: 아래 이미지와 텍스트의 의미를 설명해 주세요.\n\n[추출된 텍스트]\n{ocr}{tip}"


def call(model, image, ocr, max_tok, detail, stream):
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}},
               {"type": "text", "text": msg(ocr, detail)}]
    p = {"model": model, "max_tokens": max_tok, "system": SYS, "messages": [{"role": "user", "content": content}]}
    t0 = time.perf_counter(); ttft = None
    if not stream:
        r = httpx.post(URL, headers=H, json=p, timeout=120); r.raise_for_status()
        return None, (time.perf_counter()-t0)*1000
    p["stream"] = True
    with httpx.Client(timeout=120) as c, c.stream("POST", URL, headers=H, json=p) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                try: ev = json.loads(line[6:])
                except: continue
                if ev.get("type") == "content_block_delta" and ev["delta"].get("text") and ttft is None:
                    ttft = (time.perf_counter()-t0)*1000
    return ttft, (time.perf_counter()-t0)*1000


def avg(xs): return sum(xs)/len(xs)


def main():
    if not KEY: print("KEY 없음"); return
    print(f"explain mode · K={K} · prefetch dwell={DWELL//1000}s · (단위 ms, 체감 LLM 시간)\n")
    hdr = f"{'시나리오':12}{'기존 v1':>10}{'v2 비스트림':>12}{'v2 스트림(첫토큰)':>18}{'v2 prefetch':>13}"
    print(hdr); print("-"*len(hdr)+"-"*6)
    agg = {k: [] for k in ("v1", "ns", "st", "pf")}
    for name, lines in SCENARIOS:
        img = make_img(lines); ocr = " / ".join(lines)
        v1 = avg([call(SONNET, img, ocr, 2000, "before", False)[1] for _ in range(K)])
        ns = avg([call(HAIKU, img, ocr, 1200, "full", False)[1] for _ in range(K)])
        sts, fts = [], []
        for _ in range(K):
            tt, tot = call(HAIKU, img, ocr, 1200, "full", True); sts.append(tt); fts.append(tot)
        st = avg(sts); full_tot = avg(fts)
        pf = max(0, full_tot - DWELL)
        for k, v in (("v1", v1), ("ns", ns), ("st", st), ("pf", pf)): agg[k].append(v)
        print(f"{name:12}{v1:>10.0f}{ns:>12.0f}{st:>18.0f}{pf:>13.0f}")
    print("-"*len(hdr)+"-"*6)
    print(f"{'평균':12}{avg(agg['v1']):>10.0f}{avg(agg['ns']):>12.0f}{avg(agg['st']):>18.0f}{avg(agg['pf']):>13.0f}")
    print("\n해석: 작을수록 빠름. '스트림'은 첫 글자가 보이는 시점(체감 반응), 나머지는 완성/체감 대기.")
    print(f"prefetch는 dwell {DWELL//1000}s 동안 full이 진행됐다는 가정의 클릭 후 체감 대기.")


if __name__ == "__main__":
    main()

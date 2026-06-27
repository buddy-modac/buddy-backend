"""지연 측정 — translate(이미지/텍스트, 모델, 출력길이)별 TTFT·총시간 비교.

API(Anthropic) 직접 스트리밍 호출로 first-token / total 측정.
'전(before)'은 무거운 케이스: 큰 텍스트-빽빽 이미지 + Sonnet + 긴 출력(verbose).
ANTHROPIC_API_KEY 필요 (server/.env.local).
    python benchmarks/run_latency_test.py
"""
import os, sys, time, json, base64, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
SONNET, HAIKU = "claude-sonnet-4-6", "claude-haiku-4-5-20251001"
PERSONA = "ISTJ"
OCR = ("CITY TRANSIT — SERVICE NOTICE\n"
       "Effective March 1 through April 30\n"
       "Line 2 (Blue) will not stop at Central, Park, or Riverside stations\n"
       "Replacement shuttle buses depart every 12 minutes from Gate C\n"
       "Weekday service 05:30-24:00, Weekend 06:00-23:30\n"
       "Fares unchanged; transfers valid for 90 minutes\n"
       "Monthly pass holders: no additional charge\n"
       "Elevators at Central out of service until further notice\n"
       "Accessibility assistance available at all staffed stations\n"
       "Lost and found: Gate A office, 09:00-18:00 daily\n"
       "For real-time updates scan the QR code or call 1599-0000")


def heavy_image_b64():
    img = Image.new("RGB", (1600, 1200), "white"); d = ImageDraw.Draw(img)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 40)
    except: f = ImageFont.load_default()
    y = 40
    for ln in OCR.split("\n"):
        d.text((40, y), ln, fill="black", font=f); y += 64
    buf = io.BytesIO(); img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def user_msg(concise):
    base = (f"요청: 아래 텍스트를 자연스러운 한국어로 번역해 주세요.\n\n[추출된 텍스트]\n{OCR}")
    if concise:
        base += "\n\n간결하게: 번역문만, 표·대안 표현·부연 설명 없이."
    return base


def timed(model, with_image, max_tokens, concise, img_b64):
    system = build_assistant_system_prompt(PERSONA, "Korean")
    content = []
    if with_image:
        content.append({"type": "image", "source": {"type": "base64",
                        "media_type": "image/png", "data": img_b64}})
    content.append({"type": "text", "text": user_msg(concise)})
    payload = {"model": model, "max_tokens": max_tokens, "system": system, "stream": True,
               "messages": [{"role": "user", "content": content}]}
    t0 = time.perf_counter(); ttft = None; out = []
    with httpx.Client(timeout=120) as c:
        with c.stream("POST", "https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"}, json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data: "): continue
                try: ev = json.loads(line[6:])
                except: continue
                if ev.get("type") == "content_block_delta":
                    t = ev.get("delta", {}).get("text", "")
                    if t:
                        if ttft is None: ttft = time.perf_counter() - t0
                        out.append(t)
    total = time.perf_counter() - t0
    return ttft or total, total, len("".join(out))


def main():
    if not KEY:
        print("ANTHROPIC_API_KEY 없음 — set -a; source server/.env.local; set +a 후 실행"); return
    img = heavy_image_b64()
    print(f"무거운 이미지: 1600x1200, base64 {len(img):,}자, OCR {len(OCR)}자\n")
    configs = [
        ("① 전(현재): Sonnet + 이미지 + 2000tok", SONNET, True, 2000, False),
        ("② 이미지 제거: Sonnet + 텍스트만 + 2000", SONNET, False, 2000, False),
        ("③ +Haiku: Haiku + 텍스트만 + 2000",      HAIKU,  False, 2000, False),
        ("④ +간결: Haiku + 텍스트만 + 400 + 간결", HAIKU,  False, 400,  True),
    ]
    print(f"{'구성':42} {'TTFT':>8} {'총시간':>8} {'출력자':>7}")
    print("-" * 70)
    rows = []
    for name, model, img_on, mt, concise in configs:
        try:
            ttft, total, n = timed(model, img_on, mt, concise, img)
            rows.append((name, ttft, total, n))
            print(f"{name:42} {ttft:7.2f}s {total:7.2f}s {n:6}")
        except Exception as e:
            print(f"{name:42}  ERROR: {e}")
    if len(rows) >= 2:
        b, a = rows[0], rows[-1]
        print("-" * 70)
        print(f"전(①) 총 {b[2]:.2f}s → 후(④) 총 {a[2]:.2f}s  =  {b[2]/a[2]:.1f}배 빠름, "
              f"{b[2]-a[2]:.1f}s 단축 (TTFT {b[1]:.2f}s→{a[1]:.2f}s)")


if __name__ == "__main__":
    main()

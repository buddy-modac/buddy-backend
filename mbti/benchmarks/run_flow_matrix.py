"""전체 플로우 지연 매트릭스 — mode(translate/explain) × detail(brief/full)
 + 현재(before) 기준선 + '더 자세히' reply 케이스. API 스트리밍으로 TTFT·총시간 측정.

의미있는 이미지: 실제 있을 법한 빽빽한 안내문(1600x1200). ANTHROPIC_API_KEY 필요.
    set -a; source server/.env.local; set +a
    python benchmarks/run_flow_matrix.py
"""
import os, sys, time, json, base64, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
SONNET, HAIKU = "claude-sonnet-4-6", "claude-haiku-4-5-20251001"
PERSONA = "ENFJ"
OCR = ("CITY TRANSIT — SERVICE NOTICE\nEffective March 1 through April 30\n"
       "Line 2 (Blue) will not stop at Central, Park, or Riverside stations\n"
       "Replacement shuttle buses depart every 12 minutes from Gate C\n"
       "Weekday service 05:30-24:00, Weekend 06:00-23:30\n"
       "Fares unchanged; transfers valid for 90 minutes\n"
       "Monthly pass holders: no additional charge\n"
       "Elevators at Central out of service until further notice\n"
       "Accessibility assistance available at all staffed stations\n"
       "Lost and found: Gate A office, 09:00-18:00 daily\n"
       "For real-time updates scan the QR code or call 1599-0000")
PARENT = "이전 답변: 블루 2호선이 3월1일~4월30일 센트럴·파크·리버사이드역에 정차하지 않습니다."


def heavy_img():
    img = Image.new("RGB", (1600, 1200), "white"); d = ImageDraw.Draw(img)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 40)
    except: f = ImageFont.load_default()
    y = 40
    for ln in OCR.split("\n"):
        d.text((40, y), ln, fill="black", font=f); y += 64
    b = io.BytesIO(); img.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def umsg(mode, detail, parent=False):
    task = "자연스러운 한국어로 번역" if mode == "translate" else "의미를 설명"
    ctx = (f"[이전 대화]\n{PARENT}\n위 맥락을 참고해서 답해 주세요.\n\n" if parent else "")
    tip = {"brief": ("\n\n간결하게: 핵심만, 표·대안·부연 없이 1~3줄." ),
           "full":  ("\n\n충분히 자세하게: 필요하면 짧은 목록/예시 포함."),
           "before": ""}[detail]
    return f"{ctx}요청: 아래 텍스트를 {task}해 주세요.\n\n[추출된 텍스트]\n{OCR}{tip}"


def timed(model, with_image, max_tokens, mode, detail, img, parent=False):
    system = build_assistant_system_prompt(PERSONA, "Korean")
    content = []
    if with_image:
        content.append({"type": "image", "source": {"type": "base64",
                        "media_type": "image/png", "data": img}})
    content.append({"type": "text", "text": umsg(mode, detail, parent)})
    payload = {"model": model, "max_tokens": max_tokens, "system": system, "stream": True,
               "messages": [{"role": "user", "content": content}]}
    t0 = time.perf_counter(); ttft = None; out = []
    with httpx.Client(timeout=120) as c:
        with c.stream("POST", "https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"}, json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: "):
                    try: ev = json.loads(line[6:])
                    except: continue
                    if ev.get("type") == "content_block_delta":
                        t = ev.get("delta", {}).get("text", "")
                        if t:
                            if ttft is None: ttft = time.perf_counter() - t0
                            out.append(t)
    return (ttft or 0), time.perf_counter() - t0, len("".join(out))


def main():
    if not KEY:
        print("ANTHROPIC_API_KEY 없음"); return
    img = heavy_img()
    print(f"이미지: 1600x1200 안내문, base64 {len(img):,}자\n")
    # (라벨, 모델, 이미지포함, 캡, mode, detail, parent)
    cfgs = [
        ("translate · 현재(Sonnet+이미지+2000)", SONNET, True, 2000, "translate", "before", False),
        ("translate · brief (Haiku·텍스트·400)", HAIKU, False, 400, "translate", "brief", False),
        ("translate · full  (Haiku·텍스트·800)", HAIKU, False, 800, "translate", "full", False),
        ("explain · 현재(Sonnet+이미지+2000)",   SONNET, True, 2000, "explain", "before", False),
        ("explain · brief (Haiku·텍스트·400)",   HAIKU, False, 400, "explain", "brief", False),
        ("explain · full  (Haiku·텍스트·1200)",  HAIKU, False, 1200, "explain", "full", False),
        ("[더자세히] explain·full+reply맥락(Haiku)", HAIKU, False, 1200, "explain", "full", True),
    ]
    print(f"{'플로우':44}{'TTFT':>8}{'총시간':>8}{'출력자':>7}")
    print("-" * 71)
    res = {}
    for label, model, imgon, cap, mode, detail, parent in cfgs:
        try:
            ttft, total, n = timed(model, imgon, cap, mode, detail, img, parent)
            res[label] = total
            print(f"{label:44}{ttft:7.2f}s{total:7.2f}s{n:6}")
        except Exception as e:
            print(f"{label:44}  ERROR: {e}")
    print("-" * 71)
    def cmp(before, after):
        if before in res and after in res:
            b, a = res[before], res[after]
            print(f"· {after.split('·')[0].strip()}: {b:.1f}s → {a:.1f}s ({b/a:.1f}배, -{b-a:.1f}s)")
    cmp("translate · 현재(Sonnet+이미지+2000)", "translate · brief (Haiku·텍스트·400)")
    cmp("explain · 현재(Sonnet+이미지+2000)", "explain · brief (Haiku·텍스트·400)")


if __name__ == "__main__":
    main()

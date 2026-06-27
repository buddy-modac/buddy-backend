"""병렬(fan-out+merge) vs 단일 호출 — ask 액션 기준. 우리 구조(httpx+thread).
측정: total, first_result(draft 시점), 호출수(비용 프록시), 단일 스트리밍 TTFT.
    set -a; source server/.env.local; set +a
    python benchmarks/run_parallel_test.py
"""
import os, sys, time, json, base64, io
import concurrent.futures as cf
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
HAIKU = "claude-haiku-4-5-20251001"
SYSTEM = build_assistant_system_prompt("ENFJ", "Korean")
OCR = ("CITY TRANSIT — SERVICE NOTICE\nLine 2 (Blue) will not stop at Central, Park, Riverside\n"
       "Replacement shuttle every 12 min from Gate C\nElevators at Central out of service\n"
       "Weekday 05:30-24:00, transfers valid 90 min, call 1599-0000")
QUESTION = "센트럴역에서 환승하려는데 지금 어떻게 해야 해?"
URL = "https://api.anthropic.com/v1/messages"
H = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def img_b64():
    im = Image.new("RGB", (1200, 700), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 34)
    except: f = ImageFont.load_default()
    y = 30
    for ln in OCR.split("\n"): d.text((30, y), ln, fill="black", font=f); y += 56
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def call(prompt, max_tokens, image=None):
    """단발 호출 → (text, 소요s)."""
    content = []
    if image: content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}})
    content.append({"type": "text", "text": prompt})
    payload = {"model": HAIKU, "max_tokens": max_tokens, "system": SYSTEM,
               "messages": [{"role": "user", "content": content}]}
    t0 = time.perf_counter()
    r = httpx.post(URL, headers=H, json=payload, timeout=120); r.raise_for_status()
    txt = "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")
    return txt, time.perf_counter() - t0


def stream_ttft(prompt, max_tokens, image=None):
    content = []
    if image: content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}})
    content.append({"type": "text", "text": prompt})
    payload = {"model": HAIKU, "max_tokens": max_tokens, "system": SYSTEM, "stream": True,
               "messages": [{"role": "user", "content": content}]}
    t0 = time.perf_counter(); ttft = None
    with httpx.Client(timeout=120) as c, c.stream("POST", URL, headers=H, json=payload) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                try: ev = json.loads(line[6:])
                except: continue
                if ev.get("type") == "content_block_delta" and ev["delta"].get("text"):
                    if ttft is None: ttft = time.perf_counter() - t0
    return ttft or 0, time.perf_counter() - t0


def main():
    if not KEY: print("KEY 없음"); return
    img = img_b64()
    base = f"[추출 텍스트]\n{OCR}\n[질문]\n{QUESTION}\n"

    print("=== A. 단일 호출 (이미지+텍스트, ask, brief) ===")
    _, single_total = call(base + "질문에 간결히 답해.", 500, img)
    s_ttft, s_str_total = stream_ttft(base + "질문에 간결히 답해.", 500, img)
    print(f"  단일 total: {single_total:.2f}s | 스트리밍 TTFT(첫결과): {s_ttft:.2f}s, total {s_str_total:.2f}s | 호출 1")

    print("\n=== B. 병렬 4서브 + merge ===")
    tasks = {
        "intent":  (base + "이 질문의 의도만 한 줄로 분류해.", 120, None),
        "text_ev": (base + "OCR에서 질문 관련 근거 텍스트만 뽑아 나열해.", 200, None),
        "visual_ev": (base + "이미지에서 질문 관련 시각 근거만 뽑아 나열해.", 200, img),
        "quick":   (base + "질문에 빠른 초안 답을 간결히.", 300, img),
    }
    t0 = time.perf_counter(); durs = {}; vals = {}
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(call, p, mt, im): name for name, (p, mt, im) in tasks.items()}
        for fut in cf.as_completed(futs):
            name = futs[fut]; v, d = fut.result(); vals[name] = v; durs[name] = d
    fanout = time.perf_counter() - t0
    merge_prompt = (base + "아래 분석들을 종합해 최종 답을 간결히:\n" +
                    "\n".join(f"[{k}] {v}" for k, v in vals.items()))
    _, merge_dur = call(merge_prompt, 500)
    par_total = time.perf_counter() - t0
    print(f"  서브 소요: " + ", ".join(f"{k} {durs[k]:.1f}s" for k in durs))
    print(f"  fan-out(=max 서브): {fanout:.2f}s | merge: {merge_dur:.2f}s")
    print(f"  병렬 total: {par_total:.2f}s | first_result(quick draft): {durs.get('quick',0):.2f}s | 호출 5")

    print("\n=== 비교 ===")
    print(f"  total    단일 {single_total:.2f}s  vs  병렬 {par_total:.2f}s   → 단일이 {par_total-single_total:+.1f}s")
    print(f"  첫결과   단일(스트림) {s_ttft:.2f}s  vs  병렬(draft) {durs.get('quick',0):.2f}s")
    print(f"  호출수   단일 1  vs  병렬 5  (비용 ~5배)")


if __name__ == "__main__":
    main()

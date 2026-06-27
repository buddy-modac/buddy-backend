"""결판: '더 자세히(full)' 클릭 후 체감 대기 — 3전략 비교.

  A 순차 비스트리밍 : 클릭 → full 완성까지 멍하니 대기        = full_total
  B 순차 스트리밍   : 클릭 → 첫 토큰 흐르기 시작              = full_TTFT
  C prefetch        : brief 읽는 동안 full 미리 돌림           = max(0, full_total - dwell)
                      (dwell = 유저가 brief 읽고 클릭하기까지 시간)

핵심 질문: 스트리밍(B)만으로 충분한가, prefetch(C)까지 갈 가치가 있나?
같은 이미지·explain·Haiku(v2 full). ANTHROPIC_API_KEY 필요(API 백엔드 경로 직접 호출).
    set -a; source server/.env.local; set +a
    python benchmarks/run_prefetch_verdict.py
"""
import os, sys, json, time, base64, io
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
HAIKU = "claude-haiku-4-5-20251001"
URL = "https://api.anthropic.com/v1/messages"
H = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
SYS = build_assistant_system_prompt("ENFP", "Korean", amplify=True)
OCR = ("CITY TRANSIT — SERVICE NOTICE / Line 2 (Blue) will not stop at Central, Park, Riverside "
       "(Mar 1-Apr 30) / Replacement shuttle every 12 min from Gate C / Elevators at Central out of service")
K = 3


def img():
    im = Image.new("RGB", (900, 400), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26)
    except: f = ImageFont.load_default()
    for i, ln in enumerate(OCR.split(" / ")): d.text((20, 20 + i*48), ln, fill="black", font=f)
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def msg(detail):
    tip = "\n\n충분히 자세하게: 필요하면 짧은 목록/예시 포함." if detail == "full" else "\n\n간결하게: 핵심만 1~3줄."
    return f"요청: 아래 이미지와 텍스트의 의미를 설명해 주세요.\n\n[추출된 텍스트]\n{OCR}{tip}"


def run(detail, image, stream):
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}},
               {"type": "text", "text": msg(detail)}]
    payload = {"model": HAIKU, "max_tokens": 1200 if detail == "full" else 400,
               "system": SYS, "messages": [{"role": "user", "content": content}]}
    t0 = time.perf_counter(); ttft = None; n = 0
    if not stream:
        r = httpx.post(URL, headers=H, json=payload, timeout=120); r.raise_for_status()
        txt = "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")
        return None, (time.perf_counter()-t0)*1000, len(txt)
    payload["stream"] = True
    with httpx.Client(timeout=120) as c, c.stream("POST", URL, headers=H, json=payload) as r:
        for line in r.iter_lines():
            if line.startswith("data: "):
                try: ev = json.loads(line[6:])
                except: continue
                if ev.get("type") == "content_block_delta" and ev["delta"].get("text"):
                    if ttft is None: ttft = (time.perf_counter()-t0)*1000
                    n += len(ev["delta"]["text"])
    return ttft, (time.perf_counter()-t0)*1000, n


def avg(xs): return sum(xs)/len(xs)


def main():
    if not KEY: print("KEY 없음"); return
    im = img()
    print(f"explain · Haiku v2 full · K={K}\n측정 중…\n")
    full_total, full_ttft, brief_total = [], [], []
    for _ in range(K):
        _, ft, _ = run("full", im, stream=False); full_total.append(ft)
        tt, _, _ = run("full", im, stream=True); full_ttft.append(tt)
        _, bt, _ = run("brief", im, stream=False); brief_total.append(bt)
    FT, FTTFT, BT = avg(full_total), avg(full_ttft), avg(brief_total)
    print(f"full 총 생성: {FT:.0f} ms | full 첫토큰(TTFT): {FTTFT:.0f} ms | brief 총: {BT:.0f} ms\n")

    print("=== '더 자세히' 클릭 후 체감 대기 ===")
    print(f"  A 순차 비스트리밍 : {FT:7.0f} ms  (완성까지 멍)")
    print(f"  B 순차 스트리밍   : {FTTFT:7.0f} ms  (첫 글자 흐름)   ← 공짜")
    for dwell in (2000, 4000, 6000):
        pre = max(0, FT - dwell)
        print(f"  C prefetch(dwell {dwell//1000}s): {pre:7.0f} ms  (읽는 {dwell//1000}초 동안 full 진행)")
    print("\n=== 결판: prefetch가 스트리밍보다 추가로 깎는 시간 ===")
    for dwell in (2000, 4000, 6000):
        pre = max(0, FT - dwell)
        gain = FTTFT - pre   # 스트리밍 대비 prefetch 순증 이득(+면 prefetch가 더 빠름)
        verdict = f"prefetch {gain:+.0f} ms" + ("  → 이득 미미/역전" if gain < 300 else "  → prefetch 유의미")
        print(f"  dwell {dwell//1000}s: 스트리밍 {FTTFT:.0f} vs prefetch {pre:.0f}  =  {verdict}")


if __name__ == "__main__":
    main()

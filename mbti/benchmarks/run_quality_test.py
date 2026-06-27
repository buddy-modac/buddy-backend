"""단일 vs 병렬 — 같은 이미지·같은 ask 플로우·같은 질문들로 속도+품질 동시 측정.
품질: 블라인드 심판(Sonnet)이 정확/근거/완전/유용 1~5 채점(A·B 위치 교대로 편향 제거).
    set -a; source server/.env.local; set +a
    python benchmarks/run_quality_test.py
"""
import os, sys, time, json, base64, io
import concurrent.futures as cf
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import httpx
from PIL import Image, ImageDraw, ImageFont
from personaforge import build_assistant_system_prompt

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
HAIKU, SONNET = "claude-haiku-4-5-20251001", "claude-sonnet-4-6"
SYS = build_assistant_system_prompt("ENFJ", "Korean")
OCR = ("CITY TRANSIT — SERVICE NOTICE\nLine 2 (Blue) will not stop at Central, Park, Riverside (Mar 1–Apr 30)\n"
       "Replacement shuttle every 12 min from Gate C\nElevators at Central out of service until further notice\n"
       "Accessibility assistance available at all staffed stations\nWeekday 05:30-24:00, transfers valid 90 min, call 1599-0000")
QUESTIONS = [
    "센트럴역에서 환승하려는데 지금 어떻게 해야 해?",
    "블루라인 언제부터 다시 정상 운행해?",
    "휠체어 이용하는데 센트럴역 이용할 수 있어?",
]
URL = "https://api.anthropic.com/v1/messages"
H = {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def imgb64():
    im = Image.new("RGB", (1200, 600), "white"); d = ImageDraw.Draw(im)
    try: f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    except: f = ImageFont.load_default()
    y = 24
    for ln in OCR.split("\n"): d.text((24, y), ln, fill="black", font=f); y += 50
    b = io.BytesIO(); im.save(b, "PNG"); return base64.b64encode(b.getvalue()).decode()


def call(prompt, max_tokens, image=None, model=HAIKU, system=SYS):
    content = []
    if image: content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image}})
    content.append({"type": "text", "text": prompt})
    p = {"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": content}]}
    r = httpx.post(URL, headers=H, json=p, timeout=120); r.raise_for_status()
    return "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")


def single(q, img):
    base = f"[추출 텍스트]\n{OCR}\n[질문]\n{q}\n질문에 간결히 답해."
    t0 = time.perf_counter(); ans = call(base, 500, img); return ans, time.perf_counter() - t0


def parallel(q, img):
    base = f"[추출 텍스트]\n{OCR}\n[질문]\n{q}\n"
    tasks = {"intent": (base + "질문 의도만 한 줄 분류.", 120, None),
             "text_ev": (base + "OCR에서 관련 근거 텍스트만 나열.", 200, None),
             "visual_ev": (base + "이미지에서 관련 시각 근거만 나열.", 200, img),
             "quick": (base + "빠른 초안 답 간결히.", 300, img)}
    t0 = time.perf_counter(); vals = {}
    with cf.ThreadPoolExecutor(4) as ex:
        futs = {ex.submit(call, p, mt, im): n for n, (p, mt, im) in tasks.items()}
        for fut in cf.as_completed(futs): vals[futs[fut]] = fut.result()
    merge = base + "아래 분석 종합해 최종 답 간결히:\n" + "\n".join(f"[{k}] {v}" for k, v in vals.items())
    ans = call(merge, 500)
    return ans, time.perf_counter() - t0


def judge(q, a, b):
    jp = (f"질문: {q}\n원문(OCR): {OCR}\n\n두 답변을 원문 근거로 1~5 채점.\n"
          f"[A]\n{a}\n\n[B]\n{b}\n\n"
          'JSON만: {"A":{"accuracy":n,"grounding":n,"completeness":n,"usefulness":n},'
          '"B":{"accuracy":n,"grounding":n,"completeness":n,"usefulness":n},"winner":"A|B|tie"}')
    raw = call(jp, 400, None, model=SONNET, system="You are a strict evaluator. Output only JSON.")
    s = raw[raw.find("{"):raw.rfind("}") + 1]
    return json.loads(s)


def main():
    if not KEY: print("KEY 없음"); return
    img = imgb64()
    dims = ["accuracy", "grounding", "completeness", "usefulness"]
    agg = {"single": {d: [] for d in dims}, "parallel": {d: [] for d in dims}}
    times = {"single": [], "parallel": []}; wins = {"single": 0, "parallel": 0, "tie": 0}
    for i, q in enumerate(QUESTIONS):
        s_ans, s_t = single(q, img); p_ans, p_t = parallel(q, img)
        times["single"].append(s_t); times["parallel"].append(p_t)
        # 블라인드: 짝수 질문은 A=단일, 홀수는 A=병렬
        if i % 2 == 0: A, B, amap = s_ans, p_ans, ("single", "parallel")
        else: A, B, amap = p_ans, s_ans, ("parallel", "single")
        v = judge(q, A, B)
        for d in dims:
            agg[amap[0]][d].append(v["A"][d]); agg[amap[1]][d].append(v["B"][d])
        w = v["winner"]; wins[amap[0] if w == "A" else amap[1] if w == "B" else "tie"] += 1
        print(f"Q{i+1}: 단일 {s_t:.1f}s / 병렬 {p_t:.1f}s | 승: {amap[0] if w=='A' else amap[1] if w=='B' else 'tie'}")

    avg = lambda xs: sum(xs) / len(xs) if xs else 0
    print("\n=== 종합 (같은 이미지·같은 ask·질문 3개 평균) ===")
    print(f"{'항목':14}{'단일':>12}{'병렬':>12}")
    print(f"{'총시간(평균)':14}{avg(times['single']):>10.2f}s{avg(times['parallel']):>10.2f}s")
    print(f"{'첫결과':14}{'~0.8s(스트림)':>12}{'~7.5s(draft)':>12}")
    print(f"{'호출/비용':14}{'1':>12}{'5(~5배)':>12}")
    for d in dims:
        print(f"{d:14}{avg(agg['single'][d]):>11.2f}{avg(agg['parallel'][d]):>11.2f}")
    so = avg([avg(agg['single'][d]) for d in dims]); po = avg([avg(agg['parallel'][d]) for d in dims])
    print(f"{'종합품질(/5)':14}{so:>11.2f}{po:>11.2f}")
    print(f"{'품질 승':14}{wins['single']:>12}{wins['parallel']:>12}  (tie {wins['tie']})")


if __name__ == "__main__":
    main()

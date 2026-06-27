# Image Generation Eval Report

## Summary

이미지 생성/편집 테스트 하네스를 추가하고, 총 15개 케이스를 준비했다.

- Mock report: 기본/기사형 케이스 실행
- Real API report: 기본 핵심 3개 케이스 + 기사형 3개 케이스 실행
- Model matrix report: 기사형 대표 3개 케이스를 `gpt-image-1`, `gpt-image-1.5`, `gpt-image-2`로 비교
- Provider: OpenAI
- Model: `gpt-image-1`
- Output dir: `eval/results/image-gen-real/`
- Article output dir: `eval/results/image-gen-article-real/`
- Model matrix output dir: `eval/results/image-gen-model-matrix/`

## Case Set

| Case | Action | Purpose |
| --- | --- | --- |
| `buddy-simple-generate` | `generate` | 단순 Buddy 마스코트 이미지 생성 |
| `buddy-translate-text-edit` | `translate-text` | 이미지 내 텍스트를 한국어로 번역해 반영 |
| `buddy-image-edit` | `edit-image` | 기존 이미지에 Buddy 설명 callout 추가 |
| `buddy-quality-low` | `generate` | 같은 프롬프트의 low 품질 기준선 |
| `buddy-quality-high` | `generate` | 같은 프롬프트의 high 품질 비교 |
| `buddy-size-wide` | `generate` | 와이드 온보딩 이미지 생성 |
| `buddy-format-webp` | `generate` | WebP 출력 및 압축 효율 확인 |
| `buddy-dense-text-translation` | `translate-text` | 텍스트가 많은 차트/리포트 번역 편집 |
| `buddy-preserve-layout-edit` | `edit-image` | 원본 레이아웃 보존형 이미지 수정 |
| `medium-article-translate-ko` | `translate-text` | 기사형 스크린샷의 텍스트 한국어 번역 적용 |
| `medium-article-content-rewrite` | `edit-image` | 기사 제목/부제 내용을 더 차분한 표현으로 수정 |
| `medium-article-image-change` | `edit-image` | 기사 본문 이미지 영역만 새로운 비주얼로 변경 |
| `medium-article-highlight` | `edit-image` | 기사형 스크린샷에 하이라이트 표시 추가 |
| `medium-article-shapes` | `edit-image` | 기사형 스크린샷에 사각형/화살표 도형 추가 |
| `medium-article-speech-bubble` | `edit-image` | 기사형 스크린샷에 Buddy 말풍선 추가 |

## Real Run Results

| Case | Action | Latency | Output | Size | Bytes | Report |
| --- | --- | ---: | --- | --- | ---: | --- |
| `buddy-simple-generate` | `generate` | 21.276s | PNG | 1024x1024 | 1,501,505 | `eval/results/image-gen-real/buddy-simple-generate-2026-06-27T05-39-09-624Z.md` |
| `buddy-translate-text-edit` | `translate-text` | 16.220s | PNG | 1024x1024 | 901,311 | `eval/results/image-gen-real/buddy-translate-text-edit-2026-06-27T05-39-25-853Z.md` |
| `buddy-image-edit` | `edit-image` | 14.922s | PNG | 1024x1024 | 914,312 | `eval/results/image-gen-real/buddy-image-edit-2026-06-27T05-39-40-782Z.md` |

## Article Screenshot Real Run Results

| Case | Action | Latency | Output | Size | Bytes | Report |
| --- | --- | ---: | --- | --- | ---: | --- |
| `medium-article-translate-ko` | `translate-text` | 28.015s | PNG | 1024x1536 | 1,665,309 | `eval/results/image-gen-article-real/medium-article-translate-ko-2026-06-27T05-45-45-642Z.md` |
| `medium-article-content-rewrite` | `edit-image` | 26.803s | PNG | 1024x1536 | 1,591,807 | `eval/results/image-gen-article-real/medium-article-content-rewrite-2026-06-27T05-46-12-453Z.md` |
| `medium-article-image-change` | `edit-image` | 28.414s | PNG | 1024x1536 | 1,698,276 | `eval/results/image-gen-article-real/medium-article-image-change-2026-06-27T05-46-40-874Z.md` |

## Model Matrix Real Run Results

| Case | Model | Latency | Size | Bytes | Report |
| --- | --- | ---: | --- | ---: | --- |
| `medium-article-translate-ko` | `gpt-image-1` | 30.516s | 1024x1536 | 1,629,917 | `eval/results/image-gen-model-matrix/medium-article-translate-ko-gpt-image-1-2026-06-27T05-59-02-348Z.md` |
| `medium-article-translate-ko` | `gpt-image-1.5` | 29.314s | 1024x1536 | 968,275 | `eval/results/image-gen-model-matrix/medium-article-translate-ko-gpt-image-1.5-2026-06-27T05-59-31-670Z.md` |
| `medium-article-translate-ko` | `gpt-image-2` | 48.738s | 1024x1536 | 1,558,404 | `eval/results/image-gen-model-matrix/medium-article-translate-ko-gpt-image-2-2026-06-27T06-00-20-413Z.md` |
| `medium-article-image-change` | `gpt-image-1` | 27.080s | 1024x1536 | 1,594,668 | `eval/results/image-gen-model-matrix/medium-article-image-change-gpt-image-1-2026-06-27T06-00-47-500Z.md` |
| `medium-article-image-change` | `gpt-image-1.5` | 29.538s | 1024x1536 | 1,353,362 | `eval/results/image-gen-model-matrix/medium-article-image-change-gpt-image-1.5-2026-06-27T06-01-17-048Z.md` |
| `medium-article-image-change` | `gpt-image-2` | 53.427s | 1024x1536 | 1,791,524 | `eval/results/image-gen-model-matrix/medium-article-image-change-gpt-image-2-2026-06-27T06-02-10-485Z.md` |
| `medium-article-speech-bubble` | `gpt-image-1` | 28.575s | 1024x1536 | 1,576,946 | `eval/results/image-gen-model-matrix/medium-article-speech-bubble-gpt-image-1-2026-06-27T06-02-39-067Z.md` |
| `medium-article-speech-bubble` | `gpt-image-1.5` | 29.882s | 1024x1536 | 1,121,982 | `eval/results/image-gen-model-matrix/medium-article-speech-bubble-gpt-image-1.5-2026-06-27T06-03-08-964Z.md` |
| `medium-article-speech-bubble` | `gpt-image-2` | 50.997s | 1024x1536 | 1,567,449 | `eval/results/image-gen-model-matrix/medium-article-speech-bubble-gpt-image-2-2026-06-27T06-03-59-973Z.md` |

### Model Matrix Notes

- `gpt-image-1.5` was the most efficient in this run: latency stayed near `gpt-image-1`, while file size was consistently smaller.
- `gpt-image-2` was much slower in all three article edit cases, roughly 49-53 seconds.
- For full-page article screenshots, all models still show text preservation risk. The model upgrade alone does not remove the need for crop/mask-based editing and OCR checks.
- The newly added speech-bubble case gives a better product-like annotation test than pure text rewriting, but it still needs manual review for occlusion and text preservation.

## Streaming Demo Result

`stream: true` and `partial_images: 2` were tested through the local demo view.

| Metric | Value |
| --- | ---: |
| Model | `gpt-image-1.5` |
| Size | 1024x1024 |
| Quality | medium |
| First partial image | 10.04s |
| Second partial image | 14.31s |
| Final image | 17.97s |
| Images received | 3 |
| Perceived wait saved | 7.92s |

The total generation time was still about 18 seconds, but the first preview arrived after about 10 seconds. For Buddy UX, this means streaming is useful for perceived latency even when it does not reduce final completion time.

Detailed result: `eval/results/image-gen-model-matrix/stream-demo-result.md`

## Observations

### `buddy-simple-generate`

- Prompt adherence is mostly good: friendly mascot, centered composition, no visible text.
- Visual quality is usable for a product concept.
- Risk: `background: transparent` was requested, but the rendered image visually includes a gray background. The output file is RGBA, so follow-up should inspect actual alpha distribution before deciding whether this is a prompt failure or viewer/background artifact.

### `buddy-translate-text-edit`

- The image was translated into Korean-like UI text, so the task direction worked.
- Risk: the model regenerated much of the UI instead of preserving the original image exactly.
- Risk: some Korean text looks awkward or malformed.
- This case needs a stricter prompt and an automated comparison step if Buddy requires precise text replacement rather than creative reconstruction.

### `buddy-image-edit`

- The Buddy assistant callout was added successfully.
- Risk: the callout text is partially clipped off-canvas.
- Risk: original UI text/detail was simplified or lost.
- This suggests edit prompts should include stricter placement constraints, or the product should provide a mask/safe region when available.

### `medium-article-translate-ko`

- The model attempted full-page Korean translation.
- The image grid and general article structure were preserved.
- Risk: Korean text quality is poor and many glyphs are malformed.
- This is a strong signal that full-page text translation inside a raster image is not reliable enough for production without OCR/text-layer reconstruction.

### `medium-article-content-rewrite`

- The requested headline replacement was mostly applied.
- Risk: metadata, dates, author text, body copy, and caption were unintentionally changed.
- This suggests headline-only edits should be done on a cropped title region or with a mask, not on the full screenshot.

### `medium-article-image-change`

- The brain image area was replaced with a modern editorial illustration.
- Risk: surrounding text and metadata became corrupted, despite instructions to preserve them.
- The useful path is region-limited editing: crop/mask the image area, edit only that region, then composite it back onto the original screenshot.

## Evaluation Takeaways

1. Simple generation is already good enough for concept/illustration exploration.
2. Text translation inside images is the riskiest case because it tends to redraw UI and can produce broken text.
3. Full-screenshot edit requests tend to mutate unrelated areas, especially article-style screens with lots of text.
4. Image edit works better when the editable region is visually large and text outside the region is not important.
5. For Buddy product use, generation can be offered as a creative feature first; precise screenshot editing should stay experimental until preservation metrics are added.

## Recommended Next Tests

1. Run the quality matrix: `buddy-quality-low`, `buddy-simple-generate`, `buddy-quality-high`.
2. Run the format matrix: PNG vs WebP with compression.
3. Add alpha validation for transparent-background outputs.
4. Add image-diff or OCR-based checks for edit cases:
   - source UI text still visible
   - important regions not covered
   - translated text legible
   - numeric values preserved
5. Add prompt variants for strict editing:
   - "do not redraw the screen"
   - "only modify text layers"
   - "leave all shapes and positions unchanged"
   - "place new callout fully inside the canvas"
6. Add crop/mask-based edit flow:
   - crop target region
   - edit cropped image only
   - composite edited region back onto original screenshot
   - compare OCR before/after outside the edited region

## Commands

```bash
node scripts/image-gen-eval.mjs --all-cases --mock
```

```bash
node scripts/image-gen-eval.mjs \
  --cases eval/image-gen-cases/buddy-simple-generate.json,eval/image-gen-cases/buddy-translate-text-edit.json,eval/image-gen-cases/buddy-image-edit.json \
  --output-dir eval/results/image-gen-real
```

```bash
node scripts/image-gen-eval.mjs \
  --cases eval/image-gen-cases/medium-article-translate-ko.json,eval/image-gen-cases/medium-article-content-rewrite.json,eval/image-gen-cases/medium-article-image-change.json \
  --output-dir eval/results/image-gen-article-real
```

```bash
node scripts/image-gen-eval.mjs \
  --cases eval/image-gen-cases/medium-article-translate-ko.json,eval/image-gen-cases/medium-article-image-change.json,eval/image-gen-cases/medium-article-speech-bubble.json \
  --models gpt-image-1,gpt-image-1.5,gpt-image-2 \
  --output-dir eval/results/image-gen-model-matrix
```

```bash
npm run eval:image-stream-demo
```

# AI Eval

스크린샷 기반 AI 액션의 단일 요청, 병렬 요청, provider 혼합 요청을 로컬에서 비교하는 실험 지면입니다.

## Dry run

```bash
node scripts/ai-eval.mjs --case eval/cases/sample-ask.json --dry-run
```

리포트 산출물 형태만 확인하려면 mock 실행을 사용합니다. 외부 API를 호출하지 않습니다.

```bash
node scripts/ai-eval.mjs --all-cases --mock
```

## Run

```bash
node scripts/ai-eval.mjs --case eval/cases/sample-ask.json
```

실제 실행은 OpenAI/Claude API를 호출하므로 비용이 발생할 수 있습니다.

모든 샘플 케이스를 한 번에 실행하려면:

```bash
node scripts/ai-eval.mjs --all-cases
```

OpenAI/Claude 모델을 여러 개 비교하려면:

```bash
node scripts/ai-eval.mjs \
  --all-cases \
  --openai-models gpt-5.4,gpt-5.4-mini \
  --claude-models claude-sonnet-4-6,claude-haiku-4-5
```

## Image-reading model matrix

`docs/api 별 리서치.md`의 입력 정책을 반영해, OCR 텍스트를 보조로 두고 실제 이미지 안의 숫자/표/문맥을 모델이 읽는지 확인하는 케이스도 포함되어 있습니다.

```bash
node scripts/ai-eval.mjs \
  --cases eval/cases/kbs-wealth-ask.json,eval/cases/kbs-wealth-describe.json,eval/cases/kbs-wealth-translate.json \
  --strategies single \
  --providers openai,claude \
  --openai-models gpt-5.4,gpt-5.4-mini \
  --claude-models claude-sonnet-4-6,claude-haiku-4-5
```

이 케이스들은 `expectedFindings`를 가지고 있어, 응답에 핵심 수치와 문맥이 포함됐는지 자동 finding score를 계산합니다.

- `inputMode: ocr-image`: OCR 텍스트와 이미지를 함께 보냅니다.
- `inputMode: ocr-only`: 이미지 없이 OCR 텍스트만 보냅니다.
- `inputMode: image-only`: OCR 텍스트 없이 이미지만 보냅니다.
- `openaiImageDetail`: OpenAI Responses API의 이미지 detail 값을 케이스별로 지정합니다.
- `imageFidelity`, `imageTextPolicy`: Claude처럼 직접 detail 옵션이 없는 provider까지 비교하기 위한 리포트용 정책 필드입니다.

## Case format

```json
{
  "id": "sample-ask",
  "action": "ask",
  "imagePath": "../images/sample-screen.png",
  "inputMode": "ocr-image",
  "openaiImageDetail": "high",
  "question": "이 에러는 왜 나는 거야?",
  "ocrText": "...",
  "expectedFindings": [
    { "label": "핵심 수치", "anyOf": ["19배", "19x"] }
  ]
}
```

- `action`: `translate`, `describe`, `ask`
- `imagePath`: case JSON 파일 위치 기준 상대 경로
- `ocrText`: 클라이언트에서 OCR 처리된 텍스트
- `question`: `ask` 액션에서만 필수
- `targetLanguage`: `translate` 액션에서 사용하며 기본값은 `ko`
- `inputMode`: 모델 요청에 넣을 입력 조합. 기본값은 `ocr-image`
- `openaiImageDetail`: OpenAI 이미지 detail. 기본값은 `auto`
- `expectedFindings`: 응답 품질 자동 체크용 핵심 항목

결과는 `eval/results/`에 JSON과 Markdown으로 저장됩니다.

## Reports

각 실행은 아래 산출물을 생성합니다.

- 케이스별 JSON: 원본 API 응답, provider/model, 호출별 latency, usage, 비용 추정
- 케이스별 Markdown: 요청 구조, 실행 결과, 자동 분석, 품질 평가 루브릭, 사람이 남길 품질 메모
- 전체 비교 HTML: `eval/results/index.html`

검증 축은 다음과 같습니다.

- `latencyTotalMs`: 최종 응답까지 걸린 시간
- `latencyFirstResultMs`: 병렬 작업 중 첫 결과가 나온 시간
- `inputTokens`, `outputTokens`: provider usage 기반 토큰 수
- `estimatedCostUsd`: 스크립트 내부 가격표 기반 비용 추정
- `finding score`: `expectedFindings` 중 응답에 포함된 항목 비율
- aggregate metrics: 전략별, provider별, 모델별 평균 지연시간과 총 비용

## Image generation eval

이미지 생성/편집 API는 입력과 결과 구조가 달라 별도 하네스로 분리했습니다.

```bash
node scripts/image-gen-eval.mjs --all-cases --dry-run
node scripts/image-gen-eval.mjs --all-cases --mock
```

실제 OpenAI 이미지 API를 호출하려면 `.env`에 `OPENAI_API_KEY` 또는 `CODEX_API_KEY`를 설정하고 `--mock` 없이 실행합니다.

```bash
node scripts/image-gen-eval.mjs --all-cases
```

기본 케이스는 `eval/image-gen-cases/`에 있습니다.

- `buddy-simple-generate`: 단순 이미지 생성
- `buddy-translate-text-edit`: 이미지 안의 텍스트를 한국어로 번역해 반영
- `buddy-image-edit`: 기존 이미지를 수정해 Buddy 설명 callout 반영
- `buddy-quality-low`, `buddy-quality-high`: 같은 프롬프트의 품질 옵션 비교
- `buddy-size-wide`: 와이드 온보딩 이미지 생성
- `buddy-format-webp`: WebP 출력과 압축 효율 확인
- `buddy-dense-text-translation`: 텍스트가 많은 차트/리포트 이미지 번역 편집
- `buddy-preserve-layout-edit`: 원본 레이아웃 보존형 이미지 수정
- `medium-article-translate-ko`: 기사형 스크린샷의 텍스트 한국어 번역 적용
- `medium-article-content-rewrite`: 기사 제목/부제 내용을 더 차분한 표현으로 수정
- `medium-article-image-change`: 기사 본문 이미지 영역만 새로운 비주얼로 변경
- `medium-article-highlight`: 기사형 스크린샷에 하이라이트 표시 추가
- `medium-article-shapes`: 기사형 스크린샷에 사각형/화살표 도형 추가
- `medium-article-speech-bubble`: 기사형 스크린샷에 Buddy 말풍선 추가

검증 축은 다음과 같습니다.

- `latencyTotalMs`: 이미지 생성 또는 편집 완료 시간
- `output.format`, `output.width`, `output.height`, `output.bytes`: 결과 이미지 속성
- `generation.quality`, `generation.size`, `generation.outputFormat`, `generation.background`: 품질/크기/효율 조절 옵션
- `manualReview.checklist`: 액션별 수동 품질 평가 기준

모델별 비교는 `--models` 옵션으로 실행합니다.

```bash
node scripts/image-gen-eval.mjs \
  --cases eval/image-gen-cases/medium-article-translate-ko.json,eval/image-gen-cases/medium-article-image-change.json,eval/image-gen-cases/medium-article-speech-bubble.json \
  --models gpt-image-1,gpt-image-1.5,gpt-image-2 \
  --output-dir eval/results/image-gen-model-matrix
```

Streaming partial image 체감 테스트는 로컬 데모 서버로 실행합니다.

```bash
npm run eval:image-stream-demo
```

브라우저에서 `http://127.0.0.1:8767/eval/results/image-gen-model-matrix/stream-demo.html`을 열면 `stream: true`, `partial_images` 호출의 첫 이미지 도착 시간과 최종 완료 시간을 확인할 수 있습니다.

실제 핵심 3개 케이스 실행 결과 요약은 `docs/image-gen-eval-report.md`에 정리했습니다.

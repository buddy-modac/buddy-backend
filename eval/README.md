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

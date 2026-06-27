아래는 바로 복사해서 `docs/ai-eval-plan.md` 같은 파일로 넣기 좋은 형태로 정리한 문서입니다.

근거는 공식 문서 기준으로 다시 확인했습니다. OpenAI는 latency 최적화 원칙으로 “빠른 모델, 출력 토큰 감소, 입력 토큰 감소, 요청 수 감소, 병렬화, 사용자 대기 체감 감소, LLM 기본 사용 회피”를 제시하고 있고, Streaming은 SSE 기반으로 생성 중인 출력을 먼저 받을 수 있습니다.   OpenAI Prompt Caching은 반복 prefix를 재사용해 latency와 input token cost를 줄이며, static content를 앞에 두는 구조를 권장합니다.   OpenAI Vision은 `detail` 파라미터로 `low`, `high`, `original`, `auto` 수준을 지정할 수 있습니다.   Claude Vision 문서는 이미지 content block, 이미지-먼저-텍스트 구조, 이미지 한계/비용을 설명하지만 OpenAI `detail`에 해당하는 직접 파라미터는 확인되지 않아 resize/crop/downscale로 간접 제어하는 설계가 맞습니다.   Claude Prompt Caching은 `cache_control`과 cache breakpoint를 통해 반복 prefix 처리 시간과 비용을 줄입니다.  

# **AI 액션 병렬화 검증 지면 구축 계획**

## **1. 목적**

`buddy-backend`에 로컬 실행용 AI 평가 하네스를 추가한다.

이 하네스는 스크린샷 이미지와 OCR 텍스트를 입력으로 받아 다음 AI 액션을 검증한다.

- `translate`
- `describe`
- `ask`

검증 목적은 단순히 모델 응답 품질을 보는 것이 아니다.

핵심 목적은 다음과 같다.

1. 단일 요청 대비 병렬 요청이 실제로 빠른지 확인한다.
2. 병렬화가 품질 개선에 도움이 되는지 확인한다.
3. 병렬화로 인해 비용이 과도하게 증가하지 않는지 확인한다.
4. OpenAI와 Claude를 섞는 mixed-provider 전략이 실전적으로 유리한지 확인한다.
5. OCR 텍스트와 이미지 입력을 함께 사용할 때 어떤 입력 모드가 가장 효율적인지 확인한다.
6. 실제 제품 적용 시 latency, cost, quality, reliability를 함께 비교할 수 있는 기준을 만든다.

---

## **2. 기본 요약**

### **Summary**

`buddy-backend`에 로컬 실행용 AI 평가 하네스를 추가해, `screenshot image + ocrText` 입력으로 `translate`, `describe`, `ask` 액션을 검증한다.

비교 대상은 기본적으로 다음 3가지 전략으로 고정한다.

- `single`
- `parallel`
- `mixed-provider`

추가로 제품 적용 검증을 위해 다음 전략도 확장 후보로 둔다.

- `single-stream`
- `parallel-stream`
- `heuristic-first`
- `ocr-only`
- `vision-fallback`
- `ocr-redacted-image`
- `ocr-conflict-image`

결과는 다음 형태로 남긴다.

- 실행 시간
- 첫 결과 시간
- 첫 유용한 결과 시간
- provider/model별 latency
- 모델별 출력
- token usage
- 비용 추정
- partial success 여부
- 사람이 보기 쉬운 Markdown 리포트

---

## **3. Key Changes**

### **3.1 스크립트 추가**

`scripts/ai-eval.mjs`를 추가한다.

역할:

- `.env`에서 API key 로드
- 테스트 케이스 JSON 로드
- 이미지 파일 존재 여부 확인
- OpenAI / Claude API 직접 호출
- 전략별 실행
- 결과 JSON 저장
- Markdown 비교 리포트 생성

### **3.2 API Key 규칙**

`.env`에서 다음 값을 읽는다.

```env
CLAUDE_API_KEY=...
CODEX_API_KEY=...
OPENAI_API_KEY=...
```

규칙:

1. Claude 호출은 `CLAUDE_API_KEY` 사용
2. OpenAI 호출은 기본적으로 `CODEX_API_KEY` 사용
3. 단, `OPENAI_API_KEY`가 있으면 `OPENAI_API_KEY`를 우선 사용

```js
const openaiApiKey = process.env.OPENAI_API_KEY || process.env.CODEX_API_KEY;
const claudeApiKey = process.env.CLAUDE_API_KEY;
```

### **3.3 API 사용 방식**

- OpenAI: Responses API
- Claude: Messages API

### **3.4 테스트 케이스 위치**

```txt
eval/cases/*.json
```

필수 필드:

```json
{
  "id": "sample-ask",
  "action": "ask",
  "ocrText": "...",
  "imagePath": "./eval/assets/sample-error.png"
}
```

액션별 추가 필드:

```json
{
  "action": "ask",
  "question": "왜 나는 거야?"
}
```

```json
{
  "action": "translate",
  "targetLanguage": "ko"
}
```

`translate`의 `targetLanguage` 기본값은 `ko`로 둔다.

### **3.5 결과 위치**

```txt
eval/results/
```

생성 파일:

```txt
eval/results/{caseId}-{timestamp}.json
eval/results/{caseId}-{timestamp}.md
```

`eval/results/`는 `.gitignore`에 추가한다.

```gitignore
eval/results/
```

---

## **4. Evaluation Design**

## **4.1 기본 전략**

### **single**

선택된 액션을 모델 1개에 한 번 요청한다.

목적:

- 기준선
- 가장 단순한 latency/cost 확인
- 병렬화가 진짜 필요한지 비교

예시:

```txt
ask:
  OCR text + image + question -> model -> answer
```

---

### **parallel**

선택된 액션 내부 작업을 같은 provider/model로 병렬 실행한다.

각 subtask 결과를 모은 뒤, merge 요청을 한 번 더 보낸다.

#### **translate 병렬 subtask**

- `text_translation`
- `visual_context`
- `text_structure`

흐름:

```txt
OCR/image
 ├─ text_translation
 ├─ visual_context
 └─ text_structure
      ↓
    merge
      ↓
 final translation
```

#### **describe 병렬 subtask**

- `visual_summary`
- `ocr_summary`
- `screen_intent`
- `focus`

#### **ask 병렬 subtask**

- `question_intent`
- `text_evidence`
- `visual_evidence`
- `quick_answer`

---

### **mixed-provider**

빠르고 저렴한 작업은 OpenAI, 맥락 해석과 merge는 Claude로 나눠 실행한다.

기본값:

```txt
translation/text/structure:
  OpenAI mini급 모델

visual/context/merge:
  Claude Sonnet급 모델

ask merge:
  Claude 우선
```

예시:

```txt
ask:
  OpenAI:
    - question_intent
    - text_evidence
    - quick_answer

  Claude:
    - visual_evidence
    - merge
```

---

## **4.2 확장 전략**

### **single-stream**

단일 요청은 유지하되 최종 응답을 streaming으로 받는다.

목적:

- 전체 완료 시간은 같거나 비슷해도 사용자가 더 빨리 응답을 보기 시작할 수 있는지 확인한다.
- `latencyTotalMs`보다 `ttftMs`, `firstUsefulResultMs`를 중요하게 본다.

---

### **parallel-stream**

subtask는 병렬 실행하고, merge 응답만 streaming으로 사용자에게 보여준다.

권장 방식:

```txt
subtasks:
  non-stream JSON

merge:
  stream text
```

subtask까지 전부 stream으로 받을 필요는 낮다. 내부 판단용 subtask는 짧고 구조화된 JSON으로 받는 편이 낫다.

---

### **heuristic-first**

LLM 호출 전에 rule/heuristic으로 처리 가능한지 먼저 판단한다.

예시:

```txt
1. OCR text에서 에러 코드 탐지
2. exact match FAQ 확인
3. 단순 번역 가능 여부 확인
4. 이미지가 필요한지 판단
5. 필요할 때만 LLM 호출
```

목적:

- latency 절감
- 비용 절감
- 불필요한 LLM 호출 제거

---

### **ocr-only**

이미지를 보내지 않고 OCR 텍스트만 사용한다.

목적:

- 이미지 없이 충분히 답변 가능한지 확인
- 가장 저렴하고 빠른 기준선 확보
- 이미지 텍스트를 모델이 참고하지 않았음을 확실히 보장할 수 있는 입력 모드

---

### **vision-fallback**

기본은 OCR only로 처리하고, 부족한 경우에만 이미지를 추가한다.

예시:

```txt
1. OCR only로 답변 시도
2. confidence 낮음
3. image 포함하여 재요청
```

적합한 액션:

- `ask`
- `translate`

---

### **ocr-redacted-image**

OCR 텍스트와 함께 이미지를 보내되, 이미지 내 텍스트 영역을 blur/mask 처리한다.

목적:

- 모델이 이미지의 텍스트를 직접 읽지 못하게 한다.
- 레이아웃, 색상, 아이콘, 위치 정보만 사용하게 한다.
- OCR 텍스트와 시각적 맥락의 역할을 분리한다.

---

### **ocr-conflict-image**

OCR 텍스트와 이미지 안의 텍스트가 일부러 충돌하도록 만든다.

예시:

```txt
ocrText:
  Error: Network timeout

image:
  Error: Invalid API key
```

검증 포인트:

- 모델이 OCR을 우선하는지
- 이미지 텍스트를 직접 읽는지
- OCR과 이미지의 충돌을 감지하는지
- 조용히 한쪽을 선택해버리는지

---

## **5. OCR + Image 입력에 대한 판단**

## **5.1 질문**

OCR을 통해 텍스트를 뽑아서 모델에 제공하고, 이미지도 함께 보낸다.

프롬프트에 다음과 같이 작성한다.

```txt
OCR을 통해 텍스트를 뽑아서 주니까 이미지에 있는 텍스트는 따로 추출하거나 분석하지 않아도 돼.
```

이 경우 모델이 실제로 이미지 안의 텍스트를 참고하지 않을까?

## **5.2 결론**

보장할 수 없다.

모델은 지시를 따라 OCR 텍스트를 주된 근거로 삼으려 할 수는 있다.

하지만 이미지 입력을 받은 이상, 이미지 안의 텍스트, 레이아웃, 시각적 단서가 내부 추론에 영향을 줄 가능성이 있다.

따라서 “이미지 텍스트를 보지 마”라는 프롬프트만으로는 이미지 텍스트 미참고를 보장할 수 없다.

## **5.3 확실하게 분리하려면 입력을 바꿔야 한다**

### **확실한 기준선**

```txt
ocr-only
```

이미지를 아예 보내지 않는다.

### **현실적인 제품 검증**

```txt
ocr-redacted-image
```

이미지 안의 텍스트 영역을 가리고 보낸다.

### **최고 품질 후보**

```txt
ocr+image
```

OCR 텍스트와 원본 이미지를 함께 보낸다.

### **충돌 감지 검증**

```txt
ocr-conflict-image
```

OCR과 이미지 텍스트를 일부러 다르게 만든다.

---

## **6. OCR과 이미지 사용 정책**

프롬프트는 “이미지 텍스트를 절대 보지 마”보다 “근거 우선순위”를 명확히 하는 편이 낫다.

추천 프롬프트:

```txt
You are given OCR text and a screenshot.

Use OCR text as the authoritative source for all visible text.
Use the image only for non-textual visual context such as layout, grouping, icons, emphasis, colors, and relative positions.

Do not transcribe text from the image unless:
1. OCR text is missing,
2. OCR text is clearly corrupted,
3. OCR text conflicts with the visual context.

If you use text inferred from the image, explicitly mark it as image_inferred_text.
If OCR and image appear to conflict, report the conflict instead of silently choosing one.
```

핵심은 다음이다.

```txt
OCR = authoritative text source
Image = visual context source
Image text inference = 반드시 표시
Conflict = 조용히 선택하지 말고 리포트
```

---

## **7. OpenAI와 Claude의 이미지 분석 정도 제어**

## **7.1 OpenAI**

OpenAI API는 이미지 입력에 `detail` 파라미터를 제공한다.

사용 가능한 값:

```txt
low
high
original
auto
```

의미:

```txt
low:
  빠르고 저렴한 저해상도 분석

high:
  더 자세한 이미지 분석

original:
  원본에 가까운 고해상도 분석

auto:
  모델/입력에 따라 자동 결정
```

따라서 OpenAI 쪽은 `imageFidelity`를 `detail`에 직접 매핑할 수 있다.

```ts
function mapOpenAIImageDetail(fidelity: ImageFidelity) {
  if (fidelity === "low") return "low";
  if (fidelity === "standard") return "high";
  if (fidelity === "high") return "high";
  if (fidelity === "original") return "original";
  return undefined;
}
```

---

## **7.2 Claude**

Claude API에서는 OpenAI의 `detail`과 같은 직접적인 이미지 분석 정도 파라미터는 확인되지 않는다.

따라서 Claude는 다음 방식으로 간접 제어한다.

1. 이미지 resize
2. 이미지 crop
3. 이미지 downscale
4. 이미지 compression
5. 텍스트 영역 redaction
6. 모델 선택
7. 프롬프트로 이미지 사용 범위 제한

Claude 쪽에서는 `imageFidelity`를 전처리 정책으로 매핑한다.

```ts
function mapClaudeImagePreprocess(fidelity: ImageFidelity) {
  switch (fidelity) {
    case "none":
      return { sendImage: false };

    case "low":
      return {
        sendImage: true,
        maxLongEdge: 768,
        quality: 70
      };

    case "standard":
      return {
        sendImage: true,
        maxLongEdge: 1568,
        quality: 80
      };

    case "high":
      return {
        sendImage: true,
        maxLongEdge: 2576,
        quality: 90
      };

    case "original":
      return {
        sendImage: true,
        maxLongEdge: 8000,
        quality: 95
      };
  }
}
```

---

## **7.3 공통 추상화**

OpenAI와 Claude를 같은 인터페이스로 감싸려면 `detail`이라는 이름보다 `imageFidelity`가 낫다.

```ts
type ImageFidelity =
  | "none"
  | "low"
  | "standard"
  | "high"
  | "original";

type ImageTextPolicy =
  | "ignore"
  | "ocr_authoritative"
  | "allow_image_text"
  | "detect_conflict";

type CropMode =
  | "none"
  | "text_regions_masked"
  | "focused_region";

type VisionInputPolicy = {
  imageFidelity: ImageFidelity;
  useOcrText: boolean;
  imageTextPolicy: ImageTextPolicy;
  cropMode?: CropMode;
};
```

Provider별 처리:

```txt
OpenAI:
  imageFidelity -> detail parameter

Claude:
  imageFidelity -> image preprocessing
```

---

## **8. 액션별 권장 입력 정책**

## **8.1 translate**

기본 정책:

```txt
ocr-only 우선
```

이유:

- 번역은 대부분 OCR 텍스트만으로 충분하다.
- 이미지를 함께 보내면 비용과 latency가 증가한다.
- 화면 맥락이 필요한 경우에만 이미지를 추가한다.

추천 흐름:

```txt
1. OCR text만으로 번역
2. UI 구조 보존이 필요한지 판단
3. 필요하면 low/standard image 추가
```

추천 input mode:

```txt
ocr-only
ocr+low-image
ocr+redacted-image
```

---

## **8.2 describe**

기본 정책:

```txt
ocrText + standard image
```

이유:

- 화면 설명은 텍스트뿐 아니라 레이아웃, 시각적 위계, 버튼 위치, 강조 영역이 중요하다.
- OCR only로는 화면 목적과 사용 흐름을 놓칠 수 있다.

추천 input mode:

```txt
ocr+image
ocr+redacted-image
```

---

## **8.3 ask**

기본 정책:

```txt
ocr-only -> vision fallback
```

이유:

- 질문이 에러 메시지 기반이면 OCR only로 충분할 수 있다.
- 화면 맥락이 필요한 경우에만 이미지를 추가하는 편이 비용/속도에 유리하다.

추천 흐름:

```txt
1. OCR text + question으로 빠른 답변 시도
2. confidence 낮거나 근거 부족하면 image 추가
3. OCR과 image가 충돌하면 conflict로 리포트
```

추천 input mode:

```txt
ocr-only
ocr+image
ocr-conflict-image
```

---

## **9. Metrics**

## **9.1 기본 metric**

```json
{
  "latencyTotalMs": 0,
  "latencyFirstResultMs": 0,
  "providerLatencyMs": {},
  "inputTokens": 0,
  "outputTokens": 0,
  "estimatedCostUsd": 0,
  "qualityNotes": "",
  "winner": null
}
```

## **9.2 추가 권장 metric**

```json
{
  "latency": {
    "totalMs": 0,
    "firstResultMs": 0,
    "firstUsefulResultMs": 0,
    "ttftMs": null,
    "mergeStartMs": 0,
    "mergeMs": 0,
    "slowestSubtaskMs": 0
  }
}
```

각 필드 의미:

|**필드**|**의미**|
|---|---|
|`totalMs`|최종 결과까지 걸린 시간|
|`firstResultMs`|첫 subtask 완료까지 걸린 시간|
|`firstUsefulResultMs`|사용자에게 보여줄 수 있는 첫 결과까지 걸린 시간|
|`ttftMs`|첫 token 도착 시간|
|`mergeStartMs`|merge 요청 시작 시점|
|`mergeMs`|merge 요청만 걸린 시간|
|`slowestSubtaskMs`|가장 늦게 끝난 subtask 시간|

---

## **10. Token / Cost / Cache 기록**

## **10.1 Token usage**

```json
{
  "tokens": {
    "inputTokens": 0,
    "outputTokens": 0,
    "cachedInputTokens": 0,
    "cacheReadTokens": 0,
    "cacheWriteTokens": 0
  }
}
```

## **10.2 Cost**

```json
{
  "cost": {
    "estimatedCostUsd": 0,
    "estimatedCostKrw": 0,
    "priceTableVersion": "2026-06-27"
  }
}
```

## **10.3 Prompt caching**

Prompt caching 효과를 보기 위해 다음 값을 남긴다.

```json
{
  "cache": {
    "cacheEligible": true,
    "promptCacheKey": "ai-eval-v1-ask",
    "cachedInputTokens": 0,
    "cacheHit": false
  }
}
```

프롬프트 구조는 static prefix가 앞에 오도록 구성한다.

```txt
[static system prompt]
[static action policy]
[static output schema]
[static examples]
---
[case-specific action]
[case-specific ocrText]
[case-specific image]
[case-specific question]
```

---

## **11. Reliability / Error Handling**

병렬화에서는 일부 subtask 실패가 전체 실패로 이어지지 않게 해야 한다.

상태값:

```txt
success
partial_success
failed_provider_error
failed_rate_limited
failed_timeout
failed_invalid_case
failed_safety_or_refusal
```

예시:

```json
{
  "status": "partial_success",
  "failedSubtasks": [
    {
      "name": "visual_evidence",
      "provider": "claude",
      "model": "claude-sonnet",
      "errorType": "timeout",
      "retryable": true
    }
  ]
}
```

CLI 옵션:

```bash
--timeout-ms 30000
--retry 2
--retry-backoff exponential
--fail-fast false
```

Provider별 concurrency도 분리한다.

```js
const providerConcurrency = {
  openai: 4,
  claude: 2
};
```

---

## **12. Rate Limit / Concurrency Control**

병렬화 검증 시 반드시 rate limit과 concurrency를 고려해야 한다.

로컬 단일 케이스에서는 병렬화가 빨라 보여도, 실제 트래픽에서는 provider rate limit 때문에 전체 latency가 오히려 증가할 수 있다.

권장 CLI 옵션:

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --strategies single,parallel,mixed-provider \
  --concurrency 4 \
  --timeout-ms 30000 \
  --retry 2
```

권장 정책:

```txt
1. Provider별 concurrency limit을 둔다.
2. 429 / rate limit 발생 시 exponential backoff 적용
3. timeout된 subtask는 partial_success로 처리
4. merge에는 성공한 subtask만 전달
5. 실패한 subtask 목록을 리포트에 남긴다.
```

---

## **13. Structured Output**

subtask 응답은 자유 텍스트보다 JSON으로 받는 것이 좋다.

예시:

```json
{
  "summary": "",
  "evidence": [],
  "confidence": 0.0,
  "needsVision": false,
  "risk": "low"
}
```

장점:

- merge prompt가 짧아진다.
- partial success 처리가 쉬워진다.
- 품질 평가 자동화가 쉬워진다.
- Markdown 리포트 생성이 안정적이다.
- hallucination 여부를 비교하기 쉽다.

---

## **14. Evidence Source 기록**

OCR과 이미지 입력을 함께 쓸 경우, 답변 근거의 출처를 명시해야 한다.

추천 결과 구조:

```json
{
  "answer": "",
  "evidence": [
    {
      "text": "Error: Invalid API key",
      "source": "ocrText"
    },
    {
      "text": "red error banner at top",
      "source": "image_visual"
    }
  ],
  "imageTextUsed": false,
  "imageInferredText": [],
  "ocrImageConflict": false,
  "confidence": 0.82
}
```

OCR과 이미지 텍스트가 충돌한 경우:

```json
{
  "ocrImageConflict": true,
  "conflict": {
    "ocrText": "Network timeout",
    "imageInferredText": "Invalid API key"
  },
  "answer": "OCR과 이미지의 에러 메시지가 달라 원인을 단정할 수 없습니다."
}
```

---

## **15. Image Input 기록**

이미지 입력 최적화를 검증하려면 원본 이미지와 실제 전송 이미지 정보를 남겨야 한다.

```json
{
  "imageInput": {
    "provider": "claude",
    "fidelity": "low",
    "originalWidth": 3024,
    "originalHeight": 1964,
    "sentWidth": 768,
    "sentHeight": 499,
    "originalBytes": 1245332,
    "sentBytes": 124332,
    "cropped": false,
    "redacted": false
  }
}
```

추가 실험 input mode:

```txt
ocr-only
image-only
ocr+image
ocr+redacted-image
ocr+cropped-image
ocr+downscaled-image
ocr-conflict-image
```

---

## **16. Quality Evaluation**

사람이 직접 평가할 수 있도록 `qualityNotes`와 `winner` 필드를 둔다.

```json
{
  "quality": {
    "correctness": null,
    "completeness": null,
    "groundedness": null,
    "conciseness": null,
    "actionability": null,
    "humanNotes": "",
    "winner": null
  }
}
```

### **16.1 translate rubric**

|**항목**|**설명**|
|---|---|
|의미 보존|원문 의미가 유지되었는가|
|UI 용어 자연스러움|버튼/메뉴/라벨 번역이 자연스러운가|
|누락 없음|OCR 텍스트가 빠지지 않았는가|
|과번역 없음|불필요한 해석이 들어가지 않았는가|
|구조 보존|줄바꿈/목록/화면 구조가 유지되었는가|

### **16.2 describe rubric**

|**항목**|**설명**|
|---|---|
|화면 목적 파악|어떤 화면인지 정확히 설명했는가|
|핵심 UI 요소|중요한 버튼/메뉴/상태를 언급했는가|
|OCR 반영|텍스트 정보를 적절히 반영했는가|
|시각적 맥락|레이아웃/강조/상태를 잘 설명했는가|
|추측 통제|불확실한 내용을 단정하지 않았는가|

### **16.3 ask rubric**

|**항목**|**설명**|
|---|---|
|직접 답변|질문에 바로 답했는가|
|근거성|OCR/이미지 근거를 명확히 사용했는가|
|실용성|다음 행동이 실제로 도움이 되는가|
|불확실성|모르는 부분을 적절히 표시했는가|
|간결성|불필요하게 길지 않은가|

---

## **17. CLI 설계**

## **17.1 기본 실행**

```bash
node scripts/ai-eval.mjs --case eval/cases/sample-ask.json
```

## **17.2 전략 지정**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --strategies single,parallel,mixed-provider
```

## **17.3 모델 지정**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --openai-model gpt-5.4-mini \
  --claude-model claude-sonnet-4-6
```

## **17.4 dry run**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --dry-run
```

## **17.5 입력 모드 지정**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --input-modes ocr-only,ocr-image,ocr-redacted-image,ocr-conflict-image
```

## **17.6 이미지 fidelity 지정**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --image-fidelity none,low,standard,high
```

## **17.7 streaming 검증**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --strategies single-stream,parallel-stream
```

## **17.8 concurrency / timeout / retry**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --concurrency 4 \
  --timeout-ms 30000 \
  --retry 2
```

---

## **18. 샘플 케이스**

## **18.1 sample-translate.json**

```json
{
  "id": "sample-translate",
  "action": "translate",
  "targetLanguage": "ko",
  "ocrText": "Settings\nAccount\nBilling\nCancel subscription",
  "imagePath": "./eval/assets/sample-translate.png"
}
```

## **18.2 sample-describe.json**

```json
{
  "id": "sample-describe",
  "action": "describe",
  "ocrText": "Dashboard\nTotal Revenue\nActive Users\nConversion Rate",
  "imagePath": "./eval/assets/sample-dashboard.png"
}
```

## **18.3 sample-ask.json**

```json
{
  "id": "sample-ask",
  "action": "ask",
  "question": "왜 나는 거야?",
  "ocrText": "Error: Invalid API key\nRequest failed with status code 401",
  "imagePath": "./eval/assets/sample-error.png"
}
```

---

## **19. 결과 JSON 예시**

```json
{
  "caseId": "sample-ask",
  "action": "ask",
  "strategy": "mixed-provider",
  "inputMode": "ocr-image",
  "status": "success",
  "models": [
    {
      "provider": "openai",
      "model": "gpt-5.4-mini",
      "tasks": ["question_intent", "text_evidence", "quick_answer"]
    },
    {
      "provider": "claude",
      "model": "claude-sonnet-4-6",
      "tasks": ["visual_evidence", "merge"]
    }
  ],
  "latency": {
    "totalMs": 4210,
    "firstResultMs": 880,
    "firstUsefulResultMs": 1800,
    "ttftMs": null,
    "mergeStartMs": 2200,
    "mergeMs": 2010,
    "slowestSubtaskMs": 2120
  },
  "tokens": {
    "inputTokens": 3200,
    "outputTokens": 780,
    "cachedInputTokens": 0
  },
  "cost": {
    "estimatedCostUsd": 0.0123,
    "estimatedCostKrw": 17.1,
    "priceTableVersion": "2026-06-27"
  },
  "imageInput": {
    "fidelity": "standard",
    "originalWidth": 3024,
    "originalHeight": 1964,
    "sentWidth": 1568,
    "sentHeight": 1018,
    "originalBytes": 1245332,
    "sentBytes": 312421
  },
  "result": {
    "answer": "401 Invalid API key 오류라서 API key가 없거나 잘못 설정된 상태로 보입니다.",
    "evidence": [
      {
        "text": "Error: Invalid API key",
        "source": "ocrText"
      },
      {
        "text": "Request failed with status code 401",
        "source": "ocrText"
      }
    ],
    "imageTextUsed": false,
    "imageInferredText": [],
    "ocrImageConflict": false,
    "confidence": 0.91
  },
  "quality": {
    "correctness": null,
    "completeness": null,
    "groundedness": null,
    "conciseness": null,
    "actionability": null,
    "humanNotes": "",
    "winner": null
  }
}
```

---

## **20. Markdown 리포트 예시**

```md
# AI Eval Report: sample-ask

## Case

- Action: ask
- Question: 왜 나는 거야?
- Input mode: ocr-image
- Image: ./eval/assets/sample-error.png

## Summary

| Strategy | Status | Total | First Result | Cost | Winner |
|---|---:|---:|---:|---:|---|
| single | success | 5200ms | 5200ms | $0.0081 |  |
| parallel | partial_success | 3900ms | 900ms | $0.0184 |  |
| mixed-provider | success | 4210ms | 880ms | $0.0123 |  |

## Outputs

### single

...

### parallel

...

### mixed-provider

...

## Notes

### Quality Notes

- single:
- parallel:
- mixed-provider:

### Winner

- [ ] single
- [ ] parallel
- [ ] mixed-provider
```

---

## **21. Test Plan**

## **21.1 dry-run**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --dry-run
```

확인 항목:

- `.env` 존재 여부
- `CLAUDE_API_KEY` 존재 여부
- `OPENAI_API_KEY` 또는 `CODEX_API_KEY` 존재 여부
- case JSON parse 가능 여부
- 필수 필드 존재 여부
- imagePath 파일 존재 여부
- action별 필수 필드 존재 여부
- model price table 존재 여부
- results directory 생성 가능 여부

---

## **21.2 샘플 케이스 3개 준비**

```txt
sample-translate.json:
  영어 UI/문서 화면 번역

sample-describe.json:
  앱 또는 웹 화면 설명

sample-ask.json:
  에러 화면에 대해 “왜 나는 거야?” 질문
```

---

## **21.3 기본 전략 실행**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --strategies single,parallel,mixed-provider
```

성공 기준:

```txt
1. 모든 전략이 같은 입력 포맷으로 실행된다.
2. 결과 JSON이 생성된다.
3. Markdown 리포트가 생성된다.
4. latencyTotalMs가 기록된다.
5. provider/model별 latency가 기록된다.
6. usage가 제공되는 경우 input/output token이 기록된다.
7. 실패한 subtask가 있어도 전체 실행은 partial_success로 리포트된다.
```

---

## **21.4 입력 모드 검증**

```bash
node scripts/ai-eval.mjs \
  --case eval/cases/sample-ask.json \
  --input-modes ocr-only,image-only,ocr-image,ocr-redacted-image,ocr-conflict-image
```

성공 기준:

```txt
1. ocr-only에서는 이미지가 전송되지 않는다.
2. image-only에서는 OCR 텍스트가 전송되지 않는다.
3. ocr-redacted-image에서는 텍스트 영역이 가려진 이미지가 전송된다.
4. ocr-conflict-image에서는 OCR과 이미지 텍스트 충돌이 감지되는지 확인한다.
5. 결과에 imageTextUsed, imageInferredText, ocrImageConflict가 기록된다.
```

---

## **22. 제품 적용 관점의 핵심 판단**

## **22.1 병렬화가 항상 좋은 것은 아니다**

병렬화는 요청 수를 늘린다.

```txt
single:
  1 request

parallel:
  N subtask requests + 1 merge request

mixed-provider:
  OpenAI N requests + Claude merge request
```

따라서 다음을 함께 봐야 한다.

- latency가 실제로 줄었는가
- firstUsefulResult가 빨라졌는가
- 비용이 얼마나 증가했는가
- 품질이 좋아졌는가
- merge가 병목이 되었는가
- 실패율이 높아졌는가

---

## **22.2 액션별 예상**

|**Action**|**병렬화 적합도**|**이유**|
|---|---|---|
|translate|낮음~중간|OCR text만으로 충분한 경우가 많음|
|describe|중간~높음|시각/텍스트/의도 분리가 의미 있음|
|ask|높음|질문 의도, 텍스트 근거, 시각 근거 분리가 품질에 도움 가능|

---

## **22.3 추천 기본 정책**

```txt
translate:
  ocr-only 우선
  필요 시 image fallback

describe:
  ocr + standard image 기본

ask:
  ocr-only 우선
  confidence 낮으면 image 추가
  OCR/image 충돌 시 conflict 표시
```

---

## **23. 최종 설계 방향**

최종 하네스 흐름은 다음과 같이 잡는다.

```txt
1. dry-run
   - env 확인
   - case schema 확인
   - image 존재/크기 확인
   - model price table 확인

2. preprocess
   - OCR text normalize
   - image metadata 기록
   - optional crop/downscale/redaction

3. route
   - action 확인
   - difficulty 판단
   - ocr-only 가능 여부 판단
   - model/provider 선택

4. execute strategy
   - single
   - parallel
   - mixed-provider
   - heuristic-first
   - stream 여부

5. collect metrics
   - total latency
   - first result latency
   - first useful result latency
   - TTFT
   - provider latency
   - token/cost/cache
   - failures/retries

6. generate artifacts
   - raw JSON
   - Markdown comparison
   - optional aggregate summary
```

---

## **24. 구현 우선순위**

### **Phase 1: 최소 동작**

- `scripts/ai-eval.mjs`
- `.env` 로드
- case JSON 로드
- imagePath 검증
- single 전략
- 결과 JSON 저장
- Markdown 리포트 생성

### **Phase 2: 병렬화**

- parallel 전략
- subtask 정의
- merge 요청
- partial_success 처리
- providerLatency 기록

### **Phase 3: mixed-provider**

- OpenAI / Claude provider abstraction
- model option
- provider별 cost 추정
- provider별 concurrency 제한

### **Phase 4: 입력 모드**

- ocr-only
- image-only
- ocr-image
- ocr-redacted-image
- ocr-conflict-image

### **Phase 5: 제품화 검증**

- streaming
- prompt caching
- heuristic-first
- vision fallback
- aggregate report
- quality rubric
- batch benchmark 후보

---

## **25. 최종 체크리스트**

|**항목**|**우선순위**|
|---|---|
|single/parallel/mixed-provider|높음|
|latencyTotalMs|높음|
|latencyFirstResultMs|높음|
|firstUsefulResultMs|높음|
|TTFT|높음|
|providerLatencyMs|높음|
|token/cost 기록|높음|
|partial_success|높음|
|OCR/image conflict detection|높음|
|ocr-only 기준선|높음|
|redacted image 검증|높음|
|prompt caching|높음|
|streaming|높음|
|rate limit/retry/timeout|높음|
|heuristic-first|높음|
|image fidelity abstraction|중간~높음|
|batch benchmark|중간|
|predicted output|낮음~중간|

---

## **26. 핵심 결론**

이 검증 지면은 단순히 “AI 요청을 병렬화하면 빨라지는가?”를 확인하는 도구가 아니다.

더 정확한 목적은 다음이다.

```txt
액션별로
- 어떤 입력이 필요한지
- 어떤 모델이 충분한지
- 병렬화가 유리한지
- 이미지가 꼭 필요한지
- OCR만으로 충분한지
- 비용 대비 품질이 좋은지
- 제품에서 사용자 체감 속도가 개선되는지
를 확인하는 로컬 평가 하네스
```

가장 중요한 설계 원칙은 다음이다.

```txt
1. translate는 ocr-only 우선
2. describe는 ocr + image 기본
3. ask는 ocr-only 후 vision fallback
4. OCR은 authoritative text source로 둔다
5. 이미지를 보낸 이상 이미지 텍스트 미참고는 보장할 수 없다
6. 이미지 텍스트 미참고를 검증하려면 redaction 또는 ocr-only가 필요하다
7. OpenAI는 detail 파라미터로 이미지 분석 정도를 제어한다
8. Claude는 detail 파라미터 대신 이미지 전처리로 제어한다
9. 병렬화는 latency뿐 아니라 cost, quality, reliability까지 함께 봐야 한다
10. 제품 적용에서는 streaming, prompt caching, heuristic-first, rate limit 처리가 필수다
```
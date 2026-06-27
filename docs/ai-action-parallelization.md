# AI 액션별 병렬 요청 설계

## 목적

사용자가 스크린샷을 찍어 AI 액션을 요청할 때, 클라이언트는 항상 OCR 처리된 텍스트와 원본 이미지를 함께 전달한다고 가정한다.

이 문서는 사용자가 선택할 수 있는 세 가지 액션을 기준으로, 각 액션 내부에서 AI 요청 과정을 어떻게 병렬로 쪼개고 종합할 수 있는지 정리한다.

## 전제

사용자는 아래 세 액션 중 하나만 선택한다.

1. 번역하기
2. 이미지 설명하기
3. 이미지에 대해 질문하기

즉, 세 액션이 한 번에 모두 실행되는 구조가 아니다. 병렬화 대상은 액션 간 실행이 아니라, 선택된 액션 하나를 처리하는 내부 AI 요청 과정이다.

공통 입력은 다음과 같다.

```json
{
  "action": "translate | describe | ask",
  "image": "base64 또는 image url",
  "ocrText": "스크린샷에서 추출된 텍스트",
  "question": "ask 액션에서만 사용",
  "targetLanguage": "translate 액션에서 사용"
}
```

## 전체 실행 모델

```text
Client
  -> screenshot capture
  -> OCR
  -> POST /ai/action

Backend
  -> preprocess
  -> action별 병렬 AI 요청 실행
  -> merge AI 요청으로 종합
  -> response
```

기본 비교 대상은 다음 두 가지다.

```text
baseline
  - 선택된 액션을 AI 요청 1번으로 처리

parallel
  - 선택된 액션 내부를 3~4개 AI 요청으로 병렬 처리
  - 마지막 merge 요청 1번으로 결과 종합
```

## 공통 전처리

AI 요청 전에 서버에서 처리할 수 있는 가벼운 작업이다.

```text
preprocess
  - OCR 텍스트 공백, 줄바꿈 정리
  - 이미지 리사이즈 또는 압축
  - 너무 긴 OCR 텍스트 chunk 분리
  - action 값 검증
  - request_id 생성
```

이 단계는 AI에게 맡기지 않고 코드로 처리하는 편이 빠르고 안정적이다.

## 1. 번역하기

### 목표

OCR 텍스트를 번역하되, 이미지 문맥을 반영해 UI 문구, 에러 메시지, 문서 내용 등을 자연스럽게 보정한다.

### 입력

```json
{
  "action": "translate",
  "image": "...",
  "ocrText": "...",
  "targetLanguage": "ko"
}
```

### 병렬 작업

```text
text_translation_task
  - OCR 텍스트를 기본 번역
  - 원문에 없는 내용은 추가하지 않음
  - 빠른 초안 번역 담당

visual_context_task
  - 이미지가 어떤 화면인지 분석
  - 웹페이지, 앱 UI, 에러 화면, 문서, 채팅, 코드 등 분류
  - 번역에 영향을 줄 맥락 추출

text_structure_task
  - OCR 텍스트를 제목, 본문, 버튼, 메뉴, 표, 에러 메시지 등으로 구조화
  - 짧게 번역해야 하는 UI 문구와 자연스럽게 풀어야 하는 문장 구분
```

### 종합 작업

```text
translation_merge_task
  - text_translation_task의 번역을 기본값으로 사용
  - visual_context_task의 화면 맥락을 반영
  - text_structure_task의 구조 정보를 반영
  - UI 문구는 짧게, 문서/채팅은 자연스럽게, 에러 메시지는 기술적으로 정확하게 정리
```

### 실행 구조

```text
text_translation_task ┐
visual_context_task   ├─ translation_merge_task
text_structure_task   ┘
```

### 출력 예시

```json
{
  "action": "translate",
  "bubbleText": "화면의 주요 문구를 한국어로 번역했어요.",
  "result": {
    "translatedText": "...",
    "detectedLanguage": "en",
    "importantTerms": ["..."],
    "notes": ["UI 버튼 문구는 짧게 다듬었습니다."]
  }
}
```

### 병렬화 적합도

번역은 단순 OCR 번역만 필요하다면 단일 요청이 더 빠를 수 있다. 다만 UI, 에러, 문서 맥락 보정까지 포함하면 `번역 초안`, `화면 맥락`, `텍스트 구조화`를 병렬로 나누는 실험 가치가 있다.

## 2. 이미지 설명하기

### 목표

스크린샷에 무엇이 보이는지, 어떤 상황인지, 사용자가 주목해야 할 부분이 무엇인지 설명한다.

### 입력

```json
{
  "action": "describe",
  "image": "...",
  "ocrText": "..."
}
```

### 병렬 작업

```text
visual_summary_task
  - 이미지에서 보이는 객체, UI 구성, 레이아웃, 상태 설명
  - OCR 텍스트에 의존하지 않고 시각 정보 중심으로 분석

ocr_summary_task
  - OCR 텍스트 중 중요한 내용 요약
  - 제목, 경고, 숫자, 버튼, 핵심 문장 추출

screen_intent_task
  - 화면의 목적 또는 종류 추정
  - 로그인, 결제, 에러, 설정, 결과 화면 등으로 분류

focus_task
  - 사용자가 주목해야 할 부분 추출
  - 오류, 경고, 중요한 버튼, 입력 필요 영역 등 식별
```

### 종합 작업

```text
description_merge_task
  - visual_summary_task의 시각 설명과 ocr_summary_task의 텍스트 요약을 결합
  - screen_intent_task로 화면 목적을 정리
  - focus_task로 중요 포인트를 강조
  - 사용자가 바로 이해할 수 있도록 짧은 설명과 상세 설명을 분리
```

### 실행 구조

```text
visual_summary_task ┐
ocr_summary_task    ├─ description_merge_task
screen_intent_task  │
focus_task          ┘
```

### 출력 예시

```json
{
  "action": "describe",
  "bubbleText": "이 화면은 로그인 오류가 발생한 상황으로 보여요.",
  "result": {
    "screenType": "error_screen",
    "summary": "...",
    "keyVisuals": ["..."],
    "keyTexts": ["..."],
    "focusPoints": ["..."]
  }
}
```

### 병렬화 적합도

이미지 설명은 병렬화에 비교적 잘 맞는다. 시각 정보, OCR 요약, 화면 목적, 중요 포인트가 서로 독립적으로 분석 가능하고, 마지막에 합치기 쉽다.

## 3. 이미지에 대해 질문하기

### 목표

사용자가 스크린샷에 대해 던진 구체적인 질문에 답한다. 이미지와 OCR 텍스트를 모두 근거로 사용한다.

### 입력

```json
{
  "action": "ask",
  "image": "...",
  "ocrText": "...",
  "question": "이 에러는 왜 나는 거야?"
}
```

### 병렬 작업

```text
question_intent_task
  - 사용자가 정확히 무엇을 묻는지 분석
  - 의미 질문, 원인 질문, 해결 질문, 위치 질문, 비교 질문 등으로 분류

text_evidence_task
  - OCR 텍스트에서 질문과 관련된 근거 추출
  - 에러 메시지, 숫자, 버튼명, 문장 등 답변에 쓸 수 있는 텍스트 식별

visual_evidence_task
  - 이미지에서 질문과 관련된 시각 근거 추출
  - 버튼 위치, 색상, UI 상태, 표시된 객체, 선택 상태 등 확인

quick_answer_task
  - 전체 입력을 보고 빠른 답변 초안 생성
  - 확신도와 추정 여부를 함께 반환
```

### 종합 작업

```text
answer_merge_task
  - question_intent_task로 질문 의도를 확정
  - text_evidence_task와 visual_evidence_task로 quick_answer_task의 답변을 검증
  - 근거가 부족하면 부족하다고 명시
  - 최종 답변, 근거, 추가 질문을 생성
```

### 실행 구조

```text
question_intent_task ┐
text_evidence_task   ├─ answer_merge_task
visual_evidence_task │
quick_answer_task    ┘
```

### 출력 예시

```json
{
  "action": "ask",
  "bubbleText": "OCR에 보이는 에러 메시지 기준으로는 인증 정보가 맞지 않는 상황 같아요.",
  "result": {
    "answer": "...",
    "evidence": {
      "text": ["..."],
      "visual": ["..."]
    },
    "confidence": "medium",
    "needsMoreInfo": false,
    "followUpQuestion": null
  }
}
```

### 병렬화 적합도

질문 답변은 세 액션 중 병렬화 실험 가치가 가장 높다. 질문 의도 분석, 텍스트 근거 추출, 시각 근거 추출, 빠른 답변 초안 생성이 분리 가능하고, 마지막 merge 단계에서 답변 품질을 보정할 수 있다.

## 실패 처리

병렬 요청은 하나가 실패하더라도 전체 요청이 실패하지 않도록 처리한다.

```text
Promise.allSettled 또는 asyncio.gather(return_exceptions=True)
```

예시:

```json
{
  "action": "describe",
  "status": "partial_success",
  "results": {
    "visualSummary": { "status": "done", "value": "..." },
    "ocrSummary": { "status": "done", "value": "..." },
    "screenIntent": { "status": "failed", "error": "timeout" }
  }
}
```

## 응답 UX

최종 완료만 기다리는 방식보다, 작업별 결과를 먼저 보여주는 방식이 체감 속도에 유리하다.

```text
0.0s 요청 시작
0.5s OCR 텍스트 기반 빠른 결과 표시
1.5s 이미지 분석 결과 표시
2.5s 최종 merge 결과 표시
```

구현 방식은 두 가지가 가능하다.

```text
단순 MVP
  - 최종 response 한 번만 반환

개선 버전
  - request_id 즉시 반환
  - polling 또는 SSE로 partial result 전달
```

## 실험 지표

병렬화가 실제로 유효한지 확인하기 위해 다음 값을 기록한다.

```text
latency_total
  - 최종 응답 완료까지 걸린 시간

latency_first_result
  - 사용자에게 첫 결과를 보여주기까지 걸린 시간

cost_total
  - AI 요청 전체 비용

quality_score
  - 사람이 평가한 응답 품질

failure_rate
  - timeout, provider error 등 실패율
```

## 추천 실험 순서

```text
1순위: ask
  - 병렬화 가치가 가장 높음
  - intent, text evidence, visual evidence, quick answer로 나누기 쉬움

2순위: describe
  - visual, OCR, screen intent, focus 분석을 나누기 좋음

3순위: translate
  - 단순 번역은 단일 요청이 더 빠를 수 있음
  - 맥락 보정이 필요한 경우에 병렬화 실험 가치 있음
```

## 요약

이 설계에서 중요한 점은 세 액션을 동시에 실행하지 않는 것이다.

사용자는 `translate`, `describe`, `ask` 중 하나만 선택한다. 서버는 선택된 액션에 맞는 내부 작업 DAG를 실행하고, 병렬로 얻은 결과를 merge 단계에서 종합한다.

```text
사용자 액션 선택
  -> 선택된 액션의 내부 작업을 병렬 실행
  -> merge
  -> Buddy 말풍선과 상세 결과로 표시
```

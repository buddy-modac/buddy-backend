"""서버측 OCR — 프론트가 텍스트를 못 뽑을 때 서버가 이미지에서 직접 추출.

`/analyze` 는 ocr_text 가 비어 있고 server_ocr=true 일 때만 이 함수를 호출합니다.
구현: Anthropic 비전 모델로 "이미지의 텍스트만" 추출(설명/번역 없이) → 그 결과가 다시
ocr_text 로서 페르소나 스타일링(번역/설명) 단계로 들어갑니다.

전송은 서버의 다른 곳과 동일하게 httpx 직접 호출(=`anthropic` SDK 의존성 없음).
⚠️ OCR 은 비전이라 **ANTHROPIC_API_KEY 가 필요**합니다 (구독 claude CLI 는 비전 불가).
원본 아이디어: 사용자가 준 claude_vision.py (파일경로→base64) → 서버용(base64 직접)으로 개조.
"""
from __future__ import annotations
import os
import base64
import httpx

from .ai_backend import MODEL          # 같은 모델 id 재사용

MAX_IMAGE_BYTES = 5 * 1024 * 1024      # 5MB (Anthropic 권장 한도)
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}
# 텍스트만 verbatim 으로. 설명/번역/포맷 추가 금지 → 순수 OCR 결과를 ocr_text 로 사용.
OCR_PROMPT = (
    "Extract ALL text visible in this image, verbatim and complete — every line, "
    "number, and label, in reading order. Output ONLY the extracted text. Do NOT "
    "translate, explain, summarise, or add any commentary or formatting. If there "
    "is no readable text, output an empty string."
)


class OCRNotConfigured(RuntimeError):
    """server_ocr 요청됐지만 OCR을 실행할 수 없음 (예: API 키 없음)."""


def extract_text_from_image(image_b64: str, media_type: str = "image/jpeg") -> str:
    """이미지(base64)에서 텍스트를 추출해 반환. 비전 API(키 필요) 사용."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise OCRNotConfigured(
            "서버 OCR 에는 ANTHROPIC_API_KEY 가 필요합니다 (비전 호출). "
            "프론트에서 ocr_text 를 보내거나, 키를 설정하세요."
        )
    if media_type not in SUPPORTED_MIME:
        raise ValueError(f"지원하지 않는 이미지 형식: {media_type} (지원: {sorted(SUPPORTED_MIME)})")

    # base64 검증 + 크기 제한 (디코딩된 원본 기준)
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except Exception as e:
        raise ValueError(f"image_b64 디코딩 실패: {e}") from None
    if not raw:
        raise ValueError("빈 이미지")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"이미지가 너무 큽니다: {len(raw)/1024/1024:.1f}MB (최대 5MB)")

    payload = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": image_b64}},
                {"type": "text", "text": OCR_PROMPT},
            ],
        }],
    }
    with httpx.Client(timeout=60) as c:
        r = c.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()
    return "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()

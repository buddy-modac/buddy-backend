"""Pluggable AI backend — 같은 Phase 2 시스템 프롬프트(스타일+가드레일)를 쓰고 전송만 다름.
  • SubscriptionBackend — claude -p (구독, 키 불필요). 텍스트 기반(이미지는 비전모델 안 감).
  • APIVisionBackend     — Anthropic Messages API + base64 이미지(진짜 비전). ANTHROPIC_API_KEY 필요.
  • OpenAIBackend        — OpenAI Chat Completions + base64 이미지(비전). OPENAI_API_KEY 필요.
선택: SERVER_AI_BACKEND = "subscription"(기본) | "api"(anthropic) | "openai".

v1/v2 공용: interpret/stream_interpret 가 model·max_tokens·include_image·detail 오버라이드를 받음.
  v1 = 기본값(default·2000·이미지O).  v2 = v2_params()로 fast·캡·이미지정책·detail.
모델은 백엔드별로 매핑(model_for): 'haiku' 같은 fast 신호는 각 프로바이더의 fast 모델로 변환.
"""
import os
from typing import Optional, Protocol

from personaforge import (build_assistant_system_prompt, ModelClient, Cache,
                          ClaudeCLIBackend)
from personaforge.model import Message

MODEL = os.environ.get("SERVER_MODEL", "claude-sonnet-4-6")   # v1 기본 모델(Anthropic)
HAIKU = os.environ.get("SERVER_MODEL_FAST", "claude-haiku-4-5-20251001")  # v2 빠른 모델(Anthropic)
# OpenAI: 5.4 mini 단일 모델 사용 (v1·v2 동일). 정확한 API id가 다르면 env로 교정.
OPENAI_MODEL = os.environ.get("SERVER_OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_FAST = os.environ.get("SERVER_OPENAI_MODEL_FAST", OPENAI_MODEL)
CACHE_PATH = os.path.join(os.path.dirname(__file__), "server_cache.db")

# v2 정책: mode×detail → 출력 토큰 캡(바닥값) / 이미지 포함 여부.
# 캡은 입력(OCR) 길이에 비례해 동적으로 키운다 — 긴 텍스트(약관 등) 번역이 잘리지 않게.
_V2_CAPS = {("translate", "brief"): 400, ("translate", "full"): 800,
            ("explain", "brief"): 500, ("explain", "full"): 1200}
_V2_CAP_MAX = 4000   # 폭주 방지 상한


def v2_caps(mode: str, detail: str, ocr_len: int = 0) -> int:
    """OCR 길이 비례 동적 캡. translate는 출력≈입력이라 강하게, explain은 약하게 비례."""
    base = _V2_CAPS.get((mode, detail), 600)
    if mode == "translate":
        need = int(ocr_len * 2.2) + 80      # 번역: 출력 길이가 입력에 비례
    else:
        need = int(ocr_len * 1.0) + 120     # 설명: 요약이라 약하게 비례
    return min(_V2_CAP_MAX, max(base, need))


def v2_params(mode: str, detail: str, ocr_len: int = 0) -> dict:
    """v2 최적화 노브: Haiku, 동적 캡, translate는 이미지 생략(빠름)."""
    return {"model": HAIKU,
            "max_tokens": v2_caps(mode, detail, ocr_len),
            "include_image": (mode == "explain"),   # translate=텍스트만, explain=비전
            "detail": detail}


PLAIN_MARKER = "[[PLAIN]]"   # 능동 제안 신호(구조화) — 서버가 떼어 suggest_plain 으로 변환


def _system_prompt(persona: str, styled: bool = True) -> str:
    # styled=False → 기본 모드. styled=True면 끝에 구조화 SELF-CHECK(마커) 부착:
    # 스타일이 정확성/유용성을 해칠 것 같으면 답 맨 앞에 [[PLAIN]] 한 줄 → 서버가 떼고 suggest_plain=true.
    base = build_assistant_system_prompt(persona, language="Korean", amplify=True,
                                         include_style=styled, self_check=False)
    if styled:
        base += ("\n\n[SELF-CHECK] 만약 당신의 MBTI 소통 스타일이 이 답에서 '무엇을 말하는지'(정확성·"
                 "완전성·유용성)를 바꾸거나 덜 직접적으로 만들 것 같으면, 답의 **맨 첫 줄에 정확히 "
                 f"{PLAIN_MARKER} 만** 출력하고 줄바꿈 뒤 평소대로 답하라. 그렇지 않으면 그 줄을 넣지 마라. "
                 "이 마커는 사용자에게 보이지 않는 내부 신호다(설명·인사 금지, 마커만).")
    return base


_DETAIL_TIP = {
    "brief": "\n\n간결하게: 핵심만, 표·대안·부연 없이 1~3줄로.",
    "full":  "\n\n충분히 자세하게: 필요하면 짧은 목록/예시를 포함해 풀어서.",
}


def _user_message(mode, ocr_text, parent_context, has_image, user_text="", detail=None):
    task = ("아래 텍스트를 자연스러운 한국어로 번역" if mode == "translate"
            else "아래 이미지와 텍스트의 의미를 설명")
    img_note = "" if has_image else "(이미지 원본은 없고, 추출된 텍스트만 제공됩니다.)\n"
    msg = f"{parent_context}{img_note}요청: {task}해 주세요.\n\n[추출된 텍스트]\n{ocr_text}"
    if user_text and user_text.strip():
        msg += f"\n\n[사용자 추가 요청]\n{user_text.strip()}"
    if detail in _DETAIL_TIP:
        msg += _DETAIL_TIP[detail]
    return msg


class AIBackend(Protocol):
    name: str
    def interpret(self, persona: str, mode: str, ocr_text: str,
                  image_b64: Optional[str], media_type: str, parent_context: str,
                  user_text: str = "", model: Optional[str] = None,
                  max_tokens: int = 2000, include_image: bool = True,
                  detail: Optional[str] = None) -> str: ...
    def model_for(self, requested: Optional[str]) -> str: ...   # DB 기록용 실제 모델 id


class SubscriptionBackend:
    """구독(claude -p). 텍스트 기반(이미지 비전 불가). model 오버라이드로 v2 Haiku 가능."""
    name = "subscription-text"

    def __init__(self):
        self._client = ModelClient(model=MODEL, cache=Cache(CACHE_PATH),
                                   backend=ClaudeCLIBackend())

    def model_for(self, requested):
        return requested or MODEL

    def interpret(self, persona, mode, ocr_text, image_b64, media_type, parent_context,
                  user_text="", model=None, max_tokens=2000, include_image=True, detail=None,
                  styled=True):
        system = _system_prompt(persona, styled)
        user = _user_message(mode, ocr_text, parent_context, has_image=False,
                             user_text=user_text, detail=detail)   # 구독은 항상 텍스트만
        return self._client.complete(system, [Message("user", user)],
                                     max_tokens=max_tokens, model=model)

    def stream_interpret(self, persona, mode, ocr_text, image_b64, media_type,
                         parent_context, user_text="", model=None, max_tokens=2000,
                         include_image=True, detail=None, styled=True):
        yield self.interpret(persona, mode, ocr_text, image_b64, media_type,
                             parent_context, user_text, model, max_tokens, include_image, detail, styled)


class APIVisionBackend:
    """Anthropic API + base64 이미지(진짜 비전)."""
    name = "api-vision"

    def __init__(self, api_key: str):
        self._key = api_key

    def model_for(self, requested):
        return requested or MODEL

    def _payload(self, persona, mode, ocr_text, image_b64, media_type, parent_context,
                 user_text, model, max_tokens, include_image, detail, stream, styled=True):
        send_img = include_image and bool(image_b64)
        user = _user_message(mode, ocr_text, parent_context, has_image=send_img,
                             user_text=user_text, detail=detail)
        content = []
        if send_img:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": media_type, "data": image_b64}})
        content.append({"type": "text", "text": user})
        p = {"model": model or MODEL, "max_tokens": max_tokens,
             "system": _system_prompt(persona, styled),
             "messages": [{"role": "user", "content": content}]}
        if stream:
            p["stream"] = True
        return p

    def interpret(self, persona, mode, ocr_text, image_b64, media_type, parent_context,
                  user_text="", model=None, max_tokens=2000, include_image=True, detail=None,
                  styled=True):
        import httpx
        p = self._payload(persona, mode, ocr_text, image_b64, media_type, parent_context,
                          user_text, model, max_tokens, include_image, detail, stream=False, styled=styled)
        with httpx.Client(timeout=60) as c:
            r = c.post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": self._key, "anthropic-version": "2023-06-01",
                                "content-type": "application/json"}, json=p)
            r.raise_for_status()
            return "".join(b["text"] for b in r.json()["content"] if b["type"] == "text")

    def stream_interpret(self, persona, mode, ocr_text, image_b64, media_type,
                         parent_context, user_text="", model=None, max_tokens=2000,
                         include_image=True, detail=None, styled=True):
        import json as _json
        import httpx
        p = self._payload(persona, mode, ocr_text, image_b64, media_type, parent_context,
                          user_text, model, max_tokens, include_image, detail, stream=True, styled=styled)
        with httpx.Client(timeout=120) as c:
            with c.stream("POST", "https://api.anthropic.com/v1/messages",
                          headers={"x-api-key": self._key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"}, json=p) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    try:
                        ev = _json.loads(line[6:])
                    except Exception:
                        continue
                    if ev.get("type") == "content_block_delta":
                        t = ev.get("delta", {}).get("text", "")
                        if t:
                            yield t


class OpenAIBackend:
    """OpenAI Chat Completions + base64 이미지(비전). 같은 Phase 2 시스템 프롬프트 사용.
    모델 매핑: v1(model=None)→OPENAI_MODEL, v2(fast 신호 'haiku')→OPENAI_FAST,
    명시적 OpenAI id('gpt'/'o…')는 그대로."""
    name = "openai"

    def __init__(self, api_key: str):
        self._key = api_key

    def model_for(self, requested):
        if not requested:
            return OPENAI_MODEL                      # v1/기본
        r = requested.lower()
        if r.startswith("gpt") or r.startswith("o"):
            return requested                         # 명시적 OpenAI 모델
        if "haiku" in r or "fast" in r:
            return OPENAI_FAST                       # v2 fast 신호 → OpenAI fast
        return OPENAI_MODEL                          # 그 외(다른 프로바이더 id)는 기본으로

    def _payload(self, persona, mode, ocr_text, image_b64, media_type, parent_context,
                 user_text, model, max_tokens, include_image, detail, stream, styled=True):
        send_img = include_image and bool(image_b64)
        user = _user_message(mode, ocr_text, parent_context, has_image=send_img,
                             user_text=user_text, detail=detail)
        content = [{"type": "text", "text": user}]
        if send_img:
            content.append({"type": "image_url", "image_url": {
                "url": f"data:{media_type};base64,{image_b64}"}})
        mdl = self.model_for(model)
        # gpt-5 계열·o-시리즈는 max_completion_tokens, 그 외(gpt-4o 등)는 max_tokens
        ml = mdl.lower()
        tok_key = "max_completion_tokens" if (ml.startswith("gpt-5") or ml.startswith("o")) else "max_tokens"
        p = {"model": mdl, tok_key: max_tokens,
             "messages": [{"role": "system", "content": _system_prompt(persona, styled)},
                          {"role": "user", "content": content}]}
        if stream:
            p["stream"] = True
        return p

    def _headers(self):
        return {"Authorization": f"Bearer {self._key}", "content-type": "application/json"}

    def interpret(self, persona, mode, ocr_text, image_b64, media_type, parent_context,
                  user_text="", model=None, max_tokens=2000, include_image=True, detail=None,
                  styled=True):
        import httpx
        p = self._payload(persona, mode, ocr_text, image_b64, media_type, parent_context,
                          user_text, model, max_tokens, include_image, detail, stream=False, styled=styled)
        with httpx.Client(timeout=60) as c:
            r = c.post("https://api.openai.com/v1/chat/completions", headers=self._headers(), json=p)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    def stream_interpret(self, persona, mode, ocr_text, image_b64, media_type,
                         parent_context, user_text="", model=None, max_tokens=2000,
                         include_image=True, detail=None, styled=True):
        import json as _json
        import httpx
        p = self._payload(persona, mode, ocr_text, image_b64, media_type, parent_context,
                          user_text, model, max_tokens, include_image, detail, stream=True, styled=styled)
        with httpx.Client(timeout=120) as c:
            with c.stream("POST", "https://api.openai.com/v1/chat/completions",
                          headers=self._headers(), json=p) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        ev = _json.loads(data)
                        t = ev["choices"][0]["delta"].get("content", "")
                    except Exception:
                        continue
                    if t:
                        yield t


def text_complete(system: str, user: str, max_tokens: int = 700):
    """텍스트 전용 완성(요약 등, 이미지 없음). 가용 키로 가벼운 모델 사용.
    우선순위: Anthropic Haiku → OpenAI mini → 구독(claude -p). (text, model) 반환."""
    import httpx
    ak = os.environ.get("ANTHROPIC_API_KEY", "")
    ok = os.environ.get("OPENAI_API_KEY", "")
    if ak:
        r = httpx.post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": ak, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json={"model": HAIKU, "max_tokens": max_tokens, "system": system,
                             "messages": [{"role": "user", "content": user}]}, timeout=60)
        r.raise_for_status()
        return "".join(b["text"] for b in r.json()["content"] if b["type"] == "text"), HAIKU
    if ok:
        r = httpx.post("https://api.openai.com/v1/chat/completions",
                       headers={"Authorization": f"Bearer {ok}", "content-type": "application/json"},
                       json={"model": OPENAI_MODEL, "max_completion_tokens": max_tokens,
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                       timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], OPENAI_MODEL
    sub = SubscriptionBackend()
    return sub._client.complete(system, [Message("user", user)], max_tokens=max_tokens), MODEL


_backend: Optional[AIBackend] = None
_named: dict = {}


def get_backend_for(choice: str) -> AIBackend:
    """프로바이더 명시 선택(요청별 비교용). 'api'/'anthropic' | 'openai' | 'subscription'.
    빈 값/알 수 없으면 기본(get_backend). 인스턴스는 캐시."""
    c = (choice or "").lower()
    if not c:
        return get_backend()
    if c in _named:
        return _named[c]
    if c in ("api", "anthropic"):
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("provider=anthropic 인데 ANTHROPIC_API_KEY가 없습니다.")
        be = APIVisionBackend(key)
    elif c == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("provider=openai 인데 OPENAI_API_KEY가 없습니다.")
        be = OpenAIBackend(key)
    elif c == "subscription":
        be = SubscriptionBackend()
    else:
        return get_backend()
    _named[c] = be
    return be


def pick_backend(persona: str) -> AIBackend:
    """SERVER_AI_BACKEND=auto 일 때 페르소나로 모델 라우팅(벤치 근거):
      • F형(감정형) → Claude(Haiku): 페르소나 재현 우위(특히 ENFP/ENFJ)
      • T형(사고형) → GPT mini: 페르소나 동급/근소, 속도 우위
    두 키 모두 필요. auto 가 아니면 기본 단일 백엔드(get_backend)."""
    if os.environ.get("SERVER_AI_BACKEND", "subscription").lower() != "auto":
        return get_backend()
    is_feeling = len(persona) >= 3 and persona[2].upper() == "F"
    return get_backend_for("anthropic" if is_feeling else "openai")


def get_backend() -> AIBackend:
    global _backend
    if _backend is None:
        choice = os.environ.get("SERVER_AI_BACKEND", "subscription").lower()
        if choice == "auto":              # auto는 요청별 라우팅 → 기본 단일은 anthropic로(두 키 필요)
            choice = "api"
        if choice == "api":
            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise RuntimeError("SERVER_AI_BACKEND=api 인데 ANTHROPIC_API_KEY가 없습니다.")
            _backend = APIVisionBackend(key)
        elif choice == "openai":
            key = os.environ.get("OPENAI_API_KEY", "")
            if not key:
                raise RuntimeError("SERVER_AI_BACKEND=openai 인데 OPENAI_API_KEY가 없습니다.")
            _backend = OpenAIBackend(key)
        else:
            _backend = SubscriptionBackend()
    return _backend

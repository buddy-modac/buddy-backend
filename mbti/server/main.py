"""AI Image Assistant — FastAPI 서버.

프론트가 보낸 닉네임/페르소나(MBTI)/mode/추출텍스트/이미지를 받아, **Phase 2** 프롬프트로
AI에 보내 해석하고, 요청+결과를 SQLite에 저장한 뒤 결과를 돌려준다.

문서 대비 바뀐 점: 단순 MBTI_DESC+build_prompt+Anthropic-API 직접호출 →
`ai_backend.get_backend()`(pluggable: 구독 기본 / API 비전 옵션) + Phase 2 시스템 프롬프트.

실행:  uvicorn server.main:app --reload   (repo 루트에서, .venv 활성화 상태)
"""
import os
import json
import time
import uuid
import ipaddress
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from pydantic import BaseModel


# 관리/파괴적 엔드포인트는 기본적으로 이 호스트(localhost)에서만 — LAN 노출 차단.
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _parse_allow_nets(env_val: str):
    """SERVER_ADMIN_ALLOW_IPS 를 IP/CIDR 목록으로 파싱. 잘못된 토큰은 무시."""
    nets = []
    for tok in (env_val or "").replace(" ", "").split(","):
        if not tok:
            continue
        try:
            nets.append(ipaddress.ip_network(tok, strict=False))
        except ValueError:
            pass
    return nets


# 추가 허용 IP (예: 내 PC LAN IP). 콤마 구분, 단일 IP·CIDR 모두 가능.
#   server/.env.local 또는 환경변수:  SERVER_ADMIN_ALLOW_IPS=192.168.0.50,10.0.0.0/24
_ADMIN_ALLOW_NETS = _parse_allow_nets(os.environ.get("SERVER_ADMIN_ALLOW_IPS", ""))


def _admin_ip_allowed(host: str) -> bool:
    if host in _LOOPBACK:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(ip in net for net in _ADMIN_ALLOW_NETS)


def require_localhost(request: Request):
    host = request.client.host if request.client else ""
    if not _admin_ip_allowed(host):
        raise HTTPException(403, "이 엔드포인트는 localhost 또는 허용된 IP에서만 접근 가능합니다. "
                                 f"현재 접속 IP: {host or '알수없음'} — 서버에서 환경변수 "
                                 f"SERVER_ADMIN_ALLOW_IPS={host} 로 허용할 수 있습니다.")

from .personas import MBTI_DESC, VALID_PERSONAS, VALID_MODES
from .ai_backend import (get_backend, get_backend_for, pick_backend, v2_params,
                         text_complete, PLAIN_MARKER, MODEL as DEFAULT_MODEL)
from .ocr import extract_text_from_image, OCRNotConfigured
from .quiz import build_router as build_quiz_router, init_quiz_db
from .clipboard import build_router as build_clipboard_router, init_clipboard_db

DB = os.path.join(os.path.dirname(__file__), "app.db")

app = FastAPI(title="AI Image Assistant API")

# 공개 클립보드/갤러리는 교차 출처 프런트에서 호출될 수 있음 → CORS 허용.
# (allow_credentials 는 기본 False 유지 — "*" 와 credentials 동시 사용 불가)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ---------- DB ----------
@contextmanager
def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            parent_id INTEGER,
            nickname TEXT NOT NULL,
            persona TEXT NOT NULL,
            mode TEXT NOT NULL,
            text TEXT,                 -- 이미지에서 인식된 텍스트(OCR). 출처는 ocr_source
            ocr_source TEXT,           -- 'client' | 'server' | '' (OCR 텍스트가 어디서 왔나)
            user_text TEXT,            -- 유저가 직접 입력한 추가 요청(선택)
            image_b64 TEXT,
            media_type TEXT,
            result TEXT,
            client_ip TEXT,            -- 요청을 보낸 클라이언트 IP (X-Forwarded-For 우선)
            api_version INTEGER,       -- 1 | 2 (어느 엔드포인트로 왔나)
            detail TEXT,               -- v2: 'brief' | 'full' (v1은 NULL)
            styled INTEGER,            -- 1=MBTI 스타일 | 0=기본 모드(담백)
            ms_ocr INTEGER,            -- 서버 OCR 소요(ms). 클라이언트 OCR이면 0
            ms_llm INTEGER,            -- AI 생성(LLM) 소요(ms) — 대부분의 시간
            ms_total INTEGER,          -- 요청 전체 소요(ms)
            model TEXT,                -- 답 생성에 쓴 LLM 모델 id (지금은 Anthropic, 추후 gemini/openai)
            created_at TEXT NOT NULL,
            FOREIGN KEY(parent_id) REFERENCES requests(id)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_nickname ON requests(nickname)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_conv ON requests(conversation_id)")
        # 일별 요약 캐시 (nickname × KST 날짜). source_count로 staleness 판단 → 새 질의 생기면 재생성
        c.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            nickname TEXT NOT NULL,
            date TEXT NOT NULL,            -- KST YYYY-MM-DD
            summary TEXT NOT NULL,         -- 구조화 JSON 문자열
            source_count INTEGER NOT NULL, -- 요약에 포함된 요청 수
            model TEXT, created_at TEXT NOT NULL,
            PRIMARY KEY(nickname, date)
        )""")
        # 기존 DB 마이그레이션 (없는 컬럼만 추가)
        cols = {r[1] for r in c.execute("PRAGMA table_info(requests)")}
        for col in ("ocr_source", "user_text", "client_ip", "detail", "model"):
            if col not in cols:
                c.execute(f"ALTER TABLE requests ADD COLUMN {col} TEXT")
        for col in ("api_version", "ms_ocr", "ms_llm", "ms_total", "styled"):
            if col not in cols:
                c.execute(f"ALTER TABLE requests ADD COLUMN {col} INTEGER")


init_db()
init_quiz_db(db)
app.include_router(build_quiz_router(db))
init_clipboard_db(db)
app.include_router(build_clipboard_router(db))


# ---------- 모델 ----------
class AnalyzeRequest(BaseModel):
    nickname: str
    persona: str
    mode: str                                  # translate | explain
    image_b64: str
    media_type: str = "image/jpeg"
    # --- 텍스트 입력 (3종) ---
    ocr_text: Optional[str] = None             # 프론트가 이미지에서 뽑은 텍스트
    text: Optional[str] = None                 # (구버전 호환) ocr_text 의 옛 이름
    server_ocr: bool = False                   # true/ocr_text 비면 → 서버가 이미지 OCR
    user_text: Optional[str] = None            # 유저가 직접 친 추가 요청(선택; 없으면 mode대로)
    detail: str = "brief"                       # v2 전용: brief(기본·빠름) | full(길게). v1은 무시
    styled: bool = True                         # true=MBTI 스타일 적용(기본) | false=기본 모드(담백, 스타일 없음)
    provider: Optional[str] = None              # 요청별 백엔드 강제(비교용): anthropic|openai|subscription. 없으면 서버 기본
    # --- 대화 ---
    conversation_id: Optional[str] = None
    parent_id: Optional[int] = None


# ---------- POST /analyze (v1) · /v2/analyze (속도최적: Haiku·mode×detail·이미지정책) ----------
# 동기 def: 구독 백엔드는 subprocess(claude -p)라 FastAPI 스레드풀에서 돈다.
# ?debug=1 이면 단계별 소요시간(trace) 포함. v1/v2 공용 구현, 백엔드 호출 노브만 다름.
def _client_ip(request: Request) -> str:
    """요청 클라이언트 IP. 프록시 뒤면 X-Forwarded-For의 첫 IP, 아니면 소켓 peer."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff.strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


@app.post("/analyze")
def analyze(req: AnalyzeRequest, request: Request, debug: bool = False):
    return _analyze_impl(req, debug, v2=False, client_ip=_client_ip(request))


@app.post("/v2/analyze")
def analyze_v2(req: AnalyzeRequest, request: Request, debug: bool = False):
    return _analyze_impl(req, debug, v2=True, client_ip=_client_ip(request))


def _analyze_impl(req: AnalyzeRequest, debug: bool, v2: bool, client_ip: str = ""):
    def ms(a, b): return round((b - a) * 1000, 1)
    t0 = time.perf_counter()

    if req.persona not in VALID_PERSONAS:
        raise HTTPException(400, f"알 수 없는 persona: {req.persona}")
    if req.mode not in VALID_MODES:
        raise HTTPException(400, f"mode는 {VALID_MODES} 중 하나여야 함")
    if not (req.image_b64 or "").strip():
        raise HTTPException(400, "이미지가 필요합니다 (image_b64).")

    # OCR 텍스트 해석: 프론트가 준 ocr_text(또는 구버전 text) 우선,
    # 비어 있고 server_ocr=true 면 서버가 이미지에서 추출.
    ocr_text = (req.ocr_text or req.text or "").strip()
    ocr_source = "client" if ocr_text else ""
    ms_ocr = 0
    if not ocr_text and req.server_ocr:
        try:
            _o0 = time.perf_counter()
            ocr_text = extract_text_from_image(req.image_b64, req.media_type).strip()
            ms_ocr = round((time.perf_counter() - _o0) * 1000)
            ocr_source = "server"
        except OCRNotConfigured as e:
            raise HTTPException(501, str(e))          # 키 없음 등 설정 문제
        except ValueError as e:
            raise HTTPException(400, f"이미지 OCR 불가: {e}")   # 잘못된/큰 이미지
        except Exception as e:
            raise HTTPException(502, f"서버 OCR 호출 실패: {e}")
        if not ocr_text:
            raise HTTPException(422, "서버 OCR 결과가 비어 있습니다(이미지에서 텍스트를 찾지 못함).")
    if not ocr_text:
        raise HTTPException(400, "ocr_text(또는 text)가 없습니다. 텍스트를 보내거나 server_ocr=true 로 요청하세요.")
    t_valid = time.perf_counter()

    conv_id = req.conversation_id or str(uuid.uuid4())

    # reply 맥락: parent의 text/result를 프롬프트에 끼워 넣는다.
    parent_context = ""
    if req.parent_id is not None:
        with db() as c:
            row = c.execute(
                "SELECT text, result FROM requests WHERE id=?", (req.parent_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, f"parent_id {req.parent_id} 없음")
        parent_context = (
            f"[이전 대화]\n요청: {row['text']}\n답변: {row['result']}\n"
            f"위 맥락을 참고해서 답해 주세요.\n\n"
        )
    t_parent = time.perf_counter()

    backend = get_backend_for(req.provider) if req.provider else pick_backend(req.persona)
    eff_detail = "brief" if req.mode == "translate" else req.detail   # translate는 항상 brief
    extra = v2_params(req.mode, eff_detail, len(ocr_text)) if v2 else {}
    try:
        result = backend.interpret(
            persona=req.persona, mode=req.mode, ocr_text=ocr_text,
            image_b64=req.image_b64, media_type=req.media_type,
            parent_context=parent_context, user_text=req.user_text or "",
            styled=req.styled, **extra,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"AI 호출 실패: {e}")
    # 능동 제안 마커 떼기 → suggest_plain (마커는 항상 제거해 누수 방지; 제안은 styled에서만 의미)
    suggest_plain = False
    if result.lstrip().startswith(PLAIN_MARKER):
        suggest_plain = req.styled
        result = result.lstrip()[len(PLAIN_MARKER):].lstrip("\n :·-")
    t_llm = time.perf_counter()

    ms_llm = round((t_llm - t_valid) * 1000)
    ms_total = round((time.perf_counter() - t0) * 1000)
    model_used = backend.model_for(extra.get("model"))   # 백엔드별 실제 모델
    now = datetime.utcnow().isoformat()
    with db() as c:
        cur = c.execute(
            """INSERT INTO requests
            (conversation_id, parent_id, nickname, persona, mode,
             text, ocr_source, user_text, image_b64, media_type, result,
             client_ip, api_version, detail, styled, ms_ocr, ms_llm, ms_total, model, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (conv_id, req.parent_id, req.nickname, req.persona, req.mode,
             ocr_text, ocr_source, req.user_text, req.image_b64, req.media_type, result,
             client_ip, 2 if v2 else 1, eff_detail if v2 else None, 1 if req.styled else 0,
             ms_ocr, ms_llm, ms_total, model_used, now),
        )
        rid = cur.lastrowid
    t_store = time.perf_counter()

    resp = {
        "id": rid,
        "conversation_id": conv_id,
        "parent_id": req.parent_id,
        "result": result,
        "ocr_source": ocr_source,          # 'client' | 'server' — OCR 텍스트 출처
        "version": 2 if v2 else 1,
        "detail": eff_detail if v2 else None,
        "styled": req.styled,              # 이 답이 스타일 적용본인지(false=기본 모드)
        "suggest_plain": suggest_plain,    # 모델이 '기본 모드 권장' 신호를 낸 경우 true
        "ms_ocr": ms_ocr, "ms_llm": ms_llm, "ms_total": ms_total, "model": model_used,
        "created_at": now,
    }
    if debug:
        resp["trace"] = {
            "backend": backend.name,
            "had_parent": req.parent_id is not None,
            "ocr_source": ocr_source,
            "steps": [
                {"name": "① persona/mode 검증 + OCR 해석", "ms": ms(t0, t_valid)},
                {"name": "② parent 맥락 조회(DB)", "ms": ms(t_valid, t_parent)},
                {"name": "③ 🤖 LLM 호출 (Anthropic/구독)", "ms": ms(t_parent, t_llm)},
                {"name": "④ SQLite 저장", "ms": ms(t_llm, t_store)},
            ],
            "total_ms": ms(t0, t_store),
        }
    return resp


# ---------- POST /analyze/stream (SSE 실시간) ----------
# 단계(stage)·토큰(token)·완료(done)·오류(error) 이벤트를 흘려보냄 → 콘솔이 실시간 렌더.
def _sse(obj) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/analyze/stream")
def analyze_stream(req: AnalyzeRequest, request: Request):
    return _stream_impl(req, v2=False, client_ip=_client_ip(request))


@app.post("/v2/analyze/stream")
def analyze_stream_v2(req: AnalyzeRequest, request: Request):
    return _stream_impl(req, v2=True, client_ip=_client_ip(request))


def _stream_impl(req: AnalyzeRequest, v2: bool, client_ip: str = ""):
    # 사전 검증(여기서만 HTTP 에러; 스트림 시작 후엔 error 이벤트로)
    if req.persona not in VALID_PERSONAS:
        raise HTTPException(400, f"알 수 없는 persona: {req.persona}")
    if req.mode not in VALID_MODES:
        raise HTTPException(400, f"mode는 {VALID_MODES} 중 하나여야 함")
    if not (req.image_b64 or "").strip():
        raise HTTPException(400, "이미지가 필요합니다 (image_b64).")
    ocr_text0 = (req.ocr_text or req.text or "").strip()
    if not ocr_text0 and not req.server_ocr:
        raise HTTPException(400, "ocr_text(또는 text)가 없습니다. server_ocr=true 로 요청하세요.")
    conv_id = req.conversation_id or str(uuid.uuid4())
    parent_context = ""
    if req.parent_id is not None:
        with db() as c:
            row = c.execute("SELECT text, result FROM requests WHERE id=?",
                            (req.parent_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"parent_id {req.parent_id} 없음")
        parent_context = (f"[이전 대화]\n요청: {row['text']}\n답변: {row['result']}\n"
                          f"위 맥락을 참고해서 답해 주세요.\n\n")
    backend = get_backend_for(req.provider) if req.provider else pick_backend(req.persona)
    eff_detail = "brief" if req.mode == "translate" else req.detail   # translate는 항상 brief

    def gen():
        t0 = time.perf_counter()
        el = lambda: round((time.perf_counter() - t0) * 1000, 1)   # 누적 경과 ms
        try:
            # 각 '완료' stage 에 누적 ms 를 실어 보냄 → 콘솔이 구간별 막대(소요시간) 그림.
            ms_ocr = 0
            yield _sse({"type": "stage", "name": "① 검증", "done": True, "ms": el()})
            ocr_text, ocr_source = ocr_text0, ("client" if ocr_text0 else "")
            if not ocr_text and req.server_ocr:
                yield _sse({"type": "stage", "name": "② 서버 이미지 OCR 중…"})
                _o0 = time.perf_counter()
                ocr_text = extract_text_from_image(req.image_b64, req.media_type).strip()
                ms_ocr = round((time.perf_counter() - _o0) * 1000)
                ocr_source = "server"
                if not ocr_text:
                    yield _sse({"type": "error", "detail": "OCR 결과가 비어 있습니다."}); return
                yield _sse({"type": "stage", "name": "② 서버 OCR", "done": True, "ms": el()})
            extra = v2_params(req.mode, eff_detail, len(ocr_text)) if v2 else {}
            yield _sse({"type": "stage", "name": "③ 🤖 AI 생성 중…",
                        "backend": backend.name, "version": 2 if v2 else 1})
            parts = []
            _l0 = time.perf_counter()
            # 마커([[PLAIN]]) 선두 감지를 위해 첫 부분만 잠깐 버퍼링 후 토큰 방출
            head_buf, head_done, suggest_plain = "", False, False
            for chunk in backend.stream_interpret(
                    persona=req.persona, mode=req.mode, ocr_text=ocr_text,
                    image_b64=req.image_b64, media_type=req.media_type,
                    parent_context=parent_context, user_text=req.user_text or "",
                    styled=req.styled, **extra):
                if not head_done:
                    head_buf += chunk
                    if len(head_buf.lstrip()) < len(PLAIN_MARKER) and "\n" not in head_buf:
                        continue                       # 아직 판단 불가 → 더 버퍼
                    head_done = True
                    if head_buf.lstrip().startswith(PLAIN_MARKER):     # 마커 항상 제거
                        suggest_plain = req.styled
                        head_buf = head_buf.lstrip()[len(PLAIN_MARKER):].lstrip("\n :·-")
                        if suggest_plain:
                            yield _sse({"type": "suggest_plain"})   # 프런트: 토글 강조
                    if head_buf:
                        parts.append(head_buf); yield _sse({"type": "token", "text": head_buf})
                    continue
                parts.append(chunk)
                yield _sse({"type": "token", "text": chunk})
            if not head_done and head_buf:             # 아주 짧은 답(버퍼만으로 끝)
                if head_buf.lstrip().startswith(PLAIN_MARKER):
                    suggest_plain = req.styled
                    head_buf = head_buf.lstrip()[len(PLAIN_MARKER):].lstrip("\n :·-")
                    if suggest_plain:
                        yield _sse({"type": "suggest_plain"})
                parts.append(head_buf); yield _sse({"type": "token", "text": head_buf})
            ms_llm = round((time.perf_counter() - _l0) * 1000)
            result = "".join(parts)
            yield _sse({"type": "stage", "name": "③ 🤖 AI 생성", "done": True, "ms": el(), "llm": True})
            now = datetime.utcnow().isoformat()
            with db() as c:
                ms_total = round((time.perf_counter() - t0) * 1000)
                model_used = backend.model_for(extra.get("model"))
                cur = c.execute(
                    """INSERT INTO requests
                    (conversation_id, parent_id, nickname, persona, mode,
                     text, ocr_source, user_text, image_b64, media_type, result,
                     client_ip, api_version, detail, styled, ms_ocr, ms_llm, ms_total, model, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (conv_id, req.parent_id, req.nickname, req.persona, req.mode,
                     ocr_text, ocr_source, req.user_text, req.image_b64, req.media_type, result,
                     client_ip, 2 if v2 else 1, eff_detail if v2 else None, 1 if req.styled else 0,
                     ms_ocr, ms_llm, ms_total, model_used, now))
                rid = cur.lastrowid
            yield _sse({"type": "stage", "name": "④ 저장", "done": True, "ms": el()})
            yield _sse({"type": "done", "id": rid, "conversation_id": conv_id,
                        "parent_id": req.parent_id, "ocr_source": ocr_source, "styled": req.styled,
                        "suggest_plain": suggest_plain,
                        "ms_ocr": ms_ocr, "ms_llm": ms_llm, "ms_total": el(),
                        "created_at": now, "total_ms": el()})
        except OCRNotConfigured as e:
            yield _sse({"type": "error", "detail": str(e)})
        except Exception as e:
            yield _sse({"type": "error", "detail": f"AI 호출 실패: {e}"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# ---------- GET /messages (전체 목록 — 관리/조회용, localhost 전용) ----------
@app.get("/messages", dependencies=[Depends(require_localhost)])
def all_messages(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    nickname: Optional[str] = None,
    mode: Optional[str] = None,
    persona: Optional[str] = None,
    version: Optional[int] = None,          # api_version 1|2
    model: Optional[str] = None,            # 부분일치 (예: 'haiku')
    ocr_source: Optional[str] = None,       # 'client'|'server'
    styled: Optional[int] = None,           # 1=스타일 | 0=기본 모드
):
    where, params = [], []
    if nickname:
        where.append("nickname=?"); params.append(nickname)
    if mode:
        where.append("mode=?"); params.append(mode)
    if persona:
        where.append("persona=?"); params.append(persona)
    if version in (1, 2):
        where.append("api_version=?"); params.append(version)
    if model:
        where.append("model LIKE ?"); params.append(f"%{model}%")
    if ocr_source:
        where.append("ocr_source=?"); params.append(ocr_source)
    if styled in (0, 1):
        where.append("styled=?"); params.append(styled)
    wc = ("WHERE " + " AND ".join(where)) if where else ""
    with db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM requests {wc}", params).fetchone()[0]
        rows = c.execute(
            f"""SELECT id, conversation_id, parent_id, nickname, persona, mode,
                       text, ocr_source, user_text, result,
                       client_ip, api_version, detail, styled, ms_ocr, ms_llm, ms_total, model,
                       LENGTH(image_b64) AS img_len, created_at
                FROM requests {wc} ORDER BY id DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset,
            "messages": [dict(r) for r in rows]}


# ---------- GET /message/{id} ----------
@app.get("/message/{message_id}")
def get_message(message_id: int, include_image: bool = False):
    with db() as c:
        row = c.execute("SELECT * FROM requests WHERE id=?", (message_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "메시지 없음")
    d = dict(row)
    if not include_image:
        d.pop("image_b64", None)
    return d


# ---------- GET /conversation/{conversation_id} ----------
@app.get("/conversation/{conversation_id}")
def get_conversation(conversation_id: str):
    with db() as c:
        rows = c.execute(
            "SELECT id, parent_id, mode, text, result, created_at "
            "FROM requests WHERE conversation_id=? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
    return {
        "conversation_id": conversation_id,
        "count": len(rows),
        "messages": [dict(r) for r in rows],
    }


# ---------- GET /users/{nickname}/messages ----------
@app.get("/users/{nickname}/messages")
def user_messages(
    nickname: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = None,
):
    where = "WHERE nickname=?"
    params = [nickname]
    if mode:
        where += " AND mode=?"
        params.append(mode)

    with db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM requests {where}", params).fetchone()[0]
        rows = c.execute(
            f"""SELECT id, conversation_id, parent_id, persona, mode,
                       text, result, created_at
                FROM requests {where}
                ORDER BY id DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

    return {
        "nickname": nickname, "total": total, "limit": limit, "offset": offset,
        "messages": [dict(r) for r in rows],
    }


# ---------- GET /users/{nickname}/conversations ----------
@app.get("/users/{nickname}/conversations")
def user_conversations(nickname: str):
    with db() as c:
        rows = c.execute(
            """SELECT conversation_id,
                      COUNT(*) AS message_count,
                      MAX(created_at) AS updated_at
               FROM requests WHERE nickname=?
               GROUP BY conversation_id
               ORDER BY updated_at DESC""",
            (nickname,),
        ).fetchall()

        result = []
        for r in rows:
            last = c.execute(
                """SELECT text, result FROM requests
                   WHERE conversation_id=? ORDER BY id DESC LIMIT 1""",
                (r["conversation_id"],),
            ).fetchone()
            result.append({
                "conversation_id": r["conversation_id"],
                "message_count": r["message_count"],
                "last_text": last["text"],
                "last_result": last["result"],
                "updated_at": r["updated_at"],
            })

    return {"nickname": nickname, "conversations": result}


# ---------- GET /users/{nickname}/summary — 일별 질의 요약 (mode 분리·캐시) ----------
_SUMMARY_SYS = (
    "너는 사용자의 하루 AI 질의 로그를 요약한다. 각 줄은 '하나의 작업(대화)'이다. "
    "번역(translate)과 설명(explain)을 나누고, 비슷한 항목은 토픽으로 묶어라. 반드시 JSON만 출력:\n"
    '{"headline":"오늘 한 줄 요약","translate":{"count":n,"topics":["토픽 N건",...]},'
    '"explain":{"count":n,"topics":[...]}}')


def _kst_today() -> str:
    return (datetime.utcnow() + timedelta(hours=9)).date().isoformat()


@app.get("/users/{nickname}/summary")
def user_summary(nickname: str, date: Optional[str] = None, refresh: bool = False):
    day = date or _kst_today()
    with db() as c:
        rows = c.execute(
            """SELECT id, conversation_id, parent_id, mode, text, user_text FROM requests
               WHERE nickname=? AND date(created_at, '+9 hours')=?
               ORDER BY id""", (nickname, day)).fetchall()
        msg_count = len(rows)
        cached = c.execute("SELECT summary, source_count, model, created_at FROM summaries "
                           "WHERE nickname=? AND date=?", (nickname, day)).fetchone()
    # conversation 묶기: 대화별 루트(최초 메시지)를 '작업 1건'으로, 후속(더 자세히 등)은 합쳐 셈
    convs = {}   # conv_id -> {root row, followups}
    for r in rows:
        cid = r["conversation_id"]
        if cid not in convs:
            convs[cid] = {"root": r, "followups": 0}
        else:
            convs[cid]["followups"] += 1
    task_count = len(convs)
    if msg_count == 0:
        return {"nickname": nickname, "date": day, "total": 0, "conversations": 0, "cached": False,
                "summary": {"headline": "이 날 질의 없음", "translate": {"count": 0, "topics": []},
                            "explain": {"count": 0, "topics": []}}}
    # 캐시 적중: 메시지 수 그대로면 재사용 (새 메시지 생기면 무효화)
    if cached and cached["source_count"] == msg_count and not refresh:
        return {"nickname": nickname, "date": day, "total": msg_count, "conversations": task_count,
                "cached": True, "model": cached["model"], "summary": json.loads(cached["summary"])}
    # 생성: 대화(작업) 단위로 LLM에 전달 — 루트 질의 + 후속 수
    lines = []
    for cid, v in convs.items():
        r = v["root"]
        extra = f" | 추가요청: {r['user_text']}" if r["user_text"] else ""
        fu = f" (+후속 {v['followups']})" if v["followups"] else ""
        lines.append(f"[{r['mode']}] {(r['text'] or '')[:200]}{extra}{fu}")
    user = f"날짜 {day} · 작업 {task_count}건(메시지 {msg_count}건)\n" + "\n".join(lines)
    try:
        raw, model = text_complete(_SUMMARY_SYS, user, max_tokens=700)
        s = raw[raw.find("{"):raw.rfind("}") + 1]
        summary = json.loads(s)
    except Exception as e:
        raise HTTPException(502, f"요약 생성 실패: {e}")
    now = datetime.utcnow().isoformat()
    with db() as c:
        c.execute("""INSERT INTO summaries(nickname,date,summary,source_count,model,created_at)
                     VALUES(?,?,?,?,?,?)
                     ON CONFLICT(nickname,date) DO UPDATE SET
                       summary=excluded.summary, source_count=excluded.source_count,
                       model=excluded.model, created_at=excluded.created_at""",
                  (nickname, day, json.dumps(summary, ensure_ascii=False), msg_count, model, now))
    return {"nickname": nickname, "date": day, "total": msg_count, "conversations": task_count,
            "cached": False, "model": model, "summary": summary}


# ---------- DELETE /message/{id} ----------
@app.delete("/message/{message_id}", dependencies=[Depends(require_localhost)])
def delete_message(message_id: int):
    with db() as c:
        cur = c.execute("DELETE FROM requests WHERE id=?", (message_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "메시지 없음")
        c.execute("UPDATE requests SET parent_id=NULL WHERE parent_id=?", (message_id,))
    return {"deleted": True, "id": message_id}


# ---------- GET /personas ----------
@app.get("/personas")
def personas():
    return {"personas": [{"code": code, "style": style}
                         for code, style in MBTI_DESC.items()]}


# ---------- GET /health ----------
@app.get("/health")
def health():
    return {"status": "ok", "backend": get_backend().name,
            "time": datetime.utcnow().isoformat()}


# ---------- 테스트 콘솔 페이지 ----------
_HERE = os.path.dirname(__file__)


def _serve(name: str) -> HTMLResponse:
    with open(os.path.join(_HERE, name), encoding="utf-8") as f:  # 매 요청 읽기 → 수정 즉시 반영
        # no-store: 브라우저 캐시 방지 → 페이지를 고치면 새로고침에 바로 보임
        return HTMLResponse(f.read(), headers={"Cache-Control": "no-store"})


@app.get("/")
def console():
    return _serve("console.html")           # /analyze 테스트 콘솔


@app.get("/quiz-ui")
def quiz_console():
    return _serve("quiz_console.html")       # MBTI 퀴즈 테스트 페이지


@app.get("/clipboard-ui")
def clipboard_console():
    return _serve("clipboard.html")          # 이미지 클립보드(갤러리) 데모 페이지


# ---------- 샘플 테스트 이미지 (server/test_images/) ----------
_TEST_IMG_DIR = os.path.join(_HERE, "test_images")
_IMG_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp"}


@app.get("/test-images")
def list_test_images():
    """드롭다운용 목록. 파일명 접두사(translate_/explain_)로 mode 추정."""
    items = []
    if os.path.isdir(_TEST_IMG_DIR):
        for fn in sorted(os.listdir(_TEST_IMG_DIR)):
            ext = os.path.splitext(fn)[1].lower()
            if ext in _IMG_EXT:
                mode = ("translate" if fn.startswith("translate_")
                        else "explain" if fn.startswith("explain_") else None)
                items.append({"name": fn, "media_type": _IMG_EXT[ext], "mode": mode})
    return {"images": items}


@app.get("/test-images/{name}")
def get_test_image(name: str):
    if "/" in name or "\\" in name or name.startswith("."):   # 경로 탈출 방지
        raise HTTPException(400, "잘못된 파일명")
    ext = os.path.splitext(name)[1].lower()
    path = os.path.join(_TEST_IMG_DIR, name)
    if ext not in _IMG_EXT or not os.path.isfile(path):
        raise HTTPException(404, "이미지 없음")
    return FileResponse(path, media_type=_IMG_EXT[ext])


@app.get("/api")
def api_spec():
    return _serve("api_spec.html")           # 프론트 개발자용 API 명세


@app.get("/sample-test", dependencies=[Depends(require_localhost)])
def sample_test():
    return _serve("sample_test.html")        # v1·v2 동시 비교 (localhost 전용)


@app.get("/admin", dependencies=[Depends(require_localhost)])
def admin():
    return _serve("admin.html")              # DB 조회·삭제 관리 페이지 (localhost 전용)

"""공개 이미지 클립보드(갤러리).

누구나 이미지를 올리고(POST), 전체 목록을 조회하고(GET), 원본을 받아간다(GET .../raw).
**프런트 최소화**가 목표: 업로드는 multipart(클라 base64 0) 또는 JSON+base64 둘 다 받고,
표시는 API가 주는 url(`/clipboard/{id}/raw`)을 그대로 <img src>에 꽂으면 끝.

저장: 디코딩한 바이트는 server/uploads/ 에 디스크 파일로, 메타데이터만 SQLite(clipboard 테이블)에.
제한·인증 없음(전체 공개) — 의도된 설계. 운영에선 용량/rate 캡과 삭제 게이팅을 추가 권장.

main.py 패턴(quiz.py)과 동일: init_clipboard_db(db) + build_router(db) 를 main 이 마운트.
"""
import os
import uuid
import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

_HERE = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(_HERE, "uploads")          # 디스크 저장 위치 (gitignore)
# media_type -> 확장자. 모르는 타입이면 확장자 없이 저장(무제한이므로 거부하지 않음).
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}

router = APIRouter(prefix="/clipboard", tags=["clipboard"])


def init_clipboard_db(db):
    """clipboard 테이블 + 업로드 폴더 보장. main.py 가 startup 에 1회 호출."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with db() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS clipboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                nickname TEXT,                  -- 업로더 닉네임 (선택)
                media_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                stored_name TEXT NOT NULL,      -- 디스크 파일명 (서버 생성 uuid+ext)
                uploader_ip TEXT,
                created_at TEXT NOT NULL
            )"""
        )
        # 기존 테이블에 nickname 없으면 추가 (마이그레이션)
        cols = {r[1] for r in c.execute("PRAGMA table_info(clipboard)").fetchall()}
        if "nickname" not in cols:
            c.execute("ALTER TABLE clipboard ADD COLUMN nickname TEXT")


def _now() -> str:
    return datetime.utcnow().isoformat()


def _client_ip(request: Request) -> str:
    """요청 클라이언트 IP. 프록시 뒤면 X-Forwarded-For 첫 IP, 아니면 소켓 peer. (main._client_ip 복제)"""
    xff = request.headers.get("x-forwarded-for", "")
    if xff.strip():
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def _row_to_meta(row) -> dict:
    """목록/업로드 응답의 단일 형태. 디스크 파일명·바이트는 노출하지 않음."""
    return {
        "id": row["id"],
        "url": f"/clipboard/{row['id']}/raw",
        "media_type": row["media_type"],
        "size": row["size"],
        "name": row["name"],
        "nickname": row["nickname"],
        "created_at": row["created_at"],
    }


class ClipboardJSON(BaseModel):
    image_b64: str
    media_type: str = "image/jpeg"
    name: Optional[str] = None
    nickname: Optional[str] = None


def _save(db, name, nickname, media_type, raw: bytes, ip: str) -> dict:
    """바이트를 디스크에 쓰고 메타 row 를 INSERT. 파일명은 서버 생성 uuid(경로조작 불가)."""
    ext = _EXT.get((media_type or "").lower(), "")
    stored = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as f:
        f.write(raw)
    nickname = (nickname or "").strip() or None      # 빈 문자열은 NULL 로 (UI 에서 '익명' 표시)
    with db() as c:
        cur = c.execute(
            "INSERT INTO clipboard (name, nickname, media_type, size, stored_name, uploader_ip, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, nickname, (media_type or "application/octet-stream"), len(raw), stored, ip, _now()),
        )
        row = c.execute("SELECT * FROM clipboard WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row_to_meta(row)


def build_router(db):
    """clipboard 라우터. 전부 공개(인증·게이트 없음)."""

    @router.get("")
    def list_clipboard():
        with db() as c:
            rows = c.execute(
                "SELECT id, name, nickname, media_type, size, created_at FROM clipboard ORDER BY id DESC"
            ).fetchall()
        return {"items": [_row_to_meta(r) for r in rows]}

    @router.post("")
    async def upload(request: Request):
        ip = _client_ip(request)
        ctype = request.headers.get("content-type", "")
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            up = form.get("file")
            if up is None or not hasattr(up, "read"):
                raise HTTPException(400, "multipart 'file' 필드가 필요합니다")
            raw = await up.read()
            media_type = (up.content_type or "").lower()
            name = up.filename
            nickname = form.get("nickname")
        else:
            try:
                payload = ClipboardJSON(**(await request.json()))
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(400, "잘못된 JSON 본문 (image_b64 필요)")
            try:
                raw = base64.b64decode(payload.image_b64, validate=True)
            except Exception as e:
                raise HTTPException(400, f"image_b64 디코딩 실패: {e}")
            media_type = payload.media_type.lower()
            name = payload.name
            nickname = payload.nickname
        if not raw:
            raise HTTPException(400, "빈 이미지")
        return _save(db, name, nickname, media_type, raw, ip)

    @router.get("/{item_id}/raw")
    def raw(item_id: int, download: int = 0):
        with db() as c:
            row = c.execute(
                "SELECT name, media_type, stored_name FROM clipboard WHERE id=?", (item_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "이미지 없음")
        path = os.path.join(UPLOAD_DIR, row["stored_name"])   # stored_name 은 서버 생성값
        if not os.path.isfile(path):
            raise HTTPException(404, "파일 없음")
        headers = {"Cache-Control": "public, max-age=31536000, immutable"}
        if download:
            fn = row["name"] or f"clipboard-{item_id}"
            headers["Content-Disposition"] = f'attachment; filename="{fn}"'
        return FileResponse(path, media_type=row["media_type"], headers=headers)

    @router.delete("/{item_id}")
    def delete_clipboard(item_id: int):
        with db() as c:
            row = c.execute(
                "SELECT stored_name FROM clipboard WHERE id=?", (item_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "이미지 없음")
            try:
                os.remove(os.path.join(UPLOAD_DIR, row["stored_name"]))
            except FileNotFoundError:
                pass
            c.execute("DELETE FROM clipboard WHERE id=?", (item_id,))
        return {"deleted": item_id}

    return router

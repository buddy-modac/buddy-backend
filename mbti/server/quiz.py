"""MBTI 퀴즈 API 라우터.

흐름:
1. POST /quiz/start     → 세션 생성. 축별로 랜덤 문항 1개씩 뽑아 순서 고정. 첫 문항 반환.
2. POST /quiz/answer    → 현재 문항에 답변 → 점수 누적 → 다음 문항 or 최종 결과 반환.
3. GET  /quiz/{id}      → 세션 진행 상태 조회.

결과로 나온 4글자 MBTI는 그대로 /analyze 의 persona 로 쓸 수 있다.
"""

import json
import random
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .quiz_data import AXES, QUESTIONS
from .personas import compatibility_for

router = APIRouter(prefix="/quiz", tags=["quiz"])


# ---------- DB 초기화 (main의 db() 컨텍스트를 주입받아 사용) ----------
def init_quiz_db(db):
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS quiz_sessions (
            id TEXT PRIMARY KEY,
            nickname TEXT,
            question_ids TEXT NOT NULL,   -- 출제 순서 (json 배열)
            current_index INTEGER NOT NULL DEFAULT 0,
            scores TEXT NOT NULL,         -- {"E":0,"I":0,...} json
            answers TEXT NOT NULL,        -- [{"question_id":..,"value":..}] json
            result TEXT,                  -- 완료 시 4글자 MBTI
            status TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | done
            created_at TEXT NOT NULL
        )""")


# ---------- 헬퍼 ----------
def _pick_questions() -> list:
    """축별로 1문항씩 랜덤 추출, 축 순서대로 정렬해서 question id 리스트 반환."""
    picked = []
    for axis in AXES:
        q = random.choice(QUESTIONS[axis])
        picked.append(q["id"])
    return picked


def _find_question(qid: str) -> dict:
    for axis in AXES:
        for q in QUESTIONS[axis]:
            if q["id"] == qid:
                return q
    raise HTTPException(500, f"문항 정의를 찾을 수 없음: {qid}")


def _public_question(qid: str, index: int, total: int) -> dict:
    q = _find_question(qid)
    return {
        "question_id": q["id"],
        "index": index,          # 0-based 현재 문항 번호
        "total": total,
        "text": q["text"],
        "options": [
            {"label": o["label"], "value": o["value"]} for o in q["options"]
        ],
    }


def _compute_result(scores: dict) -> str:
    """각 축에서 점수 높은 글자를 뽑아 4글자 조합. 동점이면 좌측 글자 우선.

    주의: AXES는 'EI','NS','FT','PJ' 순이지만 MBTI 표기는 EI-SN-TF-JP 순이므로
    축 글자를 표준 순서(E/I, S/N, T/F, J/P)로 재배열해 반환한다.
    """
    def pick(axis):
        a, b = axis[0], axis[1]
        return a if scores.get(a, 0) >= scores.get(b, 0) else b
    ei = pick("EI")
    sn = pick("NS")               # N/S 축 → 표기 위치는 두 번째
    tf = pick("FT")
    jp = pick("PJ")
    return ei + sn + tf + jp


# ---------- 모델 ----------
class StartRequest(BaseModel):
    nickname: Optional[str] = None


class AnswerRequest(BaseModel):
    session_id: str
    question_id: str
    value: str   # 사용자가 고른 옵션의 value (E/I/N/S/F/T/P/J)


# ---------- 라우터 팩토리 ----------
# main.py 의 db() 컨텍스트매니저를 주입해 라우터를 구성한다.
def build_router(db):

    @router.post("/start")
    def start_quiz(req: StartRequest):
        sid = str(uuid.uuid4())
        qids = _pick_questions()
        scores = {ch: 0 for axis in AXES for ch in axis}
        now = datetime.utcnow().isoformat()

        with db() as c:
            c.execute(
                """INSERT INTO quiz_sessions
                (id, nickname, question_ids, current_index, scores,
                 answers, result, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (sid, req.nickname, json.dumps(qids), 0,
                 json.dumps(scores), json.dumps([]), None,
                 "in_progress", now),
            )

        return {
            "session_id": sid,
            "total": len(qids),
            "question": _public_question(qids[0], 0, len(qids)),
        }

    @router.post("/answer")
    def answer_quiz(req: AnswerRequest):
        with db() as c:
            row = c.execute(
                "SELECT * FROM quiz_sessions WHERE id=?", (req.session_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "세션 없음")
            if row["status"] == "done":
                raise HTTPException(400, "이미 완료된 세션")

            qids = json.loads(row["question_ids"])
            idx = row["current_index"]
            scores = json.loads(row["scores"])
            answers = json.loads(row["answers"])

            expected_qid = qids[idx]
            if req.question_id != expected_qid:
                raise HTTPException(
                    400,
                    f"현재 문항은 {expected_qid} 인데 {req.question_id} 답변이 옴",
                )

            # value 유효성 검증
            q = _find_question(expected_qid)
            valid_values = {o["value"] for o in q["options"]}
            if req.value not in valid_values:
                raise HTTPException(400, f"유효하지 않은 선택: {req.value}")

            # 점수 누적
            scores[req.value] = scores.get(req.value, 0) + 1
            answers.append({"question_id": expected_qid, "value": req.value})
            idx += 1

            # 마지막 문항이었으면 결과 계산
            if idx >= len(qids):
                result = _compute_result(scores)
                c.execute(
                    """UPDATE quiz_sessions
                    SET current_index=?, scores=?, answers=?, result=?, status='done'
                    WHERE id=?""",
                    (idx, json.dumps(scores), json.dumps(answers), result,
                     req.session_id),
                )
                return {
                    "session_id": req.session_id,
                    "done": True,
                    "result": result,        # 4글자 MBTI → persona 로 사용
                    "scores": scores,
                    "compatibility": compatibility_for(result),   # 궁합 Top-3
                }

            # 아직 남았으면 다음 문항
            c.execute(
                """UPDATE quiz_sessions
                SET current_index=?, scores=?, answers=?
                WHERE id=?""",
                (idx, json.dumps(scores), json.dumps(answers), req.session_id),
            )

        return {
            "session_id": req.session_id,
            "done": False,
            "question": _public_question(qids[idx], idx, len(qids)),
        }

    @router.get("/{session_id}")
    def get_quiz(session_id: str):
        with db() as c:
            row = c.execute(
                "SELECT * FROM quiz_sessions WHERE id=?", (session_id,)
            ).fetchone()
        if row is None:
            raise HTTPException(404, "세션 없음")

        qids = json.loads(row["question_ids"])
        idx = row["current_index"]
        out = {
            "session_id": session_id,
            "nickname": row["nickname"],
            "status": row["status"],
            "total": len(qids),
            "current_index": idx,
            "result": row["result"],
        }
        if row["status"] == "done":
            out["compatibility"] = compatibility_for(row["result"])   # 궁합 Top-3
        else:
            out["question"] = _public_question(qids[idx], idx, len(qids))
        return out

    return router

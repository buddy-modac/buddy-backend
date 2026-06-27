# buddy-backend

버디 매칭 앱의 백엔드 서버입니다.

## Client

정적 테스트 페이지는 `client/`에 있습니다.

```bash
cd client
python3 -m http.server 3000
open http://localhost:3000
```

API 호출 주소는 기본값 `http://localhost:8000`을 사용합니다.

## 데이터

- `data/questions.json` — MBTI 질문셋 (EI·SN·TF·PJ 총 11개 질문)

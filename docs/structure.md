# buddy-backend — 클라이언트 정적 페이지 설계안

## 개요

FastAPI 백엔드는 별도 팀원이 담당.
이 문서는 **정적 테스트 클라이언트 페이지**와 **GitHub Actions 자동 배포** 구조를 다룬다.

---

## 디렉토리 구조 (추가되는 부분)

```
buddy-backend/
├── data/
│   └── questions.json     # (기존)
├── client/                # ← 신규: 정적 테스트 UI
│   ├── index.html         # 질문 화면 + 결과 화면
│   ├── app.js             # API 호출 로직, 화면 전환
│   └── style.css          # 기본 스타일
├── docs/
│   └── structure.md       # 이 문서
└── .github/
    └── workflows/
        └── deploy-client.yml  # GitHub Pages 자동 배포
```

---

## 정적 클라이언트 (`client/`)

### 역할

FastAPI 서버를 **바로바로 테스트**할 수 있는 단일 페이지 UI.

1. API에서 질문 목록 가져오기
2. 질문을 순서대로 표시, 보기 선택
3. 모든 답변 완료 후 결과 API 호출
4. MBTI 결과 표시

### 화면 흐름

```
[시작 화면]
  → 버튼 클릭 → API에서 질문 로드

[질문 화면]
  → EI → SN → TF → PJ 순으로 각 질문 표시
  → 보기 선택 시 다음 질문으로 자동 이동

[결과 화면]
  → MBTI 4글자 크게 표시
  → 각 축 점수 표시 (E:2 / I:1 등) — 백엔드가 scores 필드를 내려줄 때만 표시
    (로컬 계산 fallback 경로에서는 scores 미제공이므로 점수 표시 없음)
  → 다시하기 버튼
```

### 기술 선택

- **Vanilla HTML/CSS/JS** — 빌드 스텝 없음, GitHub Pages에 바로 업로드 가능
- **API_BASE_URL 상수** — `app.js` 상단에서 한 줄만 바꾸면 로컬 ↔ 배포 전환

```js
// 로컬 테스트: 'http://localhost:8000'
// 서버 배포 후: 실제 서버 주소로 변경
// ⚠️ GitHub Pages(https)에서 사용할 때는 배포 서버도 https 주소여야 함 (mixed content 차단)
const API_BASE_URL = 'http://localhost:8000';
```

### 호출하는 API 엔드포인트 (예상)

| Method | Path | 용도 |
|--------|------|------|
| GET | `/api/questions` | 질문 전체 로드 |
| POST | `/api/result` | 답변 제출 → MBTI 결과 |

> 실제 엔드포인트 경로는 팀원 백엔드 구현에 맞춰 `app.js`에서 수정

---

## GitHub Actions — GitHub Pages 자동 배포

### 트리거

`main` 브랜치에 push 시 자동 실행
(필요 시 `client/**` path filter 추가 가능)

### 배포 흐름

```
push to main
  → GitHub Actions: client/ 폴더를 artifact로 업로드
  → GitHub 공식 deploy-pages 액션이 Pages에 배포
```

GitHub 공식 액션(`actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`)을 사용해 서드파티 의존성 없이 배포.

### 배포 결과 URL

```
https://buddy-modac.github.io/buddy-backend/
```

> ⚠️ GitHub Pages 활성화는 repo Settings → Pages에서 직접 설정 필요
> (Source: **GitHub Actions** 선택 — "Deploy from a branch" 아님)

---

## 로컬 테스트 방법

```bash
# 빌드 없이 브라우저에서 바로 열기
open client/index.html

# 또는 간단한 로컬 서버 (CORS 이슈 방지)
cd client && python3 -m http.server 3000
open http://localhost:3000
```

---

## 검토 포인트

- [ ] **API 엔드포인트 경로**: 팀원 백엔드의 실제 경로 확인 후 `app.js`에 반영 필요
- [ ] **CORS 설정**: 팀원 백엔드에서 Pages URL origin 허용 여부 확인 필요
- [ ] **GitHub Pages**: `buddy-modac` org 레포에서 Pages 사용 가능한지 확인 필요
- [ ] **결과 로직 위치**: MBTI 결과 계산을 백엔드가 하는지, 프론트에서 하는지 확인 필요

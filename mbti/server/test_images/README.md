# 샘플 테스트 이미지

API v1/v2 · mode(translate/explain) 수동 테스트용 이미지. 콘솔(`/`)의 **"샘플 이미지" 드롭다운**에서
클릭 한 번으로 불러와 업로드 없이 반복 테스트할 수 있다.

## 동작
- `GET /test-images` — 이 폴더의 이미지 목록(JSON). 콘솔 드롭다운이 이걸 읽는다.
- `GET /test-images/{파일명}` — 이미지 바이트 반환. 콘솔이 받아 base64로 변환해 사용.

## 네이밍 규칙 (mode 자동 선택)
- `translate_*` → 콘솔이 mode를 **translate**로 자동 설정
- `explain_*`   → mode **explain**으로 자동 설정
- 그 외 접두사 → mode 자동변경 없음(현재 선택 유지)

예: `translate_sale.png`, `explain_error_screen.png`, `translate_menu.jpg` …

## 추가 방법
이 폴더에 이미지 파일(png/jpg/jpeg/gif/webp)을 넣기만 하면 드롭다운에 자동 노출(서버 재시작 불필요,
목록은 요청 시마다 디렉토리를 읽음). **≤5MB 권장.** 민감정보 포함 이미지는 넣지 말 것.

## 기본 제공 샘플
- `translate_sale.png` — 세일 배너(번역용)
- `explain_error_screen.png` — 로그인 에러 화면(설명용)

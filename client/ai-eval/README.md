# Buddy AI Eval Report

GitHub Pages용 정적 리포트입니다.

- 진입점: `index.html`
- 이미지 에셋: `assets/`
- 생성 명령:

```bash
node scripts/ai-eval.mjs \
  --results <result-json-csv> \
  --pages-dir client/ai-eval
```

현재 GitHub Pages workflow는 `client/`를 배포 artifact로 사용합니다.
따라서 리포트는 `client/ai-eval/`에 있어야 하며, 배포 후 `/ai-eval/` 경로에서 볼 수 있습니다.

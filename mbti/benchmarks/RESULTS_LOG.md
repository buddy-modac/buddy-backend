# PersonaForge 블라인드 식별 벤치마크 로그

변경할 때마다 `run_benchmark.py`로 K회 측정한 결과를 아래에 append합니다.
K-sampled라 단일 표본 노이즈에 흔들리지 않고 추세 비교가 가능합니다.
(평균 적중률 = 모든 유형의 hits 합 / (유형수×K), 안정 = hits ≥ 80%×K)

---

## 2026-06-26 01:52 · "baseline 기준선 (기본 엔진)"
condition=**baseline** · K=5 · 유형 16개

- **평균 적중률: 88%** (70/80 draws)
- 안정 유형(hits≥4/5): **13/16**

| 유형 | 적중 | 분포 |
|---|---|---|
| ISTJ | 5/5 | ISTJ×5 |
| ISFJ | 5/5 | ISFJ×5 |
| INFJ | 5/5 | INFJ×5 |
| INTJ | 5/5 | INTJ×5 |
| ISTP | 3/5 | ISTP×3, INTP×2 |
| ISFP | 0/5 | INFP×5 |
| INFP | 5/5 | INFP×5 |
| INTP | 5/5 | INTP×5 |
| ESTP | 5/5 | ESTP×5 |
| ESFP | 5/5 | ESFP×5 |
| ENFP | 5/5 | ENFP×5 |
| ENTP | 5/5 | ENTP×5 |
| ESTJ | 5/5 | ESTJ×5 |
| ESFJ | 5/5 | ESFJ×5 |
| ENFJ | 5/5 | ENFJ×5 |
| ENTJ | 2/5 | INTJ×3, ENTJ×2 |

---

## 2026-06-26 02:15 · "약점 산문 수정 (ISFP+ISTP Se 전면, 큐레이션)"
condition=**curated** · K=5 · 유형 16개

- **평균 적중률: 96%** (77/80 draws)
- 안정 유형(hits≥4/5): **15/16**

| 유형 | 적중 | 분포 |
|---|---|---|
| ISTJ | 5/5 | ISTJ×5 |
| ISFJ | 5/5 | ISFJ×5 |
| INFJ | 5/5 | INFJ×5 |
| INTJ | 5/5 | INTJ×5 |
| ISTP | 5/5 | ISTP×5 |
| ISFP | 5/5 | ISFP×5 |
| INFP | 5/5 | INFP×5 |
| INTP | 5/5 | INTP×5 |
| ESTP | 5/5 | ESTP×5 |
| ESFP | 5/5 | ESFP×5 |
| ENFP | 5/5 | ENFP×5 |
| ENTP | 5/5 | ENTP×5 |
| ESTJ | 5/5 | ESTJ×5 |
| ESFJ | 5/5 | ESFJ×5 |
| ENFJ | 5/5 | ENFJ×5 |
| ENTJ | 2/5 | INTJ×3, ENTJ×2 |

---

## 2026-06-26 02:17 · "K=10 확정 — 고친 유형(ISFP·ISTP) 신뢰도 검증"
condition=**curated** · K=10 · 유형 2개

- **평균 적중률: 100%** (20/20 draws)
- 안정 유형(hits≥8/10): **2/2**

| 유형 | 적중 | 분포 |
|---|---|---|
| ISFP | 10/10 | ISFP×10 |
| ISTP | 10/10 | ISTP×10 |

---

## 2026-06-26 02:37 · "약점 3종 산문수정 (ISFP·ISTP Se + ENTJ E-전면, 큐레이션)"
condition=**curated** · K=5 · 유형 16개

- **평균 적중률: 99%** (79/80 draws)
- 안정 유형(hits≥4/5): **16/16**

| 유형 | 적중 | 분포 |
|---|---|---|
| ISTJ | 5/5 | ISTJ×5 |
| ISFJ | 5/5 | ISFJ×5 |
| INFJ | 5/5 | INFJ×5 |
| INTJ | 5/5 | INTJ×5 |
| ISTP | 5/5 | ISTP×5 |
| ISFP | 5/5 | ISFP×5 |
| INFP | 5/5 | INFP×5 |
| INTP | 5/5 | INTP×5 |
| ESTP | 5/5 | ESTP×5 |
| ESFP | 5/5 | ESFP×5 |
| ENFP | 5/5 | ENFP×5 |
| ENTP | 5/5 | ENTP×5 |
| ESTJ | 5/5 | ESTJ×5 |
| ESFJ | 5/5 | ESFJ×5 |
| ENFJ | 5/5 | ENFJ×5 |
| ENTJ | 4/5 | ENTJ×4, ESTJ×1 |

---

## 2026-06-26 02:39 · "K=10 확정 — ENTJ(E-전면) 신뢰도 검증"
condition=**curated** · K=10 · 유형 1개

- **평균 적중률: 90%** (9/10 draws)
- 안정 유형(hits≥8/10): **1/1**

| 유형 | 적중 | 분포 |
|---|---|---|
| ENTJ | 9/10 | ENTJ×9, ESTJ×1 |

---

## 2026-06-26 04:47 · "Phase 2 어시스턴트 모드 스타일 인식도"
condition=**assistant** · K=3 · 유형 16개

- 평균 적중률: **38%** (18/48) · 안정 7/16
- (어시스턴트 모드에서도 MBTI 스타일이 식별되나 — 상세표 assistant_style_20260626.md)

---

## 2026-06-26 11:33 · "P2.3 Sensing 강화 실험"
- A(스타일): 8 S유형 amplify, S로 읽힌 비율 6/24 (강화 전 0)
- B(능력): 강화 스타일 vs 기본 모드 정확·완전성 — 상세 amplify_experiment_20260626.md

---

## 2026-06-26 13:18 · "P2.3 Sensing 강화 실험"
- A(스타일): 8 S유형 amplify, S로 읽힌 비율 6/24 (강화 전 0)
- B(능력): 강화 스타일 vs 기본 모드 정확·완전성 — 상세 amplify_experiment_20260626.md

---

## 2026-06-26 13:40 · "P2.3 S-family 루프 (K=5)"
- S-family read율 5/40 = 12% (목표 70%) · 능력바닥 FAIL — 상세 s_family_loop_20260626.md

---

## 2026-06-26 14:28 · "P2.3 방법 배터리"
- M1 vibe차원 / M2 실사용probe / M3 few-shot 비교 — 상세 methods_battery_20260626.md

---

## 2026-06-26 15:10 · "Phase 2 현재상태 (실사용+패밀리, K=3)"
- 정확16지 6/48=12% · 패밀리매칭 12/48=25% — 상세 phase2_eval_20260626.md

---

## 2026-06-27 00:18 · "Option A 행동형 16유형"
- 정확 16%(vs12) 패밀리 35%(vs25) P등록 1/48 · 상세 behavioral_all16_20260626.md

---

## 2026-06-27 01:19 · "Option A 행동형 16유형"
- 정확 30%(vs12) 패밀리 43%(vs25) P등록 10/80 · 상세 curated_all16_20260626.md

---

## 2026-06-27 02:43 · "Option A 행동형 16유형"
- 정확 47%(vs12) 패밀리 62%(vs25) P등록 12/80 · 상세 curated_v2_all16_20260626.md

---

## 2026-06-27 03:04 · "Option A 행동형 16유형"
- 정확 46%(vs12) 패밀리 61%(vs25) P등록 9/80 · 상세 curated_v3_all16_20260626.md

---

## 2026-06-27 03:20 · "Option A 행동형 16유형"
- 정확 50%(vs12) 패밀리 61%(vs25) P등록 12/80 · 상세 curated_v4_all16_20260626.md

---

## 2026-06-27 03:34 · "Option A 행동형 16유형"
- 정확 51%(vs12) 패밀리 62%(vs25) P등록 18/80 · 상세 curated_v5_all16_20260626.md

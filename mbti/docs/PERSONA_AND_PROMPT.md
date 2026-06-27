# 페르소나 추출 & A/B/C 프롬프트 경계

이 문서는 **MBTI 유형이 어떻게 페르소나로 추출되는지**와, 그 페르소나가 **시스템 프롬프트의
A/B/C 블록**에 어떻게 들어가는지를 한 장으로 정리한다.
> **정본은 코드.** 이 문서는 요약이며, 실제 동작은 아래 파일들이 진실이다.
> 추출: `personaforge/mbti.py` · 스타일(B): `personaforge/style.py` · 프롬프트 조립: `personaforge/assistant_prompt.py` · 가드레일(C): `personaforge/guardrails.py`

---

## 1. 페르소나 추출 파이프라인 (`personaforge/mbti.py`)

**입력은 4글자 유형 하나(예: `INTP`)뿐.** 외부 호출·웹수집 없이 **결정론적**으로 만들어진다.
근거 이론은 **공개 모델**이다: 16Personalities/NERIS의 4축 + **Harold Grant 인지기능 스택**
(융 계보 — 공식 MBTI가 아니고 학술적으로 논쟁적이지만, 대중적 유형 이미지를 재현하는 게 목적).

```
유형(INTP)
  │
  ├─① 인지기능 스택  STACKS[INTP] = (Ti, Ne, Si, Fe)   # 주·부·3차·열등
  │       (FUNCTIONS: Ti=내향사고·정밀, Ne=외향직관·가능성, Si=내향감각·경험, Fe=외향감정·조화)
  │
  ├─② saliences      derive_saliences(stack) + FUNCTION_VALUES
  │       주·부기능이 중시하는 가치를 가중 조합 → 예: 논리적 일관성·이해·정밀, 가능성·새 아이디어
  │       (※ 어디서 베낀 설명이 아니라, 인지기능의 표준 의미에서 '파생'됨)
  │
  ├─③ 벡터           MBTIVector(EI, SN, TF, JP, [AT], saliences)
  │       4축 연속값 [-1,1] + 선택 5축 AT(정체성) + 위 saliences
  │
  └─④ build_mbti()   → CharacterProfile(.mbti, .persona_prose, .provenance)
          persona_prose = 그 유형의 말투·기질 산문 (식별력의 실제 레버)
```

### 축 부호 의미 (`MBTI_AXES`, `AXIS_LETTERS`)
| 축 | −1 | +1 | 16P 이름 |
|---|---|---|---|
| `EI` | E (외향) | I (내향) | Mind |
| `SN` | S (감각) | N (직관) | Energy |
| `TF` | T (사고) | F (감정) | Nature |
| `JP` | J (판단) | P (인식) | Tactics |
| `AT`(선택) | Assertive | Turbulent | Identity |

> **핵심:** 식별력(이 답이 그 유형으로 읽히는지)은 **벡터 숫자보다 `persona_prose`(단어)**가 좌우한다.
> 그래서 어려운 유형은 산문에서 "구분되는 보조기능"을 전면화해 고친다(예: ISFP=Se 손에 잡히는 감각).
> 자세한 측정/개선 기록은 `benchmarks/RESULTS_LOG.md`.

---

## 2. A/B/C 프롬프트 경계 (`personaforge/assistant_prompt.py`)

서버가 AI에 보내는 시스템 프롬프트는 **3블록**이다. **A·C는 모든 유형 공통(상수), B만 유형별.**
이는 Phase 1(캐릭터 롤플레이: 사람인 척, AI 숨김)의 **역(逆)** — 여기선 **투명한 AI, 말투만 MBTI**.

```
[A] BASE_ASSISTANT  (상수)   ── 유능·정직·투명한 AI. "AI임을 숨기지 않는다." 정확/도움 최우선.
[B] COMMUNICATION STYLE (유형별) ── build_style_guide(type): *어떻게* 말할지(톤·구조·강조)만.
        무엇을 말하는지·정확성은 안 건드림.  styled=false 면 이 블록 통째 생략(= 기본 모드).
[C] PRIORITIES & GUARDRAILS (상수) ── 충돌 시 우선순위 + 안전바닥.
```

### 블록별 역할
| 블록 | 내용 | 코드 |
|---|---|---|
| **A** | 투명·유능·정직한 어시스턴트 정체성 | `BASE_ASSISTANT` (assistant_prompt.py) |
| **B** | 유형별 소통 스타일(말투만, 능력 불변) | `build_style_guide()` (style.py — 인지기능/축에서 디렉티브 생성) |
| **C** | **안전 > 정확·도움 > 스타일** + 가드레일(반아첨·고립조장 금지·위기 자원·진단 금지) | `PRIORITIES` (assistant_prompt.py) · `guardrails.py` |

### 토글 / 능동 제안
- **`styled`** (요청): `true`(기본·B 포함) | `false`(B 생략 = 기본 모드, 담백).
- **`suggest_plain`** (응답): 스타일이 답의 정확성/유용성을 해칠 것 같으면 모델이 내부 마커를 내고, 서버가 그걸 떼어 `true`로 표시 → 클라이언트가 "기본 모드" 토글을 강조. (마커는 result에 노출 안 됨)
- "정확·도움 > 스타일"(C)을 *실제로 지키는* 안전장치가 이 신호다.

---

## 한눈 요약
- **추출**: 4글자 → 인지기능 스택 → saliences → 벡터(+AT) → `persona_prose`. 전부 결정론적·공개이론. (mbti.py)
- **프롬프트**: A(투명 AI·상수) + B(유형 말투·style.py) + C(안전/정확 우선·가드레일·상수). styled로 B on/off, suggest_plain으로 능동 권유. (assistant_prompt.py)
- 모델 라우팅(F→Claude, T→GPT)·정책: `docs/MODEL_ROUTING.md`.

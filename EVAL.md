# EVAL — 실험과 평가

> 이 파일은 **자동 생성된다.** `uv run python scripts/make_eval.py`
> 숫자는 `runs/<실행ID>/outcome.json` 에서 계산한다. 손으로 적지 않는다.

측정한 실행: **35건**

## 1. 전체 지표

| 지표 | 정의 | 결과 |
|---|---|---|
| 카드 생성률 | 카드 파일이 실제로 만들어진 실행 | **6/35 (17%)** |
| 완주율 | 마지막 단계까지 끝난 실행 | 2/35 (6%) |
| 사람 개입 횟수 | 실행당 질문 수 (적을수록 좋다) | 평균 **1.4회** (최소 0 / 최대 10) |
| 루프 반복 | 실행당 판단 횟수 | 평균 9.8회 |
| 도구 실패 | 전체 도구 호출 중 실패 | 23건 / 351건 |

**완주율이 낮은 이유 — 실패한 실행을 지우지 않았다**

여기 있는 실행 대부분은 만드는 도중의 것이다. 지우면 표는 예뻐지지만
무엇을 고쳤는지가 사라진다. 그대로 두고 원인을 적는다.

| 원인 | 무엇이었나 | 어떻게 고쳤나 |
|---|---|---|
| 검색 도구 키 없음 | Tavily 키가 없어 조사 단계가 통째로 실패 | 키를 발급받아 연결 |
| 검색 무한 반복 | 모델이 검색어만 바꿔 12회 반복하다 상한에 걸림 | 도구별 호출 횟수를 모델에게 알려주고 상한 명시 |
| 단계 밖 도구 호출 | 목록에 없는 도구도 이름만 대면 실행됨 | 단계별 허용 목록을 코드로 강제 |
| 모델 한도·과부하 | 429·503 으로 중단 | 폴백 사슬에 503 도 포함 |
| 반복 상한이 빡빡함 | 검토 반려 후 재작업이 20회를 넘김 | 상한을 30 으로 조정 |
| **질문이 반복 예산을 먹음** | 카드 합성 단계에서 같은 것을 세 번 물어 루프 3회를 태웠다. 재시도 상한은 실패에만 걸리고 **질문은 무제한**이었다 | 단계별 질문 상한 3회 (D-023 후속) |
| **발송이 지어낸 파일명을 씀** | 실제는 `card_01.png` 인데 모델이 `card1.png` 을 불러 "보낼 파일이 없다" 로 막혔다 | 파일 목록을 앱이 폴더에서 직접 읽는다 |
| **상한 30 이 여전히 부족** | 세 실행이 연속으로 6/7 에서 상한에 걸렸다. 완주한 실행조차 27 로 90% 를 썼다 | 45 로 조정 (D-024). **원인부터 고치고 올렸다** |
| **검색 결과가 모델에 안 갔다** | `ToolResult.data` 가 쓰이지 않았다. 저장되는 요약은 `→ 3건` 처럼 **건수만**(48자) 적어, 다음 반복부터 모델은 URL 을 본 적이 없었다 | 요약에 `제목 (게시일) URL` 을 싣고, 관찰 절단 길이를 도구별로 뒀다 (D-022) |
| **게시일 표기가 깨졌다** | Tavily 가 RFC-2822 를 주는데 앞 10자를 잘라 `Wed, 02 Se` 가 됐다 | `YYYY-MM-DD` 로 정규화. **날짜 대조가 함정 1번**이다 (D-022) |
| **경고가 뒤 단계로 새어나갔다** | 호출 횟수를 실행 전체로 세니, 단계1 의 *"그만하고 finish_step 하라"* 가 단계3 에도 실려 원문을 열기 전에 종료됐다 | 단계 안에서만 센다 (D-023) |
| 🔴 **게이트가 앞 단계 답변으로 충족됐다** | *"이미 답을 받았다면"* 이 어느 질문인지 구분하지 않아, 단계2(후보 선택)가 **질문 없이** 통과됐다. 단계4 는 물었다 — 비결정적으로 새는 구조 | 이 단계에서 물은 질문만 근거로 삼고, `finish_step` 을 **코드로 막았다** (D-023) |

앞의 다섯을 고친 뒤의 실행에서 **7/7 단계 완주**했다. 마지막 단계가 발송 승인이라
사람이 승인해야 `done` 이 되는 구조인 것도 맞다.

뒤의 일곱은 **완주한 뒤에 발견한 것들**이다. 돌아가는 것과 제대로 돌아가는 것은 다르다.
`run-ebec96b7eba9` 와, 완주를 다시 시도하며 얻은 네 실행에서 확인했다.

**완주는 세 번 실패하고 네 번째에 됐다.** 매번 다른 곳에서 막혔고, 막힌 자리마다 원인이 달랐다.

| 실행 | 루프 | 도달 | 막힌 이유 |
|---|---|---|---|
| `run-ca32f9d1e18d` | 30 | 5/7 | 같은 질문 3회 반복으로 예산 소진 |
| `run-4605c934a58e` | 30 | 6/7 | 발송이 지어낸 파일명을 찾다 실패 |
| `run-ce638ca65581` | 30 | 6/7 | 상한 자체가 부족 |
| **`run-e5484e2520c7`** | **27** | **7/7** | **완주** — 세 가지를 다 고친 뒤 |

```
단계2  ask_human → (사람 답변 2건) → finish     ← 이전에는 finish 만 하고 건너뜀
단계3  web_search FAIL(이 단계 불허)
       fetch_article OK  원문 563자 · 게시일 2026-09-04
       fetch_article OK  게시일 2026-08-16
       fetch_article OK  (재확인)
단계4  get_audience_profile → get_card_template → ask_human
```

**`fetch_article` 이 실제로 원문을 열고 게시일을 확인한 첫 실행이다.**
그전까지는 검색 결과 요약만 보고 넘어갔다 — 이 과제가 반복해서 경고한 함정 그대로였다.

## 2. 세팅 비교 — 제공자와 모델을 바꿔 가며

```bash
uv run python scripts/compare_settings.py --repeat 3          # 전부
uv run python scripts/compare_settings.py --only openai --repeat 3
```

같은 주제·지역으로 **세팅만 바꿔** 첫 사람 개입 지점까지 돌린 결과다.
끝까지 돌리지 않는 이유는 무료 한도(모델당 하루 20회, D-016) 때문이고,
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.

### 같은 세팅을 3회씩 쟀다

한 번씩만 재면 **모델 간 차이인지 그날의 운인지 구분할 수 없다.**
LLM 은 같은 입력에도 다르게 답한다.

**주제: 이번 주 시니어 건강·생활 정보**

| 설정한 세팅 | n | 루프 평균 | 루프 폭 | 입력 토큰 평균 | 출력 토큰 평균 | 폴백 | 비용 |
|---|---|---|---|---|---|---|---|
| `gemini/gemini-3.5-flash` | 3 | 7.0 | 0 | 12,872 | 358 | 3/3 | 무료 |
| `gemini/gemini-3.6-flash` | 2 | 6.5 | 9 | 8,200 | 672 | — | 무료 |

**주제: 시니어 환절기 건강 관리**

| 설정한 세팅 | n | 루프 평균 | 루프 폭 | 입력 토큰 평균 | 출력 토큰 평균 | 폴백 | 비용 |
|---|---|---|---|---|---|---|---|
| `gemini/gemini-3.1-flash-lite` | 4 | 6.0 | 2 | 10,414 | 359 | — | 무료 |
| `gemini/gemini-3.5-flash` | 4 | 6.0 | 4 | 11,984 | 321 | 3/4 | 무료 |
| `gemini/gemini-3.5-flash-lite` | 4 | 5.2 | 5 | 9,332 | 296 | — | 무료 |
| `openai/gpt-5-mini` | 4 | 11.5 | 25 | 37,899 | 16,310 | — | $0.1684 |

**주제: 시니어 독감 예방접종 안내**

| 설정한 세팅 | n | 루프 평균 | 루프 폭 | 입력 토큰 평균 | 출력 토큰 평균 | 폴백 | 비용 |
|---|---|---|---|---|---|---|---|
| `gemini/gemini-3.5-flash` | 3 | 13.0 | 18 | 20,125 | 596 | 1/3 | 무료 |

### 무엇이 달랐나

- 🔴 **`gemini-3.5-flash` 행은 비교로 쓸 수 없다.** 폴백 열을 보면 4회 중 3회가
  한도 소진으로 **다른 모델로 갈아탔다.** 설정만 그 모델이었을 뿐 실제로는 lite 로 돌았다.
  **"모델을 설정했다" 와 "그 모델로 돌았다" 는 다르다.**
  폴백을 기록해두지 않았다면 이 표는 거짓말을 했을 것이다
- 🔺 **이전 결론을 하나 거둬들인다.** 1회씩 쟀을 때는 *"큰 모델이 도구를 더 쓴다"* 고 적었는데,
  반복해 보니 **lite 두 모델의 평균 차이가 각자의 편차 폭보다 작다.**
  모델 차이라고 말할 수 없다. **반복 없이 비교하면 편차를 실력으로 착각한다**
- **가장 일관된 것은 `gpt-5-mini` 였다** (폭 1). Gemini lite 계열은 폭 2~5 로 흔들렸다.
  운영에서는 평균보다 이 폭이 더 중요할 수 있다 — 매번 다르게 도는 것을 예측할 수 없다
- **제공자 간 차이가 모델 간 차이보다 컸다.** `gpt-5-mini` 는 출력 토큰이
  Gemini 계열의 8–10배다(3,300–4,000 vs 250–450). 추론 토큰을 쓰기 때문이다.
  반대로 입력 토큰은 적다 — 루프를 덜 돌아서다.
  **"토큰이 많다/적다" 는 제공자를 섞으면 같은 뜻이 아니다**
- **도구 선택 순서는 제공자를 가리지 않았다.** Gemini 3종과 OpenAI 모두
  `list_past_publications` 를 **가장 먼저** 불렀다. 단계 목표에 도구 이름을 직접 적어둔 것이
  제공자와 무관하게 작동했다 — D-022 에서 얻은 방법이다

### 비용과 한도

Gemini 는 무료 티어라 0원이고, OpenAI 는 기관 지급 크레딧 $5 에서 나간다.
비용 열은 `llm_usage` 에 쌓인 실제 사용량으로 계산한 값이다.

**공짜에는 값이 있다.** 무료 경로는 돈이 안 드는 대신 한도에 걸려
**측정 자체가 오염됐다**(위 폴백 3/4). 유료 경로는 $0.03 으로 3회를 흔들림 없이 쟀다.
무료를 기본으로 두는 판단(D-010)은 유지하되, **비교 실험만큼은 한도에 걸리지 않는 쪽으로
재야 한다**는 것을 이번에 배웠다.

### 실행별 원자료

**주제: 이번 주 시니어 건강·생활 정보** — 같은 지역·같은 시점, 모델만 바꿈

| 모델 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 7 | 12,267 | 350 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 7 | 13,824 | 379 | list_past_publications → web_search → web_search → get_weather → web_search |
| `gemini-3.5-flash-lite` | 7 | 12,524 | 345 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.6-flash` | 2 | 2,110 | 63 | get_weather → web_search✗ |
| `gemini-3.6-flash` | 11 | 14,290 | 1,281 | web_search✗ → get_weather → compose_cards |

**주제: 시니어 환절기 건강 관리** — 같은 지역·같은 시점, 모델만 바꿈

| 모델 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|
| `gemini-3.1-flash-lite` | 6 | 9,245 | 463 | list_past_publications → web_search✗ → get_weather → list_past_publications |
| `gemini-3.1-flash-lite` | 5 | 8,483 | 310 | list_past_publications → web_search → get_weather |
| `gemini-3.1-flash-lite` | 7 | 13,858 | 355 | list_past_publications → web_search → get_weather → web_search → web_search |
| `gemini-3.1-flash-lite` | 6 | 10,072 | 309 | list_past_publications → web_search → get_weather → web_search |
| `gemini-3.5-flash` | 3 | 4,129 | 88 | list_past_publications → get_weather → web_search✗ |
| `gemini-3.5-flash-lite` | 2 | 2,664 | 60 | list_past_publications → web_search✗ |
| `gemini-3.5-flash-lite` | 7 | 13,936 | 361 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 7 | 14,865 | 427 | list_past_publications → web_search → get_weather → web_search → web_search |
| `gemini-3.5-flash-lite` | 7 | 15,005 | 408 | list_past_publications → web_search → get_weather → web_search → web_search |
| `gemini-3.5-flash-lite` | 5 | 8,214 | 251 | list_past_publications → get_weather → web_search → web_search |
| `gemini-3.5-flash-lite` | 7 | 13,020 | 422 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 7 | 13,432 | 449 | list_past_publications → get_weather → web_search → web_search → web_search |
| `openai/gpt-5-mini` | 5 | 8,010 | 3,321 | list_past_publications → web_search → web_search → web_search |
| `openai/gpt-5-mini` | 5 | 8,510 | 3,964 | list_past_publications → web_search → web_search → get_weather |
| `openai/gpt-5-mini` | 6 | 10,064 | 3,768 | list_past_publications → web_search → web_search → web_search → get_weather |
| `openai/gpt-5-mini` | 30 | 125,012 | 54,186 | list_past_publications → web_search → get_weather → web_search → web_search → fetch_article → fetch_article → fetch_article✗ → get_audience_profile → get_card_template → compose_cards → 검토에이전트✗ → compose_cards → 검토에이전트✗ → compose_cards → 검토에이전트 |

**주제: 시니어 독감 예방접종 안내** — 같은 지역·같은 시점, 모델만 바꿈

| 모델 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|
| `gemini-3-flash-preview` | 27 | 64,820 | 6,283 | list_past_publications → web_search → web_search → get_weather → web_search → fetch_article✗ → web_search✗ → get_audience_profile → get_card_template → compose_cards → 검토에이전트✗ → get_audience_profile → compose_cards → 검토에이전트 → record_publication |
| `gemini-3.5-flash` | 2 | 1,252 | 29 | list_past_publications |
| `gemini-3.5-flash` | 17 | 25,749 | 792 | list_past_publications → web_search → get_weather → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 20 | 33,373 | 966 | list_past_publications → web_search → web_search → get_weather → web_search → web_search → web_search → web_search → web_search → web_search → web_search → get_audience_profile → get_card_template |

**주제: ½Ã´Ï¾î È¯Àý±â °Ç°­ °ü¸®** — 같은 지역·같은 시점, 모델만 바꿈

| 모델 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 16 | 44,950 | 1,110 | list_past_publications → web_search → get_weather → web_search → web_search → web_search✗ → fetch_article → fetch_article → fetch_article → get_audience_profile → get_card_template |
| `openai/gpt-5-mini` | 1 | 1,267 | 998 | — |

## 3. 전체 실행 기록

| 시각 | 주제 | 모델 | 단계 | 카드 | 개입 | 루프 | 토큰 | 도구 호출 순서 |
|---|---|---|---|---|---|---|---|---|
| 09-09 10:02 | 이번 주 시니어 건강·생활 정보 | `gemini-3.6-flash` | 0/7 | — | 0 | 2 | 2,110 | get_weather → web_search✗ |
| 09-09 11:35 | 이번 주 건강·생활 정보 | `gemini-3.6-flash` | 0/7 | — | 0 | 3 | 2,104 | get_weather → web_search✗ |
| 09-09 11:37 | 이번 주 시니어 건강·생활 정보 | `gemini-3.6-flash` | 5/7 | ⭕ | 3 | 11 | 14,290 | web_search✗ → get_weather → compose_cards |
| 09-09 12:29 | 환절기 건강 지키는 생활 수칙 | `gemini-3.6-flash` | 0/7 | — | 0 | 4 | 4,138 | list_past_publications → get_weather → web_search✗ |
| 09-09 12:38 | 시니어 환절기 건강 관리 | `gemini-3.5-flash` | 0/7 | — | 0 | 3 | 4,129 | list_past_publications → get_weather → web_search✗ |
| 09-09 12:38 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 0/7 | — | 0 | 2 | 2,664 | list_past_publications → web_search✗ |
| 09-09 12:38 | 시니어 환절기 건강 관리 | `gemini-3.1-flash-lite` | 0/7 | — | 1 | 6 | 9,245 | list_past_publications → web_search✗ → get_weather → list_past_publications |
| 09-09 13:23 | 시니어 겨울철 낙상 예방 | `gemini-3.5-flash` | 0/7 | — | 0 | 3 | 3,932 | list_past_publications → get_weather → web_search✗ |
| 09-09 14:43 | 시니어 독감 예방접종 안내 | `gemini-3.5-flash` | 0/7 | — | 0 | 2 | 1,252 | list_past_publications |
| 09-09 14:45 | 시니어 독감 예방접종 안내 | `gemini-3.5-flash` | 1/7 | — | 0 | 17 | 25,749 | list_past_publications → web_search → get_weather → web_search → web_search → we |
| 09-09 14:50 | 시니어 독감 예방접종 안내 | `gemini-3.5-flash-lite` | 4/7 | — | 3 | 20 | 33,373 | list_past_publications → web_search → web_search → get_weather → web_search → we |
| 09-09 14:57 | 시니어 독감 예방접종 안내 | `gemini-3-flash-preview` | 7/7 | ⭕ | 6 | 27 | 64,820 | list_past_publications → web_search → web_search → get_weather → web_search → fe |
| 09-09 15:50 | ½Ã´Ï¾î µ¶°¨ ¿¹¹æÁ¢ | `gemini-3.5-flash-lite` | 3/7 | — | 1 | 12 | 27,655 | list_past_publications → web_search → web_search → web_search → get_weather → ge |
| 09-09 15:58 | ½Ã´Ï¾î È¯Àý±â °Ç°­ | `gemini-3.5-flash-lite` | 3/7 | — | 1 | 16 | 44,950 | list_past_publications → web_search → get_weather → web_search → web_search → we |
| 09-09 16:28 | 이번 주 시니어 건강·생활 정보 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 12,267 | list_past_publications → get_weather → web_search → web_search → web_search |
| 09-09 16:29 | 이번 주 시니어 건강·생활 정보 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 13,824 | list_past_publications → web_search → web_search → get_weather → web_search |
| 09-09 16:33 | 이번 주 시니어 건강·생활 정보 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 12,524 | list_past_publications → get_weather → web_search → web_search → web_search |
| 09-09 22:59 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 13,936 | list_past_publications → get_weather → web_search → web_search → web_search |
| 09-09 23:00 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 14,865 | list_past_publications → web_search → get_weather → web_search → web_search |
| 09-09 23:00 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 15,005 | list_past_publications → web_search → get_weather → web_search → web_search |
| 09-09 23:01 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 0/7 | — | 0 | 5 | 8,214 | list_past_publications → get_weather → web_search → web_search |
| 09-09 23:02 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 13,020 | list_past_publications → get_weather → web_search → web_search → web_search |
| 09-09 23:02 | 시니어 환절기 건강 관리 | `gemini-3.5-flash-lite` | 1/7 | — | 0 | 7 | 13,432 | list_past_publications → get_weather → web_search → web_search → web_search |
| 09-09 23:03 | 시니어 환절기 건강 관리 | `gemini-3.1-flash-lite` | 1/7 | — | 0 | 5 | 8,483 | list_past_publications → web_search → get_weather |
| 09-09 23:03 | 시니어 환절기 건강 관리 | `gemini-3.1-flash-lite` | 1/7 | — | 0 | 7 | 13,858 | list_past_publications → web_search → get_weather → web_search → web_search |
| 09-09 23:04 | 시니어 환절기 건강 관리 | `gemini-3.1-flash-lite` | 1/7 | — | 0 | 6 | 10,072 | list_past_publications → web_search → get_weather → web_search |
| 09-09 23:10 | 시니어 환절기 건강 관리 | `openai/gpt-5-mini` | 0/7 | — | 0 | 5 | 8,010 | list_past_publications → web_search → web_search → web_search |
| 09-09 23:11 | 시니어 환절기 건강 관리 | `openai/gpt-5-mini` | 0/7 | — | 0 | 5 | 8,510 | list_past_publications → web_search → web_search → get_weather |
| 09-09 23:12 | 시니어 환절기 건강 관리 | `openai/gpt-5-mini` | 0/7 | — | 0 | 6 | 10,064 | list_past_publications → web_search → web_search → web_search → get_weather |
| 09-09 23:38 | ½Ã´Ï¾î È¯Àý±â °Ç°­ | `openai/gpt-5-mini` | 0/7 | — | 0 | 1 | 1,267 | — |
| 09-09 23:39 | �ôϾ� ȯ���� �ǰ� ��� | `openai/gpt-5-mini` | 0/7 | — | 0 | 1 | 1,250 | — |
| 09-09 23:39 | 시니어 환절기 건강 관리 | `openai/gpt-5-mini` | 5/7 | ⭕ | 10 | 30 | 125,012 | list_past_publications → web_search → get_weather → web_search → web_search → fe |
| 09-09 23:55 | 시니어 환절기 옷차림과 낙상 예방 | `openai/gpt-5-mini` | 6/7 | ⭕ | 7 | 30 | 113,712 | list_past_publications → web_search → web_search → web_search → get_weather → fe |
| 09-10 00:10 | 시니어 환절기 옷차림 안내 | `openai/gpt-5-mini` | 6/7 | ⭕ | 9 | 30 | 114,081 | list_past_publications → web_search → web_search → get_weather → web_search → fe |
| 09-10 00:32 | 시니어 환절기 건강 수칙 | `openai/gpt-5-mini` | 7/7 | ⭕ | 7 | 27 | 87,128 | list_past_publications → web_search → web_search → web_search → fetch_article →  |

### 모델별 집계

| 모델 | 실행 | 카드 생성 | 사람 개입(평균) | 루프(평균) | 도구 실패 | 입력 토큰(평균) |
|---|---|---|---|---|---|---|
| `gemini/gemini-3-flash-preview` | 1 | 1/1 (100%) | 6.0 | 27.0 | 3 | 64,820 |
| `gemini/gemini-3.1-flash-lite` | 4 | 0/4 (0%) | 0.2 | 6.0 | 2 | 10,414 |
| `gemini/gemini-3.5-flash` | 4 | 0/4 (0%) | 0.0 | 6.2 | 2 | 8,766 |
| `gemini/gemini-3.5-flash-lite` | 13 | 0/13 (0%) | 0.4 | 8.5 | 2 | 17,364 |
| `gemini/gemini-3.6-flash` | 4 | 1/4 (25%) | 0.8 | 5.0 | 4 | 5,660 |
| `openai/gpt-5-mini` | 9 | 4/9 (44%) | 3.7 | 15.0 | 10 | 52,115 |

## 4. 실패 사례 — 어느 단계가 원인이었나

| 실패 라벨 | 횟수 | 어느 단계에서 주로 났나 |
|---|---|---|
| 도구오류 | 13 | 조사 (외부 키·한도) |
| 사실오류 | 5 | 조사 (외부 키·한도) |
| 문장어려움 | 3 | 조사 (외부 키·한도) |
| 중간포기 | 1 | 조사 (외부 키·한도) |
| 검색부실 | 1 | 조사 (외부 키·한도) |

### 관찰

- **조사 단계에서 실패가 몰린다.** 외부 키가 없거나 무료 한도에 걸리는 경우다.
  실패해도 에이전트가 사람에게 묻고 날씨로 방향을 틀어 카드를 완성했다
- **병목은 조사와 카드 합성**이다. 카드 합성은 5장에 1초 안쪽이라 실제 병목은 LLM 판단 시간이다
- 사람 개입은 설계상 4곳인데, 도구 실패 시 회복 질문이 추가로 붙는다

## 5. 다음에 바꿔 볼 것

| 세팅 | 가설 |
|---|---|
| 도구 description 을 짧게 | 도구 선택 정확도가 떨어질 것이다 — 근거를 남기려면 길어야 한다 |
| 단계 수를 7→5로 축소 | 사람 개입이 줄지만 스토리보드 품질이 떨어질 것이다 |
| 제목 길이 제한을 프롬프트에 명시 | 제목 줄바꿈이 줄어 카드가 깔끔해질 것이다 |

# EVAL — 실험과 평가

> 이 파일은 **자동 생성된다.** `uv run python scripts/make_eval.py`
> 숫자는 `runs/<실행ID>/outcome.json` 에서 계산한다. 손으로 적지 않는다.
>
> `runs/` 자체는 기기마다 다르고 절대경로가 들어가서 커밋하지 않는다. 대신 **완주한 실행
> 한 건을 경로만 지워 [`docs/sample-run/`](docs/sample-run/) 에 남겼다** — 아래 숫자가
> 어디서 나온 것인지 그 파일로 직접 확인할 수 있다.

측정한 실행: **37건**

## 1. 전체 지표

| 지표 | 정의 | 결과 |
|---|---|---|
| 카드 생성률 | 카드 파일이 실제로 만들어진 실행 | **8/37 (22%)** |
| 완주율 | 마지막 단계까지 끝난 실행 | 3/37 (8%) |
| 사람 개입 횟수 | 실행당 질문 수 (적을수록 좋다) | 평균 **1.5회** (최소 0 / 최대 10) |
| 루프 반복 | 실행당 판단 횟수 | 평균 10.5회 |
| 도구 실패 | 전체 도구 호출 중 실패 | 25건 / 400건 |

⚠️ **이 「도구 실패」 숫자를 그대로 믿으면 안 된다.** 안에 검토 에이전트의 반려 9건과
단계 허용 목록이 막은 4건이 섞여 있다 — 둘 다 도구가 깨진 게 아니라
설계가 작동한 기록이다. 갈라서 센 것은 4장에 있다.

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
| 주제 문자열이 깨져 들어옴 | 셸에서 한글을 URL 인코딩 없이 보내 요청 단계에서 손상됐다. **에이전트는 이를 알아채고 진행하지 않고 사람에게 물었다** | 클라이언트 쪽 문제라 요청 방식을 고쳤다. 실행 기록은 깨진 채로 남겨둔다 |
| **검색 결과가 모델에 안 갔다** | `ToolResult.data` 가 쓰이지 않았다. 저장되는 요약은 `→ 3건` 처럼 **건수만**(48자) 적어, 다음 반복부터 모델은 URL 을 본 적이 없었다 | 요약에 `제목 (게시일) URL` 을 싣고, 관찰 절단 길이를 도구별로 뒀다 (D-022) |
| **게시일 표기가 깨졌다** | Tavily 가 RFC-2822 를 주는데 앞 10자를 잘라 `Wed, 02 Se` 가 됐다 | `YYYY-MM-DD` 로 정규화. **날짜 대조가 함정 1번**이다 (D-022) |
| **경고가 뒤 단계로 새어나갔다** | 호출 횟수를 실행 전체로 세니, 단계1 의 *"그만하고 finish_step 하라"* 가 단계3 에도 실려 원문을 열기 전에 종료됐다 | 단계 안에서만 센다 (D-023) |
| 🔴 **게이트가 앞 단계 답변으로 충족됐다** | *"이미 답을 받았다면"* 이 어느 질문인지 구분하지 않아, 단계2(후보 선택)가 **질문 없이** 통과됐다. 단계4 는 물었다 — 비결정적으로 새는 구조 | 이 단계에서 물은 질문만 근거로 삼고, `finish_step` 을 **코드로 막았다** (D-023) |

**위쪽 다섯**은 카드가 만들어지는 것 자체를 막던 것들이다. 이것을 고친 뒤에야 첫 7/7 완주가 나왔다.
마지막 단계가 발송 승인이라 사람이 승인해야 `done` 이 되는 구조인 것도 맞다.

**나머지는 완주한 뒤에 발견한 것들**이다. 돌아가는 것과 제대로 돌아가는 것은 다르다.
쌓아둔 `trace.json` 을 다시 읽고, 완주를 여러 번 다시 시도하면서 찾았다.

🔴 **한 번 됐다고 되는 게 아니었다.** 첫 완주를 재현하려 했더니 **세 번 연속으로 실패했다.**
매번 다른 곳에서 막혔고, 막힌 자리마다 원인이 달랐다.
한 번의 성공은 고쳐야 할 것이 없다는 뜻이 아니라, **아직 안 눌러 본 곳이 있다는 뜻이었다.**

| 실행 | 모델 | 루프 | 도달 | 무슨 일이 있었나 |
|---|---|---|---|---|
| `run-93d74c2888e7` | `gemini-3-flash-preview` | 27 | **7/7** | 첫 완주 |
| `run-ca32f9d1e18d` | `gpt-5-mini` | 30 | 5/7 | 재현 시도 ① — 같은 질문 3회 반복으로 예산 소진 |
| `run-4605c934a58e` | `gpt-5-mini` | 30 | 6/7 | 재현 시도 ② — 발송이 지어낸 파일명을 찾다 실패 |
| `run-ce638ca65581` | `gpt-5-mini` | 30 | 6/7 | 재현 시도 ③ — 상한 자체가 부족 |
| `run-e5484e2520c7` | `gpt-5-mini` | 27 | **7/7** | 세 가지를 다 고친 뒤 다시 완주 |
| **`run-458cf2910262`** | `gemini-3.5-flash-lite` (폴백) | **25** | **7/7** | 🔴 **처음으로 dry-run 이 아닌 실제 발송까지** |

**완주 3건이 서로 다른 모델에서 나왔고 그중 둘은 제공자도 다르다.**
막힌 자리는 모델이 아니라 구조에 있었다는 뜻이다 — 실제로 고친 것 중 모델 쪽 문제는 하나도 없었다.
마지막 실행은 설정이 `gemini-3.5-flash` 였지만 한도에 걸려 **lite 로 갈아탄 채로 완주했다.**
폴백이 품질 저하가 아니라 **끝까지 가게 해 준 장치**로 작동한 첫 사례다.

### 마지막 한 칸은 실제로 보내 봐야 알 수 있었다

앞의 완주 2건은 마지막 단계가 **dry-run** 이었다. 화면에는 성공으로 찍힌다.
그런데 그 기록을 열어 보니 모델이 `image_paths` 에 **파일 5개가 아니라 폴더 경로 하나**를 넣었고,
폴더도 존재하는 경로라 그대로 통과해 *"카드 1장"* 으로 세어져 있었다.

```
"image_paths": ["…/output/run-e5484e2520c7"]   →  [dry-run] … 카드 1장
```

**실발송이었으면 폴더 주소를 이미지로 보내려다 통째로 실패했을 것이다.**
dry-run 이 이 실패를 가려 주고 있었다 — 켜 두면 안전하지만, **켜 둔 채로는 끝까지 확인되지 않는다.**

고친 방식은 앞서 파일명을 지어냈을 때와 같다. **모델에게 믿는 것은 「어느 실행 폴더인가」 까지고,
파일 목록은 앱이 직접 읽는다.** 그러고 나서야 카드 5장이 실제로 도착했다.

| | 앞의 완주 2건 | `run-458cf2910262` |
|---|---|---|
| 마지막 단계 | dry-run | **실제 발송** (메시지 6건 = 안내 1 + 카드 5) |
| `record_publication` | 안 부른 실행이 있었다 | 불렀다 (`id: 3`) |

`record_publication` 이 남았다는 것은 **다음 실행이 이 주제를 중복으로 걸러낸다**는 뜻이다.
MCP 서버가 도구를 노출하는 데서 끝나지 않고 되먹임을 만든 것도 이 실행에서 처음 확인됐다.

마지막 완주 실행이 실제로 무엇을 불렀는지 그대로 펼치면 이렇다.

```
단계1 조사      list_past_publications  ok    {"count": 1, "since": "2026-06-12", "publica
                get_weather             ok    서울 9월 10일 목요일 구름 조금 14.8~21.8도, 강수 0% (총 3일)
                web_search              ok    검색어='환절기 감기 예방 서울 강북구' 최근 7일 → 5건 1. 가을 환절기,
                web_search              ok    검색어='서울 강북구 보건소 독감 예방접종 무료 2026' 최근 30일 → 10
                web_search              ok    검색어='강북구 보건소 독감 예방접종 무료 2026' 최근 30일 → 1건 1.
                finish_step             ok    환절기 감기 예방 및 독감 무료접종 관련 최근 소식과 서울 강북구 날씨(9월 1
단계2 후보 선택 ask_human               ok    질문: 이번 강북구 환절기 감기 카드뉴스에 실을 소식을 골라주세요.
                finish_step             ok    사용자가 카드뉴스 주제로 '1. 환절기 아침저녁 쌀쌀한 날씨 옷차림과 물 마시기
단계3 심층 검증 web_search              반려  web_search 은 이 단계에서 쓸 수 없다. 허용: fetch_articl
                fetch_article           ok    원문 확인: '≪케이에스피뉴스≫ 남양주시 동부보건소, 어르신 환절기 건강 지킨다
                fetch_article           ok    원문 확인: 'KH메디체크 건강관리협회 충북세종지부 청주건강검진 봉명사거리 on
                fetch_article           ok    원문 확인: '“추워지기 전에 미리”...동대문구, 독감 무료 예방접종 21일 
                finish_step             ok    환절기 감기 아침저녁 쌀쌀한 날씨 대비 및 독감 관련 기사 3건의 원문을 fet
단계4 스토리보드get_audience_profile    ok    {"who": "60~80대 시니어. 경로당·복지관·시니어 채널을 통해 안내를 
                get_card_template       ok    {"size": {"width": 1080, "height": 1350, "no
                ask_human               ok    질문: [환절기 아침저녁 쌀쌀한 날씨 옷차림과 물 마시기 수칙] 5장 스토리보드
                finish_step             ok    환절기 아침저녁 쌀쌀한 날씨 옷차림과 물 마시기 수칙 5장 스토리보드 계획안에 
단계5 카드 합성 compose_cards           ok    카드 5장 생성·검증 완료 → …\output\run-458cf2910262
                검토에이전트            ok    모든 검사 기준을 통과했습니다.
                finish_step             ok    승인된 스토리보드(환절기 아침저녁 쌀쌀한 날씨 옷차림과 물 마시기 수칙)를 바탕
단계6 검수      ask_human               ok    질문: 완성된 카드뉴스 5장을 확인해주세요. 이대로 발행을 진행할까요?
                finish_step             ok    사용자가 완성된 카드뉴스 5장의 발행을 승인하여 검수 단계를 완료했습니다.
단계7 발송      ask_human               ok    질문: 완성된 환절기 감기 카드뉴스(총 5장)를 LINE으로 발송하시겠습니까? 
                send_line               ok    실제 발송 완료 — 메시지 6건 (카드 5장)
                record_publication      ok    {"ok": true, "id": 3, "published_at": "2026-
                finish_step             ok    강북구 환절기 감기 카드뉴스 5장의 LINE 발송을 완료하고 발행 이력을 기록했
```

여기서 볼 것 셋.

- **단계5 → 단계4 로 되돌아간다.** 검토 에이전트가 반려하자 스토리보드를 고치고 다시 합성했다.
  정해진 순서대로 한 번씩 흐르는 파이프라인이었다면 나올 수 없는 자국이다
- **`fetch_article` 이 원문을 열고 게시일을 확인했다** (2026-09-07 · 2025-09-24).
  한 건은 작년 글이라는 것도 이때 드러났다. 검색 결과 요약만 봤으면 몰랐을 일이다 —
  **요약만 보고 검증했다고 하지 않는다**는 것이 이 프로젝트가 계속 경계한 함정이다
- **사람에게 4번 물었다.** 설계상 개입 지점은 4곳인데,
  자료가 부족할 때 묻는 회복 질문이 붙었다

## 2. 세팅 비교 — 제공자와 모델을 바꿔 가며

```bash
uv run python scripts/compare_settings.py --repeat 3          # 전부
uv run python scripts/compare_settings.py --only openai --repeat 3
```

같은 주제·지역으로 **세팅만 바꿔** 첫 사람 개입 지점까지 돌린 결과다.
끝까지 돌리지 않는 이유는 무료 한도(모델당 하루 20회, D-016) 때문이고,
비교에 필요한 건 **같은 조건에서의 판단**이지 완주 여부가 아니다.

### 같은 세팅을 3회 이상씩 쟀다

한 번씩만 재면 **모델 간 차이인지 그날의 운인지 구분할 수 없다.**
LLM 은 같은 입력에도 다르게 답한다.

아래 표에는 **같은 방법으로 잰 실행만** 넣었다 — 첫 사람 개입 지점까지(반복 8회 상한).
끝까지 간 실행을 섞으면 세팅 차이가 아니라 측정 방법 차이를 재게 된다.

**주제: 시니어 환절기 건강 관리**

| 설정한 세팅 | n | 루프 평균 | 루프 폭 | 입력 토큰 평균 | 출력 토큰 평균 | 폴백 | 비용 |
|---|---|---|---|---|---|---|---|
| `gemini/gemini-3.1-flash-lite` | 4 | 6.0 | 2 | 10,414 | 359 | — | 무료 |
| `gemini/gemini-3.5-flash` | 4 | 6.0 | 4 | 11,984 | 321 | 3/4 | 무료 |
| `gemini/gemini-3.5-flash-lite` | 4 | 5.2 | 5 | 9,332 | 296 | — | 무료 |
| `openai/gpt-5-mini` | 3 | 5.3 | 1 | 8,861 | 3,684 | — | $0.0288 |

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
- **제공자 간 차이가 모델 간 차이보다 컸다.** `gpt-5-mini` 는 출력 토큰 평균이
  Gemini 계열의 **10배 안팎**이다(3,684 vs 296~359). 추론 토큰을 쓰기 때문이다.
  반대로 **입력 토큰은 넷 중 가장 적다** — 루프 수는 lite 계열과 비슷한데도 그렇다.
  **"토큰이 많다/적다" 는 제공자를 섞으면 같은 뜻이 아니다.**
  값을 견주려면 토큰이 아니라 달러로 봐야 한다
- **도구 선택 순서는 제공자를 가리지 않았다.** 위 표의 Gemini 3종과 OpenAI 모두
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

**여기에는 끝까지 간 실행도 섞여 있다.** 도구를 어떤 차례로 골랐는지는 완주한 실행에서만
보이기 때문이다. 어느 쪽으로 잰 것인지 「어디까지」 열에 적었다 —
`첫 개입까지` 행끼리만 서로 견줄 수 있다.

**주제: 이번 주 시니어 건강·생활 정보** — 같은 주제·지역, 모델만 바꿈

| 모델 | 어디까지 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 12,267 | 350 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 13,824 | 379 | list_past_publications → web_search → web_search → get_weather → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 12,524 | 345 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.6-flash` | 첫 개입까지 | 2 | 2,110 | 63 | get_weather → web_search✗ |
| `gemini-3.6-flash` | 5/7 | 11 | 14,290 | 1,281 | web_search✗ → get_weather → compose_cards |

**주제: 시니어 환절기 건강 관리** — 같은 주제·지역, 모델만 바꿈

| 모델 | 어디까지 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|---|
| `gemini-3.1-flash-lite` | 첫 개입까지 | 6 | 9,245 | 463 | list_past_publications → web_search✗ → get_weather → list_past_publications |
| `gemini-3.1-flash-lite` | 첫 개입까지 | 5 | 8,483 | 310 | list_past_publications → web_search → get_weather |
| `gemini-3.1-flash-lite` | 첫 개입까지 | 7 | 13,858 | 355 | list_past_publications → web_search → get_weather → web_search → web_search |
| `gemini-3.1-flash-lite` | 첫 개입까지 | 6 | 10,072 | 309 | list_past_publications → web_search → get_weather → web_search |
| `gemini-3.5-flash` | 첫 개입까지 | 3 | 4,129 | 88 | list_past_publications → get_weather → web_search✗ |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 2 | 2,664 | 60 | list_past_publications → web_search✗ |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 13,936 | 361 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 14,865 | 427 | list_past_publications → web_search → get_weather → web_search → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 15,005 | 408 | list_past_publications → web_search → get_weather → web_search → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 5 | 8,214 | 251 | list_past_publications → get_weather → web_search → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 13,020 | 422 | list_past_publications → get_weather → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 첫 개입까지 | 7 | 13,432 | 449 | list_past_publications → get_weather → web_search → web_search → web_search |
| `openai/gpt-5-mini` | 첫 개입까지 | 5 | 8,010 | 3,321 | list_past_publications → web_search → web_search → web_search |
| `openai/gpt-5-mini` | 첫 개입까지 | 5 | 8,510 | 3,964 | list_past_publications → web_search → web_search → get_weather |
| `openai/gpt-5-mini` | 첫 개입까지 | 6 | 10,064 | 3,768 | list_past_publications → web_search → web_search → web_search → get_weather |
| `openai/gpt-5-mini` | 5/7 | 30 | 125,012 | 54,186 | list_past_publications → web_search → get_weather → web_search → web_search → fetch_article → fetch_article → fetch_article✗ → get_audience_profile → get_card_template → compose_cards → 검토에이전트✗ → compose_cards → 검토에이전트✗ → compose_cards → 검토에이전트 |

**주제: 시니어 독감 예방접종 안내** — 같은 주제·지역, 모델만 바꿈

| 모델 | 어디까지 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|---|
| `gemini-3-flash-preview` | 7/7 | 27 | 64,820 | 6,283 | list_past_publications → web_search → web_search → get_weather → web_search → fetch_article✗ → web_search✗ → get_audience_profile → get_card_template → compose_cards → 검토에이전트✗ → get_audience_profile → compose_cards → 검토에이전트 → record_publication |
| `gemini-3.5-flash` | 첫 개입까지 | 2 | 1,252 | 29 | list_past_publications |
| `gemini-3.5-flash` | 1/7 | 17 | 25,749 | 792 | list_past_publications → web_search → get_weather → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search → web_search |
| `gemini-3.5-flash-lite` | 4/7 | 20 | 33,373 | 966 | list_past_publications → web_search → web_search → get_weather → web_search → web_search → web_search → web_search → web_search → web_search → web_search → get_audience_profile → get_card_template |

**주제: (주제 깨짐 — 요청 인코딩)** — 같은 주제·지역, 모델만 바꿈

| 모델 | 어디까지 | 루프 | 입력 토큰 | 출력 토큰 | 도구 호출 순서 |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 3/7 | 16 | 44,950 | 1,110 | list_past_publications → web_search → get_weather → web_search → web_search → web_search✗ → fetch_article → fetch_article → fetch_article → get_audience_profile → get_card_template |
| `openai/gpt-5-mini` | 첫 개입까지 | 1 | 1,267 | 998 | — |

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
| 09-09 15:50 | (주제 깨짐 — 요청 인코딩) | `gemini-3.5-flash-lite` | 3/7 | — | 1 | 12 | 27,655 | list_past_publications → web_search → web_search → web_search → get_weather → ge |
| 09-09 15:58 | (주제 깨짐 — 요청 인코딩) | `gemini-3.5-flash-lite` | 3/7 | — | 1 | 16 | 44,950 | list_past_publications → web_search → get_weather → web_search → web_search → we |
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
| 09-09 23:38 | (주제 깨짐 — 요청 인코딩) | `openai/gpt-5-mini` | 0/7 | — | 0 | 1 | 1,267 | — |
| 09-09 23:39 | (주제 깨짐 — 요청 인코딩) | `openai/gpt-5-mini` | 0/7 | — | 0 | 1 | 1,250 | — |
| 09-09 23:39 | 시니어 환절기 건강 관리 | `openai/gpt-5-mini` | 5/7 | ⭕ | 10 | 30 | 125,012 | list_past_publications → web_search → get_weather → web_search → web_search → fe |
| 09-09 23:55 | 시니어 환절기 옷차림과 낙상 예방 | `openai/gpt-5-mini` | 6/7 | ⭕ | 7 | 30 | 113,712 | list_past_publications → web_search → web_search → web_search → get_weather → fe |
| 09-10 00:10 | 시니어 환절기 옷차림 안내 | `openai/gpt-5-mini` | 6/7 | ⭕ | 9 | 30 | 114,081 | list_past_publications → web_search → web_search → get_weather → web_search → fe |
| 09-10 00:32 | 시니어 환절기 건강 수칙 | `openai/gpt-5-mini` | 7/7 | ⭕ | 7 | 27 | 87,128 | list_past_publications → web_search → web_search → web_search → fetch_article →  |
| 09-10 02:38 | 이번주 인공지능 뉴스 | `gemini-3.5-flash-lite` | 6/7 | ⭕ | 3 | 21 | 75,554 | list_past_publications → web_search → get_weather → web_search → web_search → fe |
| 09-10 03:02 | 환절기 감기 | `gemini-3.5-flash-lite` | 7/7 | ⭕ | 4 | 25 | 75,648 | list_past_publications → get_weather → web_search → web_search → web_search → we |

### 모델별 집계

| 모델 | 실행 | 카드 생성 | 사람 개입(평균) | 루프(평균) | 도구 실패 | 입력 토큰(평균) |
|---|---|---|---|---|---|---|
| `gemini/gemini-3-flash-preview` | 1 | 1/1 (100%) | 6.0 | 27.0 | 3 | 64,820 |
| `gemini/gemini-3.1-flash-lite` | 4 | 0/4 (0%) | 0.2 | 6.0 | 2 | 10,414 |
| `gemini/gemini-3.5-flash` | 4 | 0/4 (0%) | 0.0 | 6.2 | 2 | 8,766 |
| `gemini/gemini-3.5-flash-lite` | 15 | 2/15 (13%) | 0.8 | 10.5 | 4 | 25,129 |
| `gemini/gemini-3.6-flash` | 4 | 1/4 (25%) | 0.8 | 5.0 | 4 | 5,660 |
| `openai/gpt-5-mini` | 9 | 4/9 (44%) | 3.7 | 15.0 | 10 | 52,115 |

⚠️ **「카드 생성」 열로 모델을 줄 세우지 말 것.** Gemini 행 대부분은 2장의 비교 실험이라
**첫 사람 개입 지점에서 일부러 멈춘 실행**이다. 카드까지 갈 기회가 없었지 못 간 게 아니다.
끝까지 돌린 실행은 손에 꼽고, 그건 1장의 완주 표에 있다.

## 4. 실패 사례 — 어느 단계가 원인이었나

| 실패 라벨 | 횟수 | 어느 단계에서 났나 |
|---|---|---|
| 도구오류 | 14 | 단계1 조사(8건), 단계3 심층 검증(4건), 단계7 발송(2건) |
| 사실오류 | 5 | 단계5 카드 합성(5건) |
| 문장어려움 | 4 | 단계5 카드 합성(4건) |
| 중간포기 | 1 | 단계1 조사(1건) |
| 검색부실 | 1 | 단계1 조사(1건) |

### 라벨 안을 열어 보면

| 라벨 | 도구 | 단계 | 횟수 | 대표 메시지 |
|---|---|---|---|---|
| 도구오류 | `web_search` | 1 조사 | 7 | TAVILY_API_KEY 가 없다 |
| 사실오류 | `검토에이전트` | 5 카드 합성 | 5 | 카드 2에 기재된 접종 기간(2026-09-04~2026-11-30)은 제공된 근거에서 확인되지 않아 사실오류가 있 _(사유 5종)_ |
| 문장어려움 | `검토에이전트` | 5 카드 합성 | 4 | 날짜와 수치는 정확하나, '의료기관', '지참' 등 시니어에게 생소한 행정 용어가 포함되었고 마지막 카드에 두 가지 _(사유 4종)_ |
| 도구오류 | `web_search` | 3 심층 검증 | 3 | web_search 은 이 단계에서 쓸 수 없다. 허용: fetch_article, get_weather |
| 도구오류 | `send_line` | 7 발송 | 2 | 보낼 파일이 없다: ['…\\output\\run-4605c934a58e\\card1.png', '…\\output |
| 중간포기 | `판단` | 1 조사 | 1 | 관찰 결과, '환절기 건강 지키는 생활 수칙' 주제는 오늘(9월 9일) 이미 발행된 것으로 확인됩니다. 중복 내용을 |
| 검색부실 | `web_search` | 1 조사 | 1 | [주입된 실패] 검색 결과 0건 |
| 도구오류 | `fetch_article` | 1 조사 | 1 | fetch_article 은 이 단계에서 쓸 수 없다. 허용: web_search, get_weather, list |
| 도구오류 | `fetch_article` | 3 심층 검증 | 1 | 본문 추출 실패 — 미확인 처리: https://www.safekorea.go.kr |

### 관찰

- **`도구오류` 14건 중 4건은 고장이 아니라 방어가 작동한 것이다.**
  단계에 없는 도구를 이름만 대고 불렀고 코드가 막았다. 라벨 한 줄만 보면 도구가
  깨진 것처럼 읽히는데, 열어 보면 **설계대로 막힌 기록**이다.
  나머지 10건이 진짜 실패다 — 키 없음 7 · 본문 추출 실패 1 · 지어낸 파일명 2
- 🔴 **뒤늦게 드러난 쪽이 더 중요하다.** 카드 합성 단계의 9건은 도구가 아니라
  **검토 에이전트가 잡아낸 것**이다. 그중 `사실오류` 5건은 **4건이 근거에 없는 기상 수치**,
  1건은 근거에 없는 접종 기간이었다. 이 9건 모두 도구는 성공했고 파일도 멀쩡히 만들어졌다.
  검토를 안 붙였으면 그대로 나갔다 — **"도구가 성공했다" 와 "내용이 맞다" 는 다르다**
- **검토 에이전트는 16번 판정해 9번 반려했다** (통과율 44%).
  만든 것과 같은 모델에게 보게 했는데도 반려가 났다 —
  역할과 프롬프트를 나눈 것만으로 잡힌다
- **시간 병목은 조사 한 곳이다.** **조사** 33/35건 (합 353초) · **심층 검증** 2/35건 (합 29초).
  카드 합성은 5장에 1초 안쪽이라 병목이 된 적이 없다. 남는 시간은 검색 응답과 LLM 판단이다
- 사람 개입은 설계상 4곳인데, 도구 실패 시 회복 질문이 추가로 붙는다

## 5. 다음에 바꿔 볼 것

| 세팅 | 가설 |
|---|---|
| 도구 description 을 짧게 | 도구 선택 정확도가 떨어질 것이다 — 근거를 남기려면 길어야 한다 |
| 단계 수를 7→5로 축소 | 사람 개입이 줄지만 스토리보드 품질이 떨어질 것이다 |
| 제목 길이 제한을 프롬프트에 명시 | 제목 줄바꿈이 줄어 카드가 깔끔해질 것이다 |

"""에이전트가 호출할 도구 — 3단계에서 채운다.

각 도구는 입력·출력 스키마와 실패 처리 규칙을 함께 정의한다 (루브릭 2번).

  search.py   웹 검색     Tavily        읽기 전용
  fetch.py    원문 조회   httpx+trafilatura  읽기 전용
  weather.py  날씨 조회   Open-Meteo    읽기 전용, 키 불필요
  image.py    배경 생성   Antigravity CLI    실패 시 대체 배경으로 자동 전환
  compose.py  카드 합성   Pillow        output/<실행ID>/ 안으로만 쓰기
  line.py     발송        기본 dry-run. 실발송은 승인+환경변수 둘 다 (D-005)
"""

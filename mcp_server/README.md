# senior-cardnews-mcp

시니어 카드뉴스 **운영 데이터**를 MCP 도구로 노출하는 서버.

## 왜 만들었나

도구를 하나 더 붙이려고 만든 게 아니라 **에이전트가 판단할 근거를 늘리려고** 만들었다.

```
후보 12개 수집 → 과거 발행 이력 조회 → "독감 예방접종은 3주 전에 이미 다뤘다"
              → 판단: 후순위로 내리고 사람에게 알림
```

`record_publication` 이 남긴 것이 다음 실행의 입력이 되므로 **사이클**이 만들어진다.

## 노출하는 도구 4개

| 도구 | 하는 일 | 권한 |
|---|---|---|
| `list_past_publications` | 과거 발행 이력 조회 (기간·키워드) | 읽기 |
| `get_audience_profile` | 시니어 독자 특성 — 금지 표현, 글자 크기 하한, 관심 주제 | 읽기 |
| `get_card_template` | 카드 양식 — 색·레이아웃·문구 규칙 | 읽기 |
| `record_publication` | 발행 결과 기록 | 쓰기 (이 저장소만) |

## 실행

stdio 로 붙는다. 웹앱과 같은 호스트에서 띄우므로 배포 시 프로세스가 늘지 않는다.

```bash
uv run python -m mcp_server.server
```

Claude Desktop 등 다른 MCP 클라이언트에서 쓰려면:

```json
{
  "mcpServers": {
    "senior-cardnews": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"],
      "cwd": "<저장소를 클론한 경로>/senior-cardnews-agent"
    }
  }
}
```

## 데이터

앱과 같은 SQLite 파일(`data/app.db`)의 `publications` 테이블을 쓴다.
독자 특성과 카드 양식은 `profile.py` 에 있고, 값을 바꾸면 카드 합성과 문구가 함께 바뀐다.

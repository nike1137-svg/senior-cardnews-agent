"""완주한 실행 하나를 저장소에 남긴다 — `docs/sample-run/`.

`runs/` 는 `.gitignore` 대상이다. 기기마다 쌓이는 것이 다르고, 절대경로가 들어가기 때문이다.
그런데 `EVAL.md` 는 *"숫자는 outcome.json 에서 계산한다"* 고 적어 놓고, 정작 그 파일이
저장소에 없었다. **검증할 수 없는 증거는 증거가 아니다.** 그래서 완주한 실행 한 건만
경로를 지워서 커밋한다.

    uv run python scripts/export_sample_run.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "docs" / "sample-run"

USER_DIR = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\"\s]+")


def scrub(value):
    """절대경로를 지운다. 공개 저장소에 계정 이름이 남으면 안 된다."""
    if isinstance(value, str):
        root = str(BASE)
        for form in (root, root.replace("\\", "\\\\"), root.replace("\\", "/")):
            value = value.replace(form, "<프로젝트>")
        return USER_DIR.sub("<홈>", value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def pick() -> Path:
    """가장 최근에 완주한 실행을 고른다."""
    done = []
    for p in (BASE / "runs").glob("*/outcome.json"):
        try:
            o = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if o.get("completed"):
            done.append((o.get("started_at") or "", p.parent))
    if not done:
        raise SystemExit("완주한 실행이 없다. 먼저 한 건을 끝까지 돌릴 것")
    return sorted(done)[-1][1]


if __name__ == "__main__":
    src = pick()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("trace.json", "outcome.json"):
        f = src / name
        if not f.exists():
            continue
        data = scrub(json.loads(f.read_text(encoding="utf-8")))
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"{name} ← {src.name}")

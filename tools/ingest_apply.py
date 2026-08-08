#!/usr/bin/env python3
"""ingest_apply.py — 에이전트가 만든 분류안(plan.jsonl)을 실제로 적용한다.

안전 규칙 (전부 강제됨)
  - 기본 동작은 **복사**. 원본은 그 자리에 그대로 남는다. move는 --allow-move 필요.
  - 목적지가 워크스페이스 밖이면 거부한다.
  - 이미 있는 파일은 덮어쓰지 않는다. `이름 (2).ext` 로 비켜 쓴다.
  - 시크릿 플래그가 붙은 항목은 plan에 있어도 무조건 skip 한다.
  - 무엇을 했는지 ingest/applied.jsonl 에 전부 남긴다. 되돌릴 근거가 된다.

plan.jsonl 한 줄 형식
    {"path": "/원본/절대경로",
     "action": "copy" | "skip" | "move",
     "dest": "30_KNOWLEDGE/2024/계약/무슨무슨_계약서.pdf",
     "reason": "왜 여기로 보내는지 한 줄"}

사용법
    python3 tools/ingest_apply.py --plan ingest/plan.jsonl --dry-run
    python3 tools/ingest_apply.py --plan ingest/plan.jsonl
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingest_scan import extract_text, scan_secrets  # noqa: E402  (같은 폴더)

WORKSPACE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ALLOWED_ROOTS = ("00_COMPANY", "10_ROLES", "20_PLAYBOOKS", "30_KNOWLEDGE",
                 "40_ASSETS", "50_PROJECTS", "60_SYSTEMS", "80_ARCHIVE",
                 "ingest/_UNSORTED")


def resolve_dest(dest):
    """목적지를 워크스페이스 내부로 한정한다. 벗어나면 None."""
    if os.path.isabs(dest):
        return None
    full = os.path.abspath(os.path.join(WORKSPACE, dest))
    if not full.startswith(WORKSPACE + os.sep):
        return None
    rel = os.path.relpath(full, WORKSPACE)
    if not rel.replace(os.sep, "/").startswith(ALLOWED_ROOTS):
        return None
    return full


def digest(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def nonclobbering(src, dest):
    """이미 있으면 비켜 쓴다. 단 내용이 같으면 None — 재적재하지 않는다.

    같은 plan을 두 번 돌려도 사본이 늘어나지 않아야 한다. 흡수 절차는 자료가
    추가될 때마다 반복 실행되는 것이 정상이기 때문이다.
    """
    if not os.path.exists(dest):
        return dest
    src_d = digest(src)
    base, ext = os.path.splitext(dest)
    i = 1
    cand = dest
    while os.path.exists(cand):
        if src_d and digest(cand) == src_d:
            return None       # 동일 내용이 이미 있다
        i += 1
        cand = f"{base} ({i}){ext}"
    return cand


def has_secret(src, plan_flags):
    """plan이 flags를 빠뜨렸어도 여기서 다시 잡는다 (방어 이중화).

    대상: 자격증명·주민번호 + 인사/급여/근로계약(policy/scope.md 범위 밖).

    분류안을 만드는 쪽이 플래그를 옮겨 적는 걸 잊는 일은 반드시 생긴다.
    자격증명·주민번호 적재는 되돌릴 수 없으므로 적용 단계에서 독립적으로 재확인한다.
    """
    if plan_flags and any(f.get("severity") == "high" for f in plan_flags):
        return True
    try:
        size = os.path.getsize(src)
    except OSError:
        return False
    ext = os.path.splitext(src)[1].lower()
    preview, _ = extract_text(src, ext, 8000, size)
    return any(f["severity"] == "high"
               for f in scan_secrets(preview, os.path.basename(src)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-move", action="store_true",
                    help="원본 이동 허용 (기본은 복사만)")
    args = ap.parse_args()

    if not os.path.exists(args.plan):
        sys.exit(f"plan 파일 없음: {args.plan}")

    log_path = os.path.join(WORKSPACE, "ingest", "applied.jsonl")
    stats = {"copied": 0, "moved": 0, "skipped": 0, "rejected": 0, "already": 0}
    log = []

    with open(args.plan, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                print(f"  ! {lineno}행 JSON 파싱 실패, 건너뜀")
                stats["rejected"] += 1
                continue

            src = item.get("path", "")
            action = item.get("action", "copy")
            dest = item.get("dest", "")

            if action == "skip":
                stats["skipped"] += 1
                continue
            if not os.path.isfile(src):
                print(f"  ! 원본 없음: {src}")
                stats["rejected"] += 1
                continue
            if has_secret(src, item.get("flags")):
                print(f"  ⛔ 적재 금지 검출(자격증명·개인정보·인사/급여) — 강제 skip: {src}")
                stats["skipped"] += 1
                continue

            full = resolve_dest(dest)
            if full is None:
                print(f"  ⛔ 목적지 거부(워크스페이스 밖이거나 허용 폴더 아님): {dest}")
                stats["rejected"] += 1
                continue
            if action == "move" and not args.allow_move:
                print(f"  ! move 요청이지만 --allow-move 없음 → copy로 처리: {dest}")
                action = "copy"

            full = nonclobbering(src, full)
            if full is None:
                stats["already"] += 1
                continue
            if args.dry_run:
                print(f"  [dry] {action} → {os.path.relpath(full, WORKSPACE)}")
            else:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                if action == "move":
                    shutil.move(src, full)
                else:
                    shutil.copy2(src, full)
            stats["moved" if action == "move" else "copied"] += 1
            log.append({"ts": datetime.now().astimezone().isoformat(),
                        "action": action, "src": src,
                        "dest": os.path.relpath(full, WORKSPACE),
                        "reason": item.get("reason", "")})

    if log and not args.dry_run:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for row in log:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print("\n" + ("[DRY RUN] " if args.dry_run else "") +
          f"복사 {stats['copied']} · 이동 {stats['moved']} · "
          f"건너뜀 {stats['skipped']} · 이미있음 {stats['already']} · "
          f"거부 {stats['rejected']}")
    if not args.dry_run and log:
        print(f"기록: {os.path.relpath(log_path, WORKSPACE)}")
    print("\n다음: 적재한 문서마다 30_KNOWLEDGE/cards/ 에 색인 카드를 쓰세요. "
          "카드 없는 문서는 나중에 검색되지 않습니다.")


if __name__ == "__main__":
    main()

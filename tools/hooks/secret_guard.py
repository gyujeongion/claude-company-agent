#!/usr/bin/env python3
"""PreToolUse 훅 — 자격증명 파일 접근을 물리적으로 차단한다.

왜 필요한가: "키를 출력하지 마세요"는 산문 규칙이라 세션이 길어지면 희석된다.
이 훅은 도구 호출 단계에서 거부하므로 희석되지 않는다.

차단 대상
  - Read / Edit / Write 의 file_path 가 자격증명 파일
  - Bash 명령이 자격증명 파일을 cat·less·head·grep 등으로 여는 경우

차단하지 않는 것: 존재 여부 확인(ls), 경로 언급. 일을 못 하게 만들면 사람들이
훅을 꺼버린다 — 실제로 값이 새는 경로만 막는다.

입출력은 Claude Code PreToolUse 훅 규약을 따른다.
"""

import json
import re
import sys

SECRET_PATH = re.compile(
    r"""(?ix)
    (^|/)\.env(\.|$)
  | \.(pem|key|p12|pfx|jks|keystore)$
  | (^|/)(id_rsa|id_ed25519|id_ecdsa)$
  | credentials?[./_-]
  | (^|/)secrets?[./_-]
  | \.aws/credentials
  | \.ssh/(id_|config$)
  | service[_-]account.*\.json$
  | token(s)?\.json$
""")

READ_CMD = re.compile(r"(?i)\b(cat|bat|less|more|head|tail|open|strings|xxd|cp|"
                      r"grep|rg|awk|sed|python3?\s|source|\.)\b")

DENY = ("자격증명 파일 접근은 이 워크스페이스에서 차단됩니다 "
        "(00_COMPANY/policy/security.md). 키·토큰·비밀번호는 워크스페이스에 "
        "적재하지도, 대화에 출력하지도 않습니다. 값이 필요하면 사람이 직접 "
        "안전한 경로로 전달해야 합니다. 대상: {target}")


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}

    if tool in {"Read", "Edit", "Write", "NotebookEdit"}:
        target = inp.get("file_path") or inp.get("notebook_path") or ""
        if target and SECRET_PATH.search(target):
            deny(DENY.format(target=target))
        return

    if tool == "Bash":
        cmd = inp.get("command", "")
        if SECRET_PATH.search(cmd) and READ_CMD.search(cmd):
            deny(DENY.format(target=cmd[:120]))
        return


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 훅이 깨져도 대화를 막아선 안 된다

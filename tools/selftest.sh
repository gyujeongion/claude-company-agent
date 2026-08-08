#!/usr/bin/env bash
# selftest.sh — 이 워크스페이스의 안전장치가 실제로 작동하는지 확인한다.
#
# 왜 필요한가: 훅과 스캐너는 "문서에 그렇게 적혀 있다"가 아니라 "돌려봤더니 막더라"로
# 확인해야 한다. 설치 직후·git pull 직후·훅을 고친 뒤에 돌린다.
#
#   bash tools/selftest.sh
#
# 워크스페이스를 더럽히지 않는다: 픽스처는 임시 폴더에 만들고, 적재 테스트는
# ingest/_UNSORTED/ 에만 쓴 뒤 지운다.
set -uo pipefail
cd "$(dirname "$0")/.."
WS="$PWD"

pass=0; fail=0
ok()   { printf "  \033[32mPASS\033[0m  %s\n" "$1"; pass=$((pass+1)); }
no()   { printf "  \033[31mFAIL\033[0m  %s\n" "$1"; fail=$((fail+1)); }
head_() { printf "\n\033[1m%s\033[0m\n" "$1"; }

FIX=$(mktemp -d)
OUT=$(mktemp -d)
trap 'rm -rf "$FIX" "$OUT"' EXIT

# ── 픽스처 ───────────────────────────────────────────────────────────────────
mkdir -p "$FIX/일반" "$FIX/민감"
printf '거래처 A 용역 계약. 기간 2026-01-01~12-31.\n'          > "$FIX/일반/거래처계약_메모.txt"
printf '# 캠페인 결과\nCTR 2.4%%\n'                              > "$FIX/일반/캠페인결과.md"
printf 'OPENAI_API_KEY=sk-FAKEKEYFORSELFTESTONLY000000\n'   > "$FIX/민감/.env.production"
printf '홍길동 주민등록번호 900101-1234567\n'                    > "$FIX/민감/신원확인.txt"
printf '2026년 3월 급여명세서\n기본급 3,000,000원 식대수당 200,000원\n' > "$FIX/민감/급여명세서.txt"
printf '근로계약서\n제1조 임금은 연봉으로 정한다.\n'              > "$FIX/민감/근로계약서.txt"

# ── 1. git 추적 범위 ─────────────────────────────────────────────────────────
head_ "1. git 추적 범위 (.gitignore)"
if git rev-parse --git-dir >/dev/null 2>&1; then
    for f in tools/hooks/secret_guard.py tools/hooks/boundary_gate.py tools/ingest_scan.py; do
        if git check-ignore -q "$f" 2>/dev/null; then
            no "$f 가 제외됨 — 클론하면 이 파일이 없습니다"
        else ok "$f 추적됨"; fi
    done
    for f in 90_ME/profile.md 90_ME/personal/x.md; do
        if git check-ignore -q "$f" 2>/dev/null; then ok "$f 제외됨 (개인 레이어)"
        else no "$f 가 추적 대상 — 개인 파일이 커밋될 수 있습니다"; fi
    done
else
    echo "  (git 레포가 아님 — 건너뜀)"
fi

# ── 2. 훅 ───────────────────────────────────────────────────────────────────
head_ "2. 훅 동작"
hook_denies() {  # $1=tool_json  → deny 나오면 0
    echo "$1" | python3 tools/hooks/secret_guard.py 2>/dev/null | grep -q '"deny"'
}
if hook_denies '{"tool_name":"Read","tool_input":{"file_path":"/x/.env"}}'; then
    ok "secret_guard: .env 읽기 차단"; else no "secret_guard: .env 를 막지 못함"; fi
if hook_denies '{"tool_name":"Bash","tool_input":{"command":"cat ~/.ssh/id_rsa"}}'; then
    ok "secret_guard: 개인키 cat 차단"; else no "secret_guard: 개인키 cat 을 막지 못함"; fi
if hook_denies '{"tool_name":"Read","tool_input":{"file_path":"30_KNOWLEDGE/INDEX.md"}}'; then
    no "secret_guard: 정상 파일까지 차단 (오탐)"; else ok "secret_guard: 정상 파일은 통과"; fi

gate_hits() { echo "{\"prompt\":\"$1\"}" | python3 tools/hooks/boundary_gate.py 2>/dev/null | grep -q "$2"; }
if gate_hits "직원 급여 정리해줘" "범위 밖"; then ok "boundary_gate: 인사·급여 감지"
else no "boundary_gate: 인사·급여를 감지 못함"; fi
if gate_hits "조직도 알려줘" "범위 밖"; then ok "boundary_gate: 조직 정보 감지"
else no "boundary_gate: 조직 정보를 감지 못함"; fi
if gate_hits "거래처에 메일 보내줘" "외부로 나가는"; then ok "boundary_gate: 외부 발송 감지"
else no "boundary_gate: 외부 발송을 감지 못함"; fi
if [ -z "$(echo '{"prompt":"이번 캠페인 결과 정리해줘"}' | python3 tools/hooks/boundary_gate.py 2>/dev/null)" ]; then
    ok "boundary_gate: 일반 업무엔 무반응"; else no "boundary_gate: 일반 업무에 오탐"; fi

# ── 3. 스캐너 ───────────────────────────────────────────────────────────────
head_ "3. INGEST 스캐너"
python3 tools/ingest_scan.py "$FIX" --out "$OUT" >/dev/null 2>&1
if [ -f "$OUT/manifest.jsonl" ]; then ok "스캔 완료 (manifest 생성)"
else no "스캔 실패"; fi

flag_of() { python3 -c "
import json,sys
for l in open('$OUT/manifest.jsonl'):
    r=json.loads(l)
    if r['name']==sys.argv[1]:
        print('HIGH' if any(f['severity']=='high' for f in r['flags']) else 'low')
        break
else: print('MISSING')
" "$1"; }
for f in ".env.production" "신원확인.txt" "급여명세서.txt" "근로계약서.txt"; do
    [ "$(flag_of "$f")" = "HIGH" ] && ok "차단 대상 탐지: $f" || no "탐지 실패: $f"
done
[ "$(flag_of "캠페인결과.md")" = "low" ] && ok "정상 파일은 통과: 캠페인결과.md" \
    || no "정상 파일 오탐: 캠페인결과.md"

# ── 4. 적재기 ───────────────────────────────────────────────────────────────
head_ "4. INGEST 적재기 (강제 skip · 경로 차단 · 멱등성)"
PLAN="$OUT/plan.jsonl"
python3 - "$OUT" "$PLAN" <<'PY'
import json, os, sys
out, plan = sys.argv[1], sys.argv[2]
rows = []
for l in open(os.path.join(out, "manifest.jsonl")):
    r = json.loads(l)
    # 일부러 flags 를 빼고 전부 copy 로 지시한다 — 분류안이 플래그를 놓친 상황 재현
    dest = "../../탈출시도.txt" if r["name"] == "캠페인결과.md" else "ingest/_UNSORTED/" + r["name"]
    rows.append({"path": r["path"], "action": "copy", "dest": dest, "reason": "selftest"})
open(plan, "w").write("\n".join(json.dumps(x, ensure_ascii=False) for x in rows))
PY
R1=$(python3 tools/ingest_apply.py --plan "$PLAN" 2>&1)
echo "$R1" | grep -q "강제 skip" && ok "플래그 없이 지시해도 민감 파일 강제 skip" \
    || no "민감 파일이 적재됨 (이중 방어 실패)"
echo "$R1" | grep -q "목적지 거부" && ok "워크스페이스 밖 경로 거부" \
    || no "경로 탈출이 막히지 않음"
[ -f "$WS/../탈출시도.txt" ] && { no "실제로 워크스페이스 밖에 파일이 생성됨"; rm -f "$WS/../탈출시도.txt"; } \
    || ok "워크스페이스 밖에 아무것도 안 생김"
R2=$(python3 tools/ingest_apply.py --plan "$PLAN" 2>&1)
echo "$R2" | grep -q "복사 0" && ok "재실행 멱등 (중복 적재 없음)" \
    || no "재실행에 사본이 늘어남"

# 정리
find ingest/_UNSORTED -type f ! -name '.gitkeep' -delete 2>/dev/null
rm -f ingest/applied.jsonl

# ── 5. 설정 ─────────────────────────────────────────────────────────────────
head_ "5. 설정 파일"
python3 -c "import json;json.load(open('.claude/settings.json'))" 2>/dev/null \
    && ok ".claude/settings.json 유효" || no ".claude/settings.json 파싱 실패"
python3 -m py_compile tools/*.py tools/hooks/*.py 2>/dev/null \
    && ok "파이썬 문법 이상 없음" || no "파이썬 컴파일 오류"
rm -rf tools/__pycache__ tools/hooks/__pycache__ 2>/dev/null

# ── 결과 ────────────────────────────────────────────────────────────────────
printf "\n────────────────────────────\n"
printf "PASS %d · FAIL %d\n" "$pass" "$fail"
if [ "$fail" -gt 0 ]; then
    printf "\n\033[31m실패 항목이 있습니다.\033[0m 안전장치가 문서에 적힌 대로 동작하지 않습니다.\n"
    printf "이 상태로 회사 자료를 넣지 마세요. 실패 항목을 그대로 클로드에게 붙여넣고 물어보세요.\n"
    exit 1
fi
printf "\n\033[32m전부 통과.\033[0m 단, 탐지는 '완벽한 차단'이 아니라 '최선형'입니다 —\n"
printf "한계는 docs/ARCHITECTURE.md 의 '보장하지 않는 것'을 읽으세요.\n"

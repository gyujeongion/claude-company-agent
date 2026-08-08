#!/usr/bin/env python3
"""ingest_scan.py — 정리 안 된 회사 자료 더미를 기계적으로 전수 스캔한다.

설계 원칙
  1. 원본은 절대 수정·이동하지 않는다. 읽기 전용.
  2. 확장자 제약 없음. 모르는 포맷도 목록에는 반드시 남는다(버리지 않는다).
  3. 의미 분류는 여기서 하지 않는다. 사실만 모은다 — 분류는 에이전트가 REPORT와
     manifest를 읽고 판단한다. 기계가 추측한 카테고리는 신뢰를 망친다.
  4. 자격증명·주민번호가 보이면 본문 미리보기를 지우고 플래그만 남긴다.

사용법
    python3 tools/ingest_scan.py <경로> [<경로> ...] [--out ingest/_scan]
    python3 tools/ingest_scan.py ingest/_INBOX --max-preview 2000

산출물
    <out>/manifest.jsonl   파일 1개당 JSON 1줄 (에이전트가 배치로 읽는 원장)
    <out>/REPORT.md        사람·에이전트가 먼저 읽는 전체 그림
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone

# ── 스캔 제외 ────────────────────────────────────────────────────────────────
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", ".cache", ".npm", "dist", "build", ".next",
    ".pytest_cache", ".mypy_cache", ".Trash", ".DS_Store", "Library",
    ".tox", ".gradle", "Pods", ".terraform",
}
SKIP_FILES = {".DS_Store", "Thumbs.db", "desktop.ini", ".localized", ".gitkeep"}

HASH_CAP = 64 * 1024 * 1024   # 이보다 큰 파일은 앞부분만 해시(중복 판정용)

# ── 종류 분류 (확장자 기반. 이건 사실이지 추측이 아니다) ──────────────────────
KIND_BY_EXT = {
    "doc":     {".doc", ".docx", ".odt", ".rtf", ".hwp", ".hwpx", ".pages"},
    "pdf":     {".pdf"},
    "sheet":   {".xls", ".xlsx", ".csv", ".tsv", ".ods", ".numbers"},
    "slide":   {".ppt", ".pptx", ".odp", ".key"},
    "text":    {".txt", ".md", ".markdown", ".rst", ".log", ".vtt", ".srt"},
    "data":    {".json", ".jsonl", ".xml", ".yaml", ".yml", ".sql", ".db", ".sqlite"},
    "code":    {".py", ".js", ".ts", ".tsx", ".jsx", ".sh", ".rb", ".go", ".java",
                ".swift", ".c", ".cpp", ".h", ".php", ".r", ".ipynb"},
    "image":   {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".tiff",
                ".bmp", ".psd", ".ai", ".sketch", ".fig"},
    "audio":   {".mp3", ".wav", ".m4a", ".flac", ".aac", ".aiff", ".ogg"},
    "video":   {".mp4", ".mov", ".avi", ".mkv", ".webm"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".dmg"},
    "email":   {".eml", ".msg", ".mbox"},
}
EXT_TO_KIND = {ext: kind for kind, exts in KIND_BY_EXT.items() for ext in exts}

TEXTLIKE = {"text", "data", "code"}
OOXML = {".docx": ("word/document.xml",),
         ".pptx": None,           # ppt/slides/slideN.xml 전부
         ".xlsx": ("xl/sharedStrings.xml",)}

# ── 시크릿 / 민감정보 패턴 ───────────────────────────────────────────────────
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private-key", "high"),
    (re.compile(r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}"
                r"|AKIA[0-9A-Z]{16})\b"), "vendor-token", "high"),
    (re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|passwo?rd|passwd)\b"
                r"\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.]{12,}"), "credential-assignment", "high"),
    (re.compile(r"\b\d{6}-[1-4]\d{6}\b"), "resident-registration-number", "high"),
    (re.compile(r"(?i)\b[0-9]{3}-[0-9]{2}-[0-9]{5}\b"), "business-registration-number", "low"),
]
# 파일명만 봐도 민감할 가능성이 높은 것 — 차단이 아니라 '주의 표시'
SENSITIVE_NAME = re.compile(
    r"(?i)(계약|정산|주민|통장|이체|세금계산서|비밀|대외비|"
    r"contract|invoice|nda|confidential)")

# 인사·급여·근로계약 — 이 워크스페이스의 '범위 밖'(policy/scope.md).
# 주의 표시가 아니라 **적재 차단**이다. 한 번 새면 되돌릴 수 없고,
# 레포를 가진 전 직원이 보게 되기 때문이다.
HR_NAME = re.compile(
    r"(?i)(급여|연봉|인사|근로계약|고용계약|재직증명|이력서|경력증명|채용|면접|"
    r"인사평가|고과|징계|퇴직|퇴사|4대보험|원천징수|명세서|"
    r"payroll|salary|compensation|resume|cv_|employment|hr[_-]|personnel|"
    r"performance[_-]review|termination|onboarding[_-]employee)")
HR_CONTENT = re.compile(
    r"(?i)(근로계약서|연봉계약서|급여명세|원천징수영수증|인사평가표|"
    r"기본급.{0,10}수당|퇴직금.{0,10}산정)")

# 파일명만으로 자격증명이 확실한 것 — 본문을 못 읽어도 무조건 high
SECRET_NAME = re.compile(
    r"""(?ix)
    (^|[/\\])\.env(\.|$)
  | \.(pem|p12|pfx|jks|keystore)$
  | (^|[/\\])(id_rsa|id_ed25519|id_ecdsa)(\.|$)
  | service[_-]account.*\.json$
""")


def sha256_of(path, size):
    h = hashlib.sha256()
    read = 0
    try:
        with open(path, "rb") as f:
            while read < HASH_CAP:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
    except OSError:
        return None, False
    return h.hexdigest(), size > HASH_CAP


def _strip_xml(raw):
    txt = re.sub(rb"<[^>]+>", b" ", raw)
    return re.sub(r"\s+", " ", txt.decode("utf-8", "ignore")).strip()


TEXT_PROBE_MAX = 4 * 1024 * 1024   # 확장자를 모를 때 텍스트인지 찔러보는 상한


def looks_like_text(path):
    """확장자로 판단 불가한 파일이 사실은 텍스트인지 확인.

    `.env.production`, `Dockerfile`, 확장자 없는 설정 파일처럼 자격증명이 가장
    잘 숨는 곳이 여기다. 앞부분에 NUL이 없고 대부분 출력 가능한 문자면 텍스트로 본다.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    if not head or b"\x00" in head:
        return False
    printable = sum(1 for b in head if 9 <= b <= 13 or 32 <= b < 127 or b >= 128)
    return printable / len(head) > 0.9


def extract_text(path, ext, limit, size=0):
    """읽을 수 있으면 앞부분 텍스트를, 못 읽으면 (None, 사유)를 돌려준다."""
    try:
        if ext in {".ipynb"}:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(limit * 3)[:limit], None
        if EXT_TO_KIND.get(ext) in TEXTLIKE or ext in {".md", ".txt"}:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(limit), None
        if ext in OOXML:
            with zipfile.ZipFile(path) as z:
                names = OOXML[ext]
                if names is None:
                    names = sorted(n for n in z.namelist()
                                   if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
                out = []
                for n in names:
                    try:
                        out.append(_strip_xml(z.read(n)))
                    except KeyError:
                        continue
                    if sum(len(o) for o in out) > limit:
                        break
                text = " ".join(out)[:limit]
                return (text, None) if text else (None, "empty-ooxml")
        if ext == ".pdf":
            if not shutil.which("pdftotext"):
                return None, "pdftotext-not-installed"
            r = subprocess.run(["pdftotext", "-l", "5", "-q", path, "-"],
                               capture_output=True, timeout=60)
            text = re.sub(r"\s+", " ", r.stdout.decode("utf-8", "ignore")).strip()
            return (text[:limit], None) if text else (None, "pdf-no-text-layer")
        if ext in {".hwp", ".hwpx", ".pages", ".key", ".numbers", ".doc", ".ppt", ".xls"}:
            return None, f"unsupported-format:{ext}"
        # 확장자를 모르는 파일 — 시크릿이 가장 잘 숨는 자리라 반드시 찔러본다
        if EXT_TO_KIND.get(ext) is None and 0 < size <= TEXT_PROBE_MAX:
            if looks_like_text(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read(limit), None
            return None, "binary-unknown-format"
    except zipfile.BadZipFile:
        return None, "corrupt-or-not-zip"
    except subprocess.TimeoutExpired:
        return None, "extract-timeout"
    except Exception as e:  # 한 파일 때문에 전체 스캔이 죽으면 안 된다
        return None, f"error:{type(e).__name__}"
    return None, None  # 이미지·오디오 등 — 본문 개념이 없음


def scan_secrets(text, name):
    hits = []
    if SECRET_NAME.search(name):
        hits.append({"type": "credential-file", "severity": "high"})
    if HR_NAME.search(name):
        hits.append({"type": "hr-out-of-scope", "severity": "high"})
    if text:
        for pat, label, sev in SECRET_PATTERNS:
            if pat.search(text):
                hits.append({"type": label, "severity": sev})
        if HR_CONTENT.search(text):
            hits.append({"type": "hr-content-out-of-scope", "severity": "high"})
    if SENSITIVE_NAME.search(name):
        hits.append({"type": "sensitive-filename", "severity": "medium"})
    return hits


def walk(roots):
    for root in roots:
        root = os.path.abspath(os.path.expanduser(root))
        if os.path.isfile(root):
            yield root, os.path.dirname(root)
            continue
        if not os.path.isdir(root):
            print(f"  ! 경로 없음, 건너뜀: {root}", file=sys.stderr)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith(".")]
            for fn in filenames:
                if fn in SKIP_FILES or fn.startswith("._"):
                    continue
                yield os.path.join(dirpath, fn), root


def main():
    ap = argparse.ArgumentParser(description="회사 자료 더미 전수 스캔 (읽기 전용)")
    ap.add_argument("paths", nargs="+", help="스캔할 폴더 또는 파일 (여러 개 가능)")
    ap.add_argument("--out", default="ingest/_scan", help="산출물 폴더")
    ap.add_argument("--max-preview", type=int, default=1200, help="본문 미리보기 글자 수")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    manifest_path = os.path.join(args.out, "manifest.jsonl")

    seen_hash = {}
    records = []
    n = 0

    with open(manifest_path, "w", encoding="utf-8") as mf:
        for path, root in walk(args.paths):
            n += 1
            if n % 200 == 0:
                print(f"  ... {n}개 스캔", file=sys.stderr)
            try:
                st = os.stat(path)
            except OSError:
                continue
            name = os.path.basename(path)
            ext = os.path.splitext(name)[1].lower()
            digest, partial = sha256_of(path, st.st_size)
            preview, why = extract_text(path, ext, args.max_preview, st.st_size)
            flags = scan_secrets(preview, name)
            redacted = any(f["severity"] == "high" for f in flags)

            rec = {
                "id": (digest or "nohash")[:12] + f"-{n}",
                "path": path,
                "rel": os.path.relpath(path, root),
                "root": root,
                "name": name,
                "ext": ext or "(none)",
                "kind": EXT_TO_KIND.get(ext, "unknown"),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc)
                          .astimezone().strftime("%Y-%m-%d"),
                "sha256": digest,
                "hash_partial": partial,
                "flags": flags,
                # 시크릿이 걸린 파일은 본문을 워크스페이스에 남기지 않는다
                "preview": None if redacted else preview,
                "preview_redacted": redacted,
                "extract_note": why,
            }
            if digest and digest in seen_hash:
                rec["duplicate_of"] = seen_hash[digest]
            elif digest:
                seen_hash[digest] = rec["path"]

            mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            records.append(rec)

    write_report(records, args.out, args.paths)
    print(f"\n스캔 완료: {len(records)}개")
    print(f"  원장  {manifest_path}")
    print(f"  리포트 {os.path.join(args.out, 'REPORT.md')}")
    print("\n다음: 클로드에게 \"스캔 리포트 읽고 분류안 만들어줘\" 라고 하세요.")


def write_report(recs, out, roots):
    kinds = Counter(r["kind"] for r in recs)
    exts = Counter(r["ext"] for r in recs)
    years = Counter(r["mtime"][:4] for r in recs)
    dirs = Counter()
    for r in recs:
        top = r["rel"].split(os.sep)[0] if os.sep in r["rel"] else "(루트)"
        dirs[top] += 1

    high = [r for r in recs if any(f["severity"] == "high" for f in r["flags"])]
    med = [r for r in recs if any(f["severity"] == "medium" for f in r["flags"])
           and r not in high]
    dups = [r for r in recs if r.get("duplicate_of")]
    unread = [r for r in recs if r["extract_note"]]
    total_size = sum(r["size"] for r in recs)

    L = []
    A = L.append
    A("# INGEST 스캔 리포트\n")
    A(f"생성: {datetime.now().astimezone():%Y-%m-%d %H:%M} · "
      f"대상: {', '.join(roots)}\n")
    A("> 이 리포트는 **사실만** 담습니다. 분류·요약은 에이전트가 manifest.jsonl을 "
      "읽고 판단합니다.\n")
    A(f"\n## 요약\n")
    A(f"- 파일 **{len(recs):,}개** · 총 {total_size/1e9:.2f} GB")
    A(f"- 중복(동일 해시) {len(dups):,}개")
    A(f"- 본문 추출 불가 {len(unread):,}개")
    A(f"- 🔴 적재 차단 대상 **{len(high)}건** (자격증명·주민번호·인사/급여/근로계약)")
    A(f"- 🟡 민감 파일명 {len(med)}건 (계약·정산·대외비 등)")

    A("\n## 종류별\n\n| 종류 | 개수 |\n|---|---|")
    for k, c in kinds.most_common():
        A(f"| {k} | {c:,} |")

    A("\n## 확장자 상위 20\n\n| 확장자 | 개수 |\n|---|---|")
    for e, c in exts.most_common(20):
        A(f"| `{e}` | {c:,} |")

    A("\n## 최상위 폴더별 (원본 구조가 곧 회사의 실제 분류다)\n\n| 폴더 | 개수 |\n|---|---|")
    for d, c in dirs.most_common(30):
        A(f"| `{d}` | {c:,} |")

    A("\n## 연도별 (수정일 기준)\n\n| 연도 | 개수 |\n|---|---|")
    for y, c in sorted(years.items(), reverse=True):
        A(f"| {y} | {c:,} |")

    if high:
        A("\n## 🔴 적재 금지 — 자격증명 · 개인정보 · 인사/급여\n")
        A("본문 미리보기는 원장에서 삭제됐습니다. 아래는 경로와 사유뿐입니다.\n"
      "인사·급여·근로계약은 이 워크스페이스의 범위 밖입니다 "
      "(policy/scope.md) — 위치만 알리고 손대지 않습니다.\n")
        A("| 파일 | 사유 |\n|---|---|")
        for r in high[:100]:
            why = ", ".join(f["type"] for f in r["flags"] if f["severity"] == "high")
            A(f"| `{r['rel']}` | {why} |")
        if len(high) > 100:
            A(f"\n... 외 {len(high)-100}건. 전체는 manifest.jsonl 참조.")

    if med:
        A("\n## 🟡 민감 파일명 (적재 가능. 단 '레포 가진 전원이 봐도 되는가' 먼저 판단)\n")
        A("| 파일 |\n|---|")
        for r in med[:50]:
            A(f"| `{r['rel']}` |")
        if len(med) > 50:
            A(f"\n... 외 {len(med)-50}건.")

    if unread:
        A("\n## 본문 추출 불가\n")
        A("파일은 보존됩니다. 카드는 파일명·경로·사용자 설명으로 수동 작성합니다.\n")
        reasons = Counter(r["extract_note"] for r in unread)
        A("| 사유 | 개수 |\n|---|---|")
        for why, c in reasons.most_common():
            A(f"| {why} | {c:,} |")

    A("\n---\n\n## 에이전트 다음 단계\n")
    A("1. 위 폴더 구조·연도 분포를 사용자에게 **먼저 보고**하고, 모르는 폴더명의 뜻을 물어본다.")
    A("2. `manifest.jsonl`을 200개씩 배치로 읽어 `ingest/plan.jsonl`을 작성한다.")
    A("3. 🔴 항목은 `action: \"skip\"` 고정. 사용자에게 원본 위치만 알린다. "
      "인사·급여·근로계약은 범위 밖이므로 요약조차 만들지 않는다.")
    A("4. 사용자 승인 후 `python3 tools/ingest_apply.py --plan ingest/plan.jsonl`")
    A("5. 적재된 문서마다 `30_KNOWLEDGE/cards/`에 색인 카드를 쓴다. 카드 없으면 검색 불가.")

    with open(os.path.join(out, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()

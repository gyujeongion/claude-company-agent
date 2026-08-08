# ingest — 자료 흡수 작업 공간

## 아무거나 던져도 됩니다

정리 상태·확장자·폴더 구조 상관없습니다. 두 가지 방법:

**A. 원래 자리 그대로 스캔** (권장 — 복사 안 해도 됨)
```bash
python3 tools/ingest_scan.py "/Volumes/NAS/회사자료" "~/Downloads/계약서모음"
```

**B. 여기 복사해 넣고 스캔**
```bash
# ingest/_INBOX/ 에 폴더째 드래그해서 넣은 뒤
python3 tools/ingest_scan.py ingest/_INBOX
```

그다음 클로드에게: **"스캔한 자료 정리해줘"**

## 폴더

| 폴더 | 용도 |
|---|---|
| `_INBOX/` | 아무렇게나 던져넣는 곳. git-ignore |
| `_scan/` | 스캔 산출물 (manifest.jsonl · REPORT.md). git-ignore |
| `_UNSORTED/` | 분류 판단이 안 선 것. **버리지 않고 여기 보관** |
| `plan.jsonl` | 에이전트가 만든 분류안 |
| `applied.jsonl` | 실제로 뭘 어디로 옮겼는지 기록 (되돌릴 근거) |

## 안전장치

- 원본은 **복사만** 합니다. 이동은 `--allow-move` 명시해야 합니다.
- 자격증명·주민번호가 검출된 파일은 **적재되지 않습니다.** 위치만 보고합니다.
- 동일 파일(해시 일치)은 한 번만 적재합니다.
- 목적지가 워크스페이스 밖이면 거부합니다.

절차 전문: `docs/INGEST.md`

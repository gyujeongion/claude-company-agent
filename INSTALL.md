# INSTALL

## 필요한 것

- [Claude Code](https://claude.com/claude-code)
- Python 3.9+ (macOS·Linux 기본 탑재)
- git

선택 — 있으면 문서 추출 품질이 올라갑니다:
- `pdftotext` (macOS: `brew install poppler`) — PDF 본문 추출
- `.docx / .xlsx / .pptx`는 추가 설치 없이 처리됩니다

## 설치

```bash
git clone <레포 주소> ~/AI/company
cd ~/AI/company
bash tools/bootstrap.sh
```

`bootstrap.sh`는 추적되는 `*.example` 시드를 실파일로 복사합니다. 이미 있는 파일은
건드리지 않으므로 몇 번을 다시 돌려도 안전합니다.

## 첫 실행

```bash
cd ~/AI/company
claude
```

클로드에게: **"세팅해줘"**

- 회사 레이어가 아직 비어 있으면 → 관리자 온보딩 (회사 인터뷰 + 자료 흡수)
- 이미 구축돼 있으면 → 직원 온보딩 (본인 직무 + 개인 설정만, 5분)

## 설치 확인

```bash
bash tools/selftest.sh
```

안전장치 24개를 실제로 돌려봅니다. 실패가 나오면 그 화면을 그대로 클로드에게
붙여넣고 물어보세요. **실패가 있는 상태로 회사 자료를 넣지 마세요.**

## 훅

`.claude/settings.json`이 이 워크스페이스 안에 들어 있어, 여기서 클로드 코드를
실행하면 자동으로 적용됩니다. 전역 설정(`~/.claude/settings.json`)은 건드리지 않습니다.

작동 확인:
```bash
echo '{"prompt":"거래처에 메일 보내줘"}' | python3 tools/hooks/boundary_gate.py
```
JSON이 출력되면 정상입니다.

## 업데이트

```bash
git pull
bash tools/bootstrap.sh   # 새로 추가된 시드만 생성
```

개인 파일·회사 실데이터는 추적 대상이 아니라 덮어써지지 않습니다.

## 문제

| 증상 | 원인·해결 |
|---|---|
| 세션 시작에 회사 정보가 안 뜸 | 워크스페이스 루트에서 `claude`를 실행했는지 확인 |
| `bootstrap.sh: permission denied` | `bash tools/bootstrap.sh` 로 실행 |
| PDF 본문이 안 뽑힘 | `brew install poppler` 후 스캔 재실행 |
| `.hwp` 등 미지원 포맷 | 리포트의 `extraction_unavailable` 목록 참조. 파일은 보존되고 카드만 수동 작성 |

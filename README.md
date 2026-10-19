<h1 align="center">Company Agent for Claude Code</h1>

<p align="center">
  <b>Turn Claude Code into a coworker who actually knows your job.</b><br>
  A workspace template that organizes <i>your work</i> — not your codebase —<br>
  so an AI agent drafts, finds, and checks things the way your team actually does.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#ingest-dump-everything-you-have">Ingest</a> ·
  <a href="docs/ARCHITECTURE.md">Architecture</a> ·
  <a href="#한국어">한국어</a>
</p>

> **Docs are written in Korean.** The structure is language-agnostic. On first run the
> agent asks what language you work in and translates the workspace for you — see
> [Language](#language).

---

## What this is

Most "AI for teams" setups end at *"point a chatbot at some documents."* Then answers
blur together: a finance question comes back in marketing voice, an outbound email
quietly leaks an internal number, and nobody reads the SOPs that pile up.

This is a folder structure your team clones. Each folder tells the agent what lives
there and when to open it. The agent follows pointers instead of scanning everything —
the same way a person opens one drawer, not the whole cabinet.

**No coding required.** Clone it, open Claude Code, say *"set this up"*, and answer
an interview.

## Three gates

1. **Navigation gate** — the agent never scans the whole workspace. It follows pointers.
2. **Judgment gate** — requests are classified. Legal calls and money movement stop at
   the draft stage. **HR, payroll, and org data are out of scope entirely.**
3. **Boundary gate** — the company layer and your personal layer stay separate. Personal
   context never leaks into work output, and company policy never governs your own career.

## What it deliberately does NOT hold

No org chart. No headcount. No approval chains. No salaries. No employee roster.
No company P&L.

Not an oversight but a design decision. You don't need any of it to write a document or
find a file, and a shared repo is exactly where that information gets exposed by one
mis-shared path. The ingest pipeline refuses those files in code rather than in prose,
so the rule doesn't erode over a long session — though detection itself is best-effort.

See [`00_COMPANY/policy/scope.md`](00_COMPANY/policy/scope.md).

## Quick start

```bash
git clone https://github.com/<you>/claude-company-agent ~/AI/company
cd ~/AI/company
bash tools/bootstrap.sh
claude
```

Then tell Claude: **"set this up"**

- **First person in** (admin): company interview → bulk-ingest existing files → your role
- **Everyone after**: role + personal setup only, about five minutes

## Ingest: dump everything you have

Point it at a messy folder. No extension filter, no cleanup required.

```bash
python3 tools/ingest_scan.py "/path/to/company/files" "/another/path"
```

Scan → report → classification plan → your approval → filed + index cards written.

**Originals are copied, never modified.** Moving requires an explicit `--allow-move`
flag. Credentials, national ID numbers, and HR/payroll files are detected and blocked
before they land — best-effort detection, **not a DLP or compliance tool**. Re-running
is idempotent by content hash (files over 64 MB are hashed by prefix).

Full procedure: [docs/INGEST.md](docs/INGEST.md)

## Layout

```
00_COMPANY/    work standards — what the company does · voice · policy · glossary
10_ROLES/      ★ your job. what you do and how to ask for it
20_PLAYBOOKS/  procedures · SOPs · checklists
30_KNOWLEDGE/  index cards for ingested material + originals
40_ASSETS/     logos · forms · templates
50_PROJECTS/   things with a deadline
60_SYSTEMS/    internal tools · accounts · automation
80_ARCHIVE/    finished
90_ME/         ← personal layer. git-ignored. never reaches the company repo
ingest/        ingest workspace
```

## Verify it actually works

```bash
bash tools/selftest.sh
```

24 checks: are the hooks tracked by git, does the personal layer stay ignored, do the
gates fire on the right prompts and stay quiet on ordinary ones, does the ingest
pipeline block credentials and HR files even when the plan forgets to flag them, does
a path-escape get rejected, is a re-run idempotent. Run it after install, after
`git pull`, and after you edit a hook.

**Read [what it does NOT guarantee](docs/ARCHITECTURE.md#보장하지-않는-것) before
putting real files in.**

## Privacy

- `90_ME/` is git-ignored in full — clone, configure, commit, and it still never leaves
  your machine. The exact scope of that guarantee (and its limits on managed hardware)
  is spelled out in [`90_ME/CLAUDE.md`](90_ME/CLAUDE.md) rather than hand-waved.
- Company files ship as `*.example` seeds; your filled-in copies stay untracked.
- A `PreToolUse` hook denies reads of `.env`, private keys, and credential files at the
  tool layer, not as prose. It is pattern-based and fails open by design (a crashed hook
  must never wedge your session), so treat it as a strong guardrail, not a sandbox.
- Access tiers in a shared repo are **labels, not permissions.** The one rule that holds:
  *if everyone with the repo shouldn't see it, it doesn't go in.*

## Language

Every template and instruction file is in Korean. The folder structure, the hooks, and
the ingest tooling are language-neutral.

If you work in another language, say so during setup — the onboarding script offers to
translate the workspace before the interview starts. Or just ask:

```
Translate this workspace into English, then set it up for me.
```

Contributions of translated template sets are welcome.

## Docs

| Doc | What's in it |
|---|---|
| [ONBOARDING.md](ONBOARDING.md) | The setup interview (written for the agent, not for you) |
| [docs/INGEST.md](docs/INGEST.md) | Full ingest procedure |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Why it's built this way, and what it can't do |
| [docs/ADMIN.md](docs/ADMIN.md) | Rollout, updates, periodic checks |
| [docs/QUICKSTART.ko.md](docs/QUICKSTART.ko.md) | 5-minute guide to hand to employees |

## Related

[claude-life-agent](https://github.com/gyujeongion/claude-life-agent) — the same idea for
your personal life instead of your job.

## License

MIT

---

<a name="한국어"></a>

# 한국어

회사 지식·업무 절차·직무 맥락을 폴더 구조로 정리해서, 클로드 코드가
"일반 AI"가 아니라 **내 일을 아는 동료**로 동작하게 만드는 워크스페이스 템플릿입니다.

개발 지식 없어도 됩니다. 폴더에 클로드 코드를 열고 "세팅해줘"라고 하면 인터뷰가 시작됩니다.

## 세 개의 게이트

1. **탐색 게이트** — 전부 훑지 않습니다. 포인터를 따라 필요한 서랍만 엽니다.
2. **판단 게이트** — 법적 판단·금전 집행은 초안까지만.
   **인사·급여·조직은 아예 다루지 않습니다.**
3. **경계 게이트** — 회사 레이어와 개인 레이어가 분리됩니다.

## 일부러 넣지 않은 것

조직도·인원·결재선·급여·직원 명단·회사 손익.

빠뜨린 게 아니라 결정입니다. 문서를 쓰고 자료를 찾는 데 필요 없고, 공유 레포에서
경로 하나 잘못 공유됐을 때만 문제가 되는 정보이기 때문입니다.
적재 파이프라인이 **코드로** 거부합니다 — 세션이 길어지면 희석되는 산문 규칙이 아니라.
다만 탐지 자체는 최선형입니다(아래 참조).

## 3분 시작

```bash
git clone https://github.com/<계정>/claude-company-agent ~/AI/company
cd ~/AI/company
bash tools/bootstrap.sh
claude
```
그리고 클로드에게: **"세팅해줘"**

## 흩어진 자료 통째로 넣기

정리 안 된 폴더를 그대로 던지면 됩니다. 확장자 제약 없습니다.

```bash
python3 tools/ingest_scan.py "/경로/회사자료" "/다른/경로"
```

**원본은 복사만 합니다.** 이동은 `--allow-move`를 명시해야 합니다. 자격증명·주민번호·
인사/급여 파일은 적재 전에 탐지·차단되지만 **최선형 탐지이지 DLP가 아닙니다.**
내용 해시로 중복을 거르므로 반복 실행해도 사본이 늘지 않습니다(64 MB 초과 파일은
앞부분 해시).

설치 후 `bash tools/selftest.sh` 로 안전장치 24개가 실제로 동작하는지 확인하세요.
**보장하지 않는 것**은 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#보장하지-않는-것)에 적어뒀습니다.

상세: [docs/INGEST.md](docs/INGEST.md) · 직원 배포용 안내: [docs/QUICKSTART.ko.md](docs/QUICKSTART.ko.md)

## 관련

[claude-life-agent](https://github.com/gyujeongion/claude-life-agent) — 같은 구조의 개인 생활 버전.

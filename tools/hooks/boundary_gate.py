#!/usr/bin/env python3
"""UserPromptSubmit 훅 — 경계 게이트.

이 워크스페이스에는 섞이면 안 되는 세 가지가 있다.

  1. 회사 레이어 ↔ 개인 레이어(90_ME)
     개인 상담에 회사 브랜드 규칙이 끼어들면 답이 이상해지고,
     회사 산출물에 개인 정보가 새면 사고가 된다.

  2. 내부용 산출물 ↔ 외부로 나가는 산출물
     발송·게시·공유는 되돌릴 수 없다. 나가기 전에 체크리스트를 강제한다.

  3. AI가 답해도 되는 것 ↔ 사람이 결정해야 하는 것
     법적 판단·금전 집행은 초안까지만.

프롬프트 키워드로 감지해 해당 규칙을 상기시킨다. 오탐은 허용된다 —
주입문 첫 줄이 "아니면 무시하라"고 명시한다.

한계(정직하게): 이건 리마인더지 물리적 격리가 아니다. 완전 격리가 필요하면
워크스페이스를 두 개로 나눠야 한다. docs/ARCHITECTURE.md 참조.
"""

import json
import re
import sys

# CJK에는 \b가 안 먹으므로 경계 문자를 쓰지 않는다.
PERSONAL = re.compile(
    r"(?i)(내 커리어|이직|연봉 협상|개인적으로|사적으로|내 개인|가족|친구|연애|"
    r"결혼|건강|병원|다이어트|내 돈|내 자산|내 투자|주식|코인|취미|"
    r"90_ME|my career|personal|family|health)")

EGRESS = re.compile(
    r"(?i)(메일 보내|메일 발송|발송해|보내줘|회신|답장|공지|게시|업로드|"
    r"거래처|클라이언트|외부|대외|보도자료|제안서 보내|공유해|전달해|"
    r"인스타|링크드인|퍼블리시|publish|send email|post)")

HUMAN_ONLY = re.compile(
    r"(?i)(계약 해지|고소|소송|법적 대응|합의금|"
    r"입금|송금|이체|결제 승인|지급 결정|투자 집행)")

# 범위 밖 — 초안조차 만들지 않는다. HUMAN_ONLY(초안까지는 함)와 다르다.
# 인사·급여 정보는 한 번 새면 되돌릴 수 없고, 이 레포는 전 직원이 공유한다.
OUT_OF_SCOPE = re.compile(
    r"(?i)(급여|연봉|월급|인센티브|퇴직금|근로계약|고용계약|재직증명|"
    r"인사평가|고과|승진|징계|해고|권고사직|채용|면접|이력서|"
    r"조직도|결재선|부서 구성|인원 몇|직원 명단|누가 담당|담당자가 누구|"
    r"누구한테 물어|누구에게 물어|보고 라인|상사|팀장이 누구|"
    r"회사 손익|회사 매출|경영 현황|"
    r"누가 얼마|연봉 얼마|월급 얼마|직원 평가|누가 더 잘)")

BLOCKS = {
    "personal": """[경계 게이트] 개인 맥락 키워드 감지.
실제로 개인 얘기인지 먼저 확인하고(회사 업무면 이 알림 무시):
1. 90_ME/ 레이어입니다. 대외 톤 가이드·회사 브랜드 규칙 적용 OFF.
2. 결과물을 회사 폴더(00~80)에 쓰지 마세요. 90_ME/ 안에 씁니다.
3. 회사 문서에서 얻은 수치·내부 정보를 개인 판단 근거로 인용하지 마세요.
4. 90_ME/how_to_work_with_me.md 를 먼저 확인하세요.""",

    "egress": """[경계 게이트] 외부로 나가는 산출물 감지. 발송·게시 전 확인:
1. 개인정보(이름 외 연락처·주민번호·계좌)가 섞였는가
2. 내부 수치·미확정 정보·타사 정보가 노출되는가
3. 작업 흔적(초안 메모, AI 언급, 내부 경로, 모델명)이 남았는가
4. 대외 톤이 00_COMPANY/brand_voice.md 와 맞는가
5. 승인이 필요한 건인지 (필요하면 사용자가 직접 받아야 함)
→ 20_PLAYBOOKS/외부발송_체크.md 통과 후, 발송은 사람이 누릅니다.""",

    "human_only": """[경계 게이트] 사람이 결정해야 하는 영역입니다
(법적 판단·금전 집행 — 00_COMPANY/policy/escalation.md).
초안·근거 정리·선택지 비교까지는 도와도, 결론을 확정하거나 실행하지 마세요.
확인이 필요하다는 사실과, 확인 없이 진행하면 뭐가 위험한지를 함께 알려주세요.
누가 결정권자인지는 추측하지 마세요 — 이 워크스페이스에 조직 정보는 없습니다.""",

    "out_of_scope": """[경계 게이트] 범위 밖 키워드 감지 (인사·급여·조직·경영).
먼저 확인하세요 — 사용자 **본인의** 커리어·연봉 고민이면 이 알림을 무시하고
90_ME/ 개인 레이어에서 처리합니다(그건 허용된 용도입니다).

**남에 대한 정보**이거나 회사의 인사·급여·조직·경영 사안이라면:
1. 이 워크스페이스의 범위 밖입니다 (00_COMPANY/policy/scope.md).
   초안도, 요약도, "일반론으로는" 도 만들지 마세요.
2. 관련 파일이 워크스페이스에 있으면 그 자체가 잘못 들어온 것입니다. 열지 말고 보고하세요.
3. 담당자에게 문의하라고 안내하세요. 누가 담당인지는 **추측하지 마세요** —
   이 워크스페이스에는 조직 정보가 없습니다. 사용자가 90_ME/에 적어뒀다면
   그것만 참고합니다.
이유: 이 레포는 전 직원이 공유합니다. 경로 하나 잘못 공유되면 전원이 봅니다.""",
}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    prompt = data.get("prompt") or data.get("user_prompt") or ""
    if len(prompt) < 4:
        return

    parts = []
    if OUT_OF_SCOPE.search(prompt):
        parts.append(BLOCKS["out_of_scope"])
    if HUMAN_ONLY.search(prompt):
        parts.append(BLOCKS["human_only"])
    if EGRESS.search(prompt):
        parts.append(BLOCKS["egress"])
    if PERSONAL.search(prompt):
        parts.append(BLOCKS["personal"])
    if not parts:
        return

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n\n".join(parts),
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

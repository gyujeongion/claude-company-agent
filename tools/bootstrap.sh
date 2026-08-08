#!/usr/bin/env bash
# 최초 실행: 추적되는 *.example 시드에서 내 실데이터 파일을 만든다.
#
# 템플릿은 모든 회사·개인 파일을 `<이름>.example`(추적, 업데이트 가능)로 배포한다.
# 이 스크립트가 `<이름>`(git-ignore, 내 것)으로 복사한다. 이미 있으면 건드리지
# 않으므로 몇 번을 다시 돌려도 데이터가 날아가지 않는다.
#
#   bash tools/bootstrap.sh
set -euo pipefail
cd "$(dirname "$0")/.."

created=0
skipped=0
while IFS= read -r seed; do
    live="${seed%.example}"
    if [ -e "$live" ]; then
        skipped=$((skipped + 1))
    else
        mkdir -p "$(dirname "$live")"
        cp "$seed" "$live"
        echo "  생성  $live"
        created=$((created + 1))
    fi
done < <(find . -name '*.example' -not -path './.git/*')

# ingest 작업 폴더 유지용
for d in ingest/_INBOX ingest/_UNSORTED 30_KNOWLEDGE/cards; do
    mkdir -p "$d"; touch "$d/.gitkeep"
done

echo ""
echo "부트스트랩 완료: $created개 생성, $skipped개는 이미 있음."
if [ "$created" -gt 0 ]; then
    echo "생성된 실파일은 git-ignore 대상입니다 — 내 데이터는 레포에 안 올라갑니다."
    echo "이제 이 폴더에서 클로드 코드를 열고 \"세팅해줘\" 라고 하세요."
fi

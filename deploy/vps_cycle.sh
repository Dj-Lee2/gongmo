#!/usr/bin/env bash
# 공모모아 VPS 한 바퀴(수집 기계 없이도 돈다).
#   full  : 웹 출처 수집 → 빌드 → 원문 확인(linkcheck) → 1차 판단(triage) → 게시   (하루 두 번, gongmo-cycle.timer)
#   quick : 헤르메스 장부만 다시 읽기 → 빌드 → 게시   (수집 기계가 자료를 보냈을 때·매시, gongmo-publish.path/.timer)
# 검증 장부는 다른 기계에서 만들어 <운영 폴더>/site/data 로 보내므로, 거기서 장부를 되살린다.
set -uo pipefail
export TZ=Asia/Seoul
MODE=${1:-quick}
# 운영 폴더: <ROOT>/repo(이 저장소) · state · public · site/data — 기본은 이 저장소의 한 단계 위
SELF_REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ROOT=${GONGMO_ROOT:-$(dirname "$SELF_REPO")}
REPO=${GONGMO_REPO:-$ROOT/repo}
STATE=${GONGMO_STATE:-$ROOT/state}
INBOX=${GONGMO_INBOX:-$ROOT/site/data}
PUBLIC=${GONGMO_PUBLIC:-$ROOT/public}
cd "$REPO" || exit 1
mkdir -p "$STATE"
exec 9>"$STATE/.cycle.lock"
if ! flock -w 2400 9; then echo "앞선 작업이 40분 넘게 안 끝나 이번은 건너뜀"; exit 0; fi
echo "=== $(date '+%F %T %Z') $MODE 시작"
export GONGMO_HERMES_LEDGER="$STATE/hermes-ledger.json"
python3 deploy/ledger_from_inbox.py --inbox "$INBOX/items.json" --out "$GONGMO_HERMES_LEDGER"
RC_COLLECT=- RC_LINK=- RC_TRIAGE=-
if [ "$MODE" = full ] || [ ! -f data/raw/collect_status.json ]; then
  python3 -m collector.collect; RC_COLLECT=$?
  [ "$RC_COLLECT" = 0 ] || echo "!!! 수집 일부 오류 — 받은 자료로 진행"
else
  python3 -m collector.collect --hermes-only || echo "!!! 헤르메스 장부 읽기 오류"
fi
python3 -m collector.build; RC_BUILD=$?
if [ "$RC_BUILD" != 0 ]; then echo "!!! 빌드 실패 — 공개본 유지"; fi
if [ "$MODE" = full ] && [ "$RC_BUILD" = 0 ]; then
  timeout 1500 python3 deploy/linkcheck.py --items site/data/items.json --state "$STATE"; RC_LINK=$?
  [ "$RC_LINK" = 0 ] || echo "!!! 원문 확인 오류(코드 $RC_LINK)"
  timeout 3000 python3 deploy/triage.py --items site/data/items.json --state "$STATE"; RC_TRIAGE=$?
  [ "$RC_TRIAGE" = 0 ] || echo "!!! 1차 판단 오류(코드 $RC_TRIAGE)"
fi
RC_PUBLISH=-
if [ "$RC_BUILD" = 0 ]; then
  python3 deploy/publish_vps.py --inbox site/data --out "$PUBLIC" --state "$STATE" --respace; RC_PUBLISH=$?
fi
# 아침 알림(daily_digest.py)이 읽는 한 바퀴 결과
printf '{"mode":"%s","at":"%s","collect":"%s","build":"%s","link":"%s","triage":"%s","publish":"%s"}\n' \
  "$MODE" "$(date -Iseconds)" "$RC_COLLECT" "$RC_BUILD" "$RC_LINK" "$RC_TRIAGE" "$RC_PUBLISH" > "$STATE/last_$MODE.json"
echo "=== $(date '+%F %T %Z') $MODE 끝"

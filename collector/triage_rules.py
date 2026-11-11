"""1차 판단 등급 규칙(triage가 매기고, 게시 때 예전 판단에도 같은 규칙으로 다시 매긴다).

기준점은 헤르메스 검증과 맞춰 정했다(2026-10-20, 헤르메스가 판단한 60건):
  - 추천/조건부 26건의 1차 점수 중앙값 61, 제외 34건 중 자격 통과분 중앙값 42
  - 75/60 기준이면 일치 44/60(추천·조건부를 많이 '낮음'으로 떨굼), 70/50 기준이면 45/60, 헤르메스 '추천' 6건 중 70↑ 4건·제외 중 70↑ 0건
  - 가중치를 바꿔도 일치가 1건밖에 안 늘어 가중치는 그대로 둔다.
"""
WEIGHTS = {"fit": 0.40, "value": 0.25, "effort": 0.20, "terms": 0.15}
RECOMMEND = 70
REVIEW = 50


def total(scores):
    return int(round(sum((scores.get(k) or 0) * w for k, w in WEIGHTS.items())))


def grade(gate, score):
    if gate == "자격 안 됨":
        return "자격 안 됨"
    if score >= RECOMMEND and gate == "통과":
        return "추천"
    if score >= REVIEW:
        return "검토"   # 자격 '확인 필요'면 점수가 높아도 검토까지
    return "낮음"

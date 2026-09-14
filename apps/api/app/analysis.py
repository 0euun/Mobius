"""
설명 가능한 위험도와 증거 무결성 서비스.
현재는 synthetic replay 시나리오용 규칙 기반 특성을 사용하며, 운영 환경에서는
학습된 분류기·그래프·시계열 워커가 동일한 특성 계약을 공급한다.
"""

from datetime import UTC, datetime
import hashlib
from pathlib import Path

from .schemas import EvidenceItem, EvidenceManifest, EventResponse, RiskFeature, RiskStage, RiskSummary
from .model_runtime import classifier

HIGH_RISK_TERMS = ("위협", "괴롭힘", "공격", "신상", "협박")
COORDINATION_TERMS = ("같은 문구", "공유하자", "반복", "동일")


def load_events(path: Path) -> list[EventResponse]:
    with path.open(encoding="utf-8") as source:
        return [EventResponse.model_validate_json(line) for line in source if line.strip()]


def bounded(value: float) -> float:
    return round(max(0.0, min(value, 1.0)), 3)


def analyze_events(events: list[EventResponse]) -> RiskSummary:
    """정규화 특성의 가중합을 이용한다. 단일 0값이 전체 점수를 없애는 곱셈식은 사용하지 않는다."""
    count = len(events)
    target_id = events[0].target_ref if events else "unknown"
    growth = bounded((count - 1) / 5)
    platform_count = len({event.platform for event in events})
    spread = bounded(platform_count / 3)
    probabilities = classifier.harmful_probabilities([event.text for event in events])
    if probabilities is None:
        toxicity = bounded(sum(any(term in event.text for term in HIGH_RISK_TERMS) for event in events) / max(count, 1))
        toxicity_source = "rule_fallback"
    else:
        toxicity = bounded(sum(probabilities) / len(probabilities))
        toxicity_source = "klue_roberta_v0"
    tag_signal = sum("#논란" in event.hashtags for event in events) / max(count, 1)
    phrase_signal = sum(any(term in event.text for term in COORDINATION_TERMS) for event in events) / max(count, 1)
    coordination = bounded((tag_signal + phrase_signal) / 2)
    score = bounded(0.34 * growth + 0.24 * spread + 0.24 * toxicity + 0.18 * coordination)
    confidence = bounded(min(0.9, 0.35 + count * 0.08))

    if score >= 0.72:
        stage, actions = RiskStage.CASCADE, ["증거 패키지를 생성하고 원문 접근 권한을 제한하세요.", "플랫폼 신고 우선순위 게시물을 검토하세요.", "알림 수신자에게 대응 가이드를 전달하세요."]
    elif score >= 0.45:
        stage, actions = RiskStage.IGNITION, ["추가 데이터를 관찰하고 알림 빈도를 낮게 설정하세요.", "오탐 여부를 검토하고 대응 체크리스트를 준비하세요."]
    else:
        stage, actions = RiskStage.PRE_IGNITION, ["정상 감시를 유지하세요.", "대상별 키워드와 신고 담당자를 확인하세요."]

    toxicity_explanation = (
        "위험 키워드가 포함된 표현이 확인되었습니다." if toxicity_source == "rule_fallback"
        else "AI 분석 결과 유해한 표현이 포함된 것으로 나타났습니다."
    )
    features = [
        RiskFeature(name="mention_growth", value=growth, explanation=f"최근 언급이 {count}건 연속으로 빠르게 늘고 있습니다."),
        RiskFeature(name="cross_platform_spread", value=spread, explanation=f"{platform_count}개의 서로 다른 플랫폼에서 관련 게시물이 확인되었습니다."),
        RiskFeature(name="toxicity_severity", value=toxicity, explanation=toxicity_explanation),
        RiskFeature(name="coordination_signal", value=coordination, explanation="동일한 문구와 해시태그가 반복적으로 발견되어 조직적 활동의 가능성이 있습니다."),
    ]
    return RiskSummary(
        target_id=target_id, score=score, stage=stage, confidence=confidence, toxicity_source=toxicity_source,
        prediction_window_minutes=120,
        rationale=[feature.explanation for feature in features if feature.value > 0],
        features=features, recommended_actions=actions,
    )


def build_evidence_manifest(events: list[EventResponse]) -> EvidenceManifest:
    items, item_hashes = [], []
    for event in events:
        digest = hashlib.sha256(event.model_dump_json().encode("utf-8")).hexdigest()
        item_hashes.append(digest)
        items.append(EvidenceItem(event_id=event.event_id, collected_at=event.occurred_at, sha256=digest))
    generated_at = max((event.occurred_at for event in events), default=datetime.fromtimestamp(0, UTC))
    return EvidenceManifest(
        target_id=events[0].target_ref,
        generated_at=generated_at,
        package_sha256=hashlib.sha256("".join(item_hashes).encode("utf-8")).hexdigest(),
        integrity_notice="본 패키지는 SHA-256과 수집 시각으로 무결성 검증을 지원합니다. 법적 증거능력은 별도 판단이 필요합니다.",
        items=items,
    )

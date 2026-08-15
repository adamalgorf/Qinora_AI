from dataclasses import dataclass

from qinora.domain.transport_request import TransportMode


@dataclass(frozen=True)
class CarrierCandidate:
    id: str
    display_name: str
    aliases: tuple[str, ...]
    modes: tuple[TransportMode, ...]
    lane_score: float
    max_weight_kg: float | None = None
    performance_score: float | None = None
    preferred: bool = False
    sample_size: int = 0


@dataclass(frozen=True)
class CarrierEvaluationInput:
    mode: TransportMode
    candidates: tuple[CarrierCandidate, ...]
    requested_carrier_name: str | None = None
    total_weight_kg: float | None = None
    min_confidence: float = 0.65


@dataclass(frozen=True)
class CarrierEvaluation:
    carrier_id: str
    rank: int
    status: str
    score_total: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ConfidenceBreakdown:
    input_completeness: float
    candidate_quality: float
    score_separation: float
    rule_clarity: float
    performance_coverage: float
    sample_strength: float


@dataclass(frozen=True)
class CarrierIntelligenceResult:
    selected_carrier_id: str | None
    requires_manual_review: bool
    overall_confidence: float
    confidence: ConfidenceBreakdown
    evaluations: tuple[CarrierEvaluation, ...]


CONFIDENCE_WEIGHTS = {
    "input_completeness": 0.20,
    "candidate_quality": 0.20,
    "score_separation": 0.15,
    "rule_clarity": 0.15,
    "performance_coverage": 0.15,
    "sample_strength": 0.15,
}


def evaluate_carriers(input_: CarrierEvaluationInput) -> CarrierIntelligenceResult:
    evaluations = _rank_candidates(input_)
    eligible = tuple(evaluation for evaluation in evaluations if evaluation.status == "eligible")
    selected_carrier_id = eligible[0].carrier_id if eligible else None
    confidence = _build_confidence(input_, eligible)
    overall_confidence = round(
        sum(getattr(confidence, key) * weight for key, weight in CONFIDENCE_WEIGHTS.items()),
        2,
    )

    return CarrierIntelligenceResult(
        selected_carrier_id=selected_carrier_id,
        requires_manual_review=not selected_carrier_id
        or overall_confidence < input_.min_confidence,
        overall_confidence=overall_confidence,
        confidence=confidence,
        evaluations=evaluations,
    )


def _rank_candidates(input_: CarrierEvaluationInput) -> tuple[CarrierEvaluation, ...]:
    ranked = sorted(
        (_evaluate_candidate(input_, candidate) for candidate in input_.candidates),
        key=lambda evaluation: evaluation.score_total,
        reverse=True,
    )

    return tuple(
        CarrierEvaluation(
            carrier_id=evaluation.carrier_id,
            rank=index + 1,
            status=evaluation.status,
            score_total=evaluation.score_total,
            reasons=evaluation.reasons,
        )
        for index, evaluation in enumerate(ranked)
    )


def _evaluate_candidate(
    input_: CarrierEvaluationInput, candidate: CarrierCandidate
) -> CarrierEvaluation:
    if input_.mode not in candidate.modes:
        return CarrierEvaluation(
            candidate.id,
            0,
            "ineligible",
            0,
            (f"Carrier does not support {input_.mode.value}",),
        )

    if input_.total_weight_kg is None:
        return CarrierEvaluation(candidate.id, 0, "incomplete", 0, ("total_weight_kg is required",))

    if candidate.max_weight_kg is not None and input_.total_weight_kg > candidate.max_weight_kg:
        return CarrierEvaluation(
            candidate.id,
            0,
            "ineligible",
            0,
            ("Requested weight exceeds carrier capability",),
        )

    reasons: list[str] = []
    alias_boost = 15 if _matches_alias(input_.requested_carrier_name, candidate) else 0
    preferred_boost = 5 if candidate.preferred else 0
    performance_score = (
        candidate.performance_score if candidate.performance_score is not None else 50
    )
    score_total = round(
        candidate.lane_score * 0.35
        + performance_score * 0.35
        + 20
        + alias_boost
        + preferred_boost,
        2,
    )

    if alias_boost:
        reasons.append("requested carrier alias matched")
    if candidate.preferred:
        reasons.append("preferred carrier boost applied")

    return CarrierEvaluation(candidate.id, 0, "eligible", score_total, tuple(reasons))


def _build_confidence(
    input_: CarrierEvaluationInput, eligible: tuple[CarrierEvaluation, ...]
) -> ConfidenceBreakdown:
    top = eligible[0] if len(eligible) > 0 else None
    second = eligible[1] if len(eligible) > 1 else None
    candidates_with_performance = sum(
        1 for candidate in input_.candidates if candidate.performance_score is not None
    )
    total_samples = sum(candidate.sample_size for candidate in input_.candidates)

    return ConfidenceBreakdown(
        input_completeness=1 if input_.total_weight_kg is not None else 0.45,
        candidate_quality=_clamp01(len(eligible) / 3),
        score_separation=_score_separation(top, second),
        rule_clarity=0.85 if input_.requested_carrier_name else 0.7,
        performance_coverage=0
        if not input_.candidates
        else candidates_with_performance / len(input_.candidates),
        sample_strength=_clamp01(total_samples / 100),
    )


def _score_separation(
    top: CarrierEvaluation | None, second: CarrierEvaluation | None
) -> float:
    if top is None:
        return 0
    if second is None:
        return 1
    return _clamp01((top.score_total - second.score_total) / 25)


def _matches_alias(requested_name: str | None, candidate: CarrierCandidate) -> bool:
    if not requested_name:
        return False

    normalized = requested_name.strip().lower()
    names = (candidate.display_name, *candidate.aliases)
    return any(name.strip().lower() == normalized for name in names)


def _clamp01(value: float) -> float:
    return max(0, min(1, value))


def parse_transport_modes(modes: tuple[str, ...]) -> tuple[TransportMode, ...]:
    """Silently drops any mode string that isn't a real TransportMode value,
    rather than letting one bad entry (e.g. a typo from manual carrier
    entry) throw and take down carrier scoring for every carrier in the
    same request.
    """
    valid = {mode.value for mode in TransportMode}
    return tuple(TransportMode(mode) for mode in modes if mode in valid)

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TransportMode(StrEnum):
    FTL = "ftl"
    LTL = "ltl"
    OCEAN = "ocean"
    AIR = "air"
    RAIL = "rail"
    INTERMODAL = "intermodal"


@dataclass(frozen=True)
class CargoLineInput:
    description: str
    quantity: int | None = None
    weight_kg: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None


@dataclass(frozen=True)
class TransportRequestInput:
    mode: TransportMode
    cargo: tuple[CargoLineInput, ...]
    loading_time: datetime | None = None
    unloading_time: datetime | None = None


@dataclass(frozen=True)
class RequestValidationIssue:
    field: str
    message: str


@dataclass(frozen=True)
class AdrFinding:
    cargo_index: int
    un_number: str


@dataclass(frozen=True)
class RequestValidationResult:
    complete: bool
    issues: tuple[RequestValidationIssue, ...]
    adr_findings: tuple[AdrFinding, ...]


MODES_REQUIRING_DIMENSIONS = {TransportMode.FTL, TransportMode.LTL, TransportMode.AIR}
UN_NUMBER_PATTERN = re.compile(r"\bUN\s?(\d{4})\b", re.IGNORECASE)

# The 3 checks validate_transport_request has always run, now individually
# toggleable per tenant via Parsek's own agent_configs.config["required_fields"]
# (see application/request_parsing_agent.py). This default preserves today's
# hardcoded behaviour exactly for every tenant that hasn't customized it.
DEFAULT_REQUIRED_FIELDS: frozenset[str] = frozenset({"weight", "dimensions", "times"})


def validate_transport_request(
    request: TransportRequestInput,
    required_fields: frozenset[str] = DEFAULT_REQUIRED_FIELDS,
) -> RequestValidationResult:
    issues: list[RequestValidationIssue] = []

    if not request.cargo:
        issues.append(RequestValidationIssue("cargo", "At least one cargo line is required"))

    for index, cargo in enumerate(request.cargo):
        if "weight" in required_fields and not _is_positive(cargo.weight_kg):
            issues.append(
                RequestValidationIssue(f"cargo.{index}.weight_kg", "weight_kg is required")
            )

        if "dimensions" in required_fields and request.mode in MODES_REQUIRING_DIMENSIONS:
            for field in ("length_cm", "width_cm", "height_cm"):
                if not _is_positive(getattr(cargo, field)):
                    issues.append(
                        RequestValidationIssue(
                            f"cargo.{index}.{field}",
                            f"{field} is required for {request.mode.value}",
                        )
                    )

    if "times" in required_fields and not request.loading_time and not request.unloading_time:
        issues.append(
            RequestValidationIssue(
                "loading_time",
                "At least one of loading_time or unloading_time is required",
            )
        )

    return RequestValidationResult(
        complete=not issues,
        issues=tuple(issues),
        adr_findings=detect_adr(request.cargo),
    )


def detect_adr(cargo_lines: tuple[CargoLineInput, ...]) -> tuple[AdrFinding, ...]:
    findings: list[AdrFinding] = []

    for index, cargo in enumerate(cargo_lines):
        match = UN_NUMBER_PATTERN.search(cargo.description)
        if match:
            findings.append(AdrFinding(index, f"UN{match.group(1)}"))

    return tuple(findings)


def _is_positive(value: float | None) -> bool:
    return value is not None and value > 0

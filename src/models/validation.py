from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class ValidationCheck(BaseModel):
    check: str
    status: CheckStatus
    details: str


class ValidationResult(BaseModel):
    checks: list[ValidationCheck]
    passed: bool

    @classmethod
    def from_checks(cls, checks: list[ValidationCheck]) -> "ValidationResult":
        return cls(checks=checks, passed=all(c.status == CheckStatus.PASS for c in checks))


class ReviewResult(BaseModel):
    audience_fit: int = Field(ge=1, le=10)
    brand_alignment: int = Field(ge=1, le=10)
    clarity: int = Field(ge=1, le=10)
    technical_quality: int = Field(ge=1, le=10)
    overall_assessment: str
    issues: list[str]
    recommendation: Literal["APPROVE", "REVISE"]

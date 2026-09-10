"""Deterministic operator commands accepted by ADK Web and the CLI."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import shlex

from question_bank.contracts import money


_CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class GenerateCampaign:
    campaign_id: str
    proposal_target: int
    level: str
    bank: str
    budget_usd: Decimal


@dataclass(frozen=True)
class StatusCampaign:
    campaign_id: str


@dataclass(frozen=True)
class CancelCampaign:
    campaign_id: str


@dataclass(frozen=True)
class ResumeCampaign:
    campaign_id: str
    budget_usd: Decimal


CampaignCommand = GenerateCampaign | StatusCampaign | CancelCampaign | ResumeCampaign


def _fields(parts: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise ValueError(f"expected key=value, received {part!r}")
        key, value = part.split("=", 1)
        if not key or not value or key in result:
            raise ValueError(f"invalid or duplicate field {key!r}")
        result[key] = value
    return result


def _campaign_id(value: str) -> str:
    if not _CAMPAIGN_ID.fullmatch(value):
        raise ValueError("campaign must be 1-128 safe identifier characters")
    return value


def _budget(value: str) -> Decimal:
    try:
        result = money(Decimal(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("budget_usd must be a decimal amount") from error
    if result <= 0:
        raise ValueError("budget_usd must be positive")
    return result


def parse_campaign_command(text: str) -> CampaignCommand:
    """Parse one explicit command without using an LLM or accepting aliases."""
    parts = shlex.split(text)
    if not parts:
        raise ValueError("campaign command is empty")
    verb, values = parts[0].lower(), _fields(parts[1:])
    if verb == "generate":
        required = {"campaign", "proposal_target", "level", "bank", "budget_usd"}
        if set(values) != required:
            raise ValueError(f"generate requires exactly {sorted(required)}")
        try:
            proposal_target = int(values["proposal_target"])
        except ValueError as error:
            raise ValueError("proposal_target must be an integer") from error
        if proposal_target < 20 or proposal_target % 20:
            raise ValueError("proposal_target must be a positive multiple of 20")
        level = values["level"].lower()
        if level not in {"mixed", "shallow", "deep"}:
            raise ValueError("level must be mixed, shallow, or deep")
        if values["bank"] != "v2.1":
            raise ValueError("only bank v2.1 is supported")
        return GenerateCampaign(
            campaign_id=_campaign_id(values["campaign"]),
            proposal_target=proposal_target,
            level=level,
            bank=values["bank"],
            budget_usd=_budget(values["budget_usd"]),
        )
    if verb in {"status", "cancel"}:
        if set(values) != {"campaign"}:
            raise ValueError(f"{verb} requires exactly campaign")
        campaign_id = _campaign_id(values["campaign"])
        return (
            StatusCampaign(campaign_id=campaign_id)
            if verb == "status"
            else CancelCampaign(campaign_id=campaign_id)
        )
    if verb == "resume":
        if set(values) != {"campaign", "budget_usd"}:
            raise ValueError("resume requires exactly campaign and budget_usd")
        return ResumeCampaign(
            campaign_id=_campaign_id(values["campaign"]),
            budget_usd=_budget(values["budget_usd"]),
        )
    raise ValueError("command must be generate, status, cancel, or resume")

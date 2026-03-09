from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, BaseModel, Field


class Benefit(BaseModel):
    app_external_id: str | None = Field(
        None, description="The third-party external ID this reward is associated with"
    )
    app_meta: dict[str, Any] | None = Field(
        None,
        description="Any metadata the third-party app included with this benefit on creation",
    )
    benefit_type: str | None = Field(
        None,
        description="Type of benefit, such as `custom` for creator-defined benefits",
    )
    created_at: AwareDatetime | None = Field(
        None, description="Datetime this benefit was created"
    )
    deliverables_due_today_count: float | None = Field(
        None,
        description="Number of deliverables for this benefit that are due today specifically",
    )
    delivered_deliverables_count: float | None = Field(
        None,
        description="Number of deliverables for this benefit that have been marked complete",
    )
    description: str | None = Field(None, description="Display description")
    is_deleted: bool | None = Field(
        None, description="Whether this benefit has been deleted"
    )
    is_ended: bool | None = Field(
        None, description="Whether this benefit is no longer available to new patrons"
    )
    is_published: bool | None = Field(
        None, description="Whether this benefit is ready to be fulfilled to patrons"
    )
    next_deliverable_due_date: AwareDatetime | None = Field(
        None, description="The next due date (after EOD today) for this benefit"
    )
    not_delivered_deliverables_count: float | None = Field(
        None,
        description="Number of deliverables for this benefit that are due, for all dates",
    )
    rule_type: str | None = Field(
        None,
        description="A rule type designation, such as `eom_monthly` or `one_time_immediate`",
    )
    tiers_count: float | None = Field(
        None, description="Number of tiers containing this benefit"
    )
    title: str | None = Field(None, description="Display title")

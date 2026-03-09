from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field


class Address(BaseModel):
    addressee: str | None = Field(None, description="Full recipient name")
    city: str | None = Field(None, description="")
    country: str | None = Field(None, description="")
    created_at: AwareDatetime | None = Field(
        None, description="Datetime address was first created"
    )
    line_1: str | None = Field(None, description="First line of street address")
    line_2: str | None = Field(None, description="Second line of street address")
    phone_number: str | None = Field(
        None, description="Telephone number. Specified for non-US addresses"
    )
    postal_code: str | None = Field(None, description="Postal or zip code")
    state: str | None = Field(None, description="State or province name")

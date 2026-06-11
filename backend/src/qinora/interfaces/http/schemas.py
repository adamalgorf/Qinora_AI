from pydantic import BaseModel, EmailStr, Field


class EmailWebhookPayload(BaseModel):
    sender: EmailStr
    subject: str = Field(min_length=1, max_length=500)
    body_text: str = Field(min_length=1)


class EmailWebhookResponse(BaseModel):
    accepted: bool
    duplicate: bool
    inbound_email_id: str | None = None

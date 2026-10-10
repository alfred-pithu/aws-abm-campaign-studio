from pydantic import BaseModel, Field


class EmailContent(BaseModel):
    subject: str
    preheader: str
    headline: str
    body_paragraphs: list[str] = Field(min_length=1)
    cta_text: str
    claim_ids: list[str]

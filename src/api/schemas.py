from pydantic import BaseModel, EmailStr, Field


class EmailRequest(BaseModel):
    to: EmailStr
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    message_type: str | None = None


class EmailResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail

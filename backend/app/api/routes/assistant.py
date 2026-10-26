from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.ai.provider import AIProviderError
from app.ai.selection import build_provider
from app.core.deps import get_current_user
from app.models.user import User
from app.services.assistant import AssistantError, ask_assistant

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/ask")
def ask(
    body: AskRequest,
    user: User = Depends(get_current_user),
) -> dict:
    question = body.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question is required",
        )

    provider = build_provider()
    try:
        answer = ask_assistant(provider, question)
    except AssistantError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider unavailable",
        ) from exc

    return answer.model_dump()
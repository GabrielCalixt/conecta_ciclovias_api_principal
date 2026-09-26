from pydantic import BaseModel


class ErroSchema(BaseModel):
    """Formato das respostas de erro (padrão do HTTPException do FastAPI)."""

    detail: str

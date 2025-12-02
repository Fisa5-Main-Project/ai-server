from pydantic import BaseModel

class VectorizationResponse(BaseModel):
    user_id: int
    persona_text: str
    status: str

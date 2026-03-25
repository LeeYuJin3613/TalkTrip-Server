from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional


app = FastAPI()


class MessageItem(BaseModel):
    id: int
    date: Optional[str] = None
    time: Optional[str] = None
    speaker: str
    message: str


class AnalyzeRequest(BaseModel):
    raw_text: str
    messages: List[MessageItem]


@app.post("/analyze")
def analyze_chat(data: AnalyzeRequest):
    print("=== FastAPI가 받은 데이터 ===")
    print("원본 텍스트:")
    print(data.raw_text)
    print("전처리 메시지:")
    for msg in data.messages:
        print(msg)

    return {
        "message": "FastAPI가 데이터를 잘 받았습니다.",
        "raw_text": data.raw_text,
        "message_count": len(data.messages),
        "messages": data.messages
    }
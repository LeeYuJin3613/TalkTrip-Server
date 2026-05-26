import json
from typing import List, Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel

from fastapi_app.inference.stage1 import predict_stage1
from fastapi_app.inference.stage2 import predict_stage2
from fastapi_app.inference.stage3 import predict_stage3
# 기존 코드
# from .schedule_builder import process as build_schedule

# 새로운 하이브리드 버전 사용
from .hybrid_schedule_builder import process

app = FastAPI()


class AnalyzeRequest(BaseModel):
    chat_file_id: int
    raw_text: str
    messages: List[Dict[str, Any]]


@app.post("/ai/analyze")
def analyze_chat(data: AnalyzeRequest):
    analyzed_messages = []

    for idx, msg in enumerate(data.messages):
        message_text = msg.get("message", "")
        context_text = msg.get("context") or message_text

        is_travel_related = predict_stage1(context_text)

        if is_travel_related:
            entities = predict_stage2(message_text)
            intent = predict_stage3(message_text)
        else:
            entities = []
            intent = "NOT_TRAVEL"

        result = {
            "source": f"chat_{data.chat_file_id}",
            "global_idx": idx + 1,
            "timestamp": msg.get("timestamp", ""),
            "text": message_text,
            "context": context_text,
            "in_travel_span": is_travel_related,
            "intent": intent,
            "entities": entities,
        }

        analyzed_messages.append(result)

        print(
            f"[{idx + 1}] {result['timestamp']} | "
            f"{message_text} | "
            f"travel={is_travel_related} | "
            f"intent={intent} | "
            f"entities={entities}"
        )

    trip_summaries = process(analyzed_messages, verbose=True)
    print("=== 최종 일정표 JSON ===")
    print(json.dumps(trip_summaries, ensure_ascii=False, indent=2))
    return {
        "status": "success",
        "chat_file_id": data.chat_file_id,
        "message_count": len(data.messages),
        "analyzed_messages": analyzed_messages,
        "trip_summaries": trip_summaries,
    }

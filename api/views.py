import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .preprocess import parse_kakao_chat
from .models import ChatFile, ParsedMessage


@csrf_exempt
def receive_kakao_text(request):
    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8"))
            raw_text = body.get("kakao_text", "")

            if not raw_text:
                return JsonResponse(
                    {"error": "kakao_text가 비어 있습니다."},
                    status=400
                )

            print("=== Django가 받은 원본 텍스트 ===")
            print(raw_text)

            messages = parse_kakao_chat(raw_text)

            chat_file_obj = ChatFile.objects.create(
                user_id=None,
                message_count=len(messages),
            )

            parsed_objects = [
                ParsedMessage(
                    chat_file=chat_file_obj,
                    global_idx=idx + 1,
                    sent_time=msg.get("timestamp", ""),
                    message=msg.get("message", ""),
                    is_travel_related=False,
                )
                for idx, msg in enumerate(messages)
            ]

            ParsedMessage.objects.bulk_create(parsed_objects)

            print(f"=== DB 저장 완료: {len(parsed_objects)}건 ===")

            try:
                fastapi_response = requests.post(
                    "http://127.0.0.1:8001/analyze",
                    json={
                        "chat_file_id": chat_file_obj.id,
                        "raw_text": raw_text,
                        "messages": messages,
                    },
                    timeout=5,
                )
                fastapi_result = fastapi_response.json()
            except Exception as e:
                fastapi_result = {
                    "warning": f"FastAPI 연결 실패: {str(e)}"
                }

            return JsonResponse({
                "message": "카카오톡 텍스트 수신, 전처리, DB 저장 성공",
                "chat_file_id": chat_file_obj.id,
                "preprocessed_count": len(messages),
                "parsed_messages": messages,
                "fastapi_result": fastapi_result,
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"error": "POST 요청만 가능합니다."}, status=405)


def test_connection(request):
    return JsonResponse({
        "message": "백엔드와 성공적으로 연결되었습니다!"
    })
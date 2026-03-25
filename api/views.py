import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .preprocess import parse_kakao_chat


@csrf_exempt
def receive_kakao_text(request):
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            raw_text = body.get('kakao_text', '')

            print("=== Django가 받은 원본 텍스트 ===")
            print(raw_text)

            messages = parse_kakao_chat(raw_text)

            print("=== Django 전처리 결과 ===")
            for msg in messages:
                print(msg)

            fastapi_response = requests.post(
                'http://127.0.0.1:8001/analyze',
                json={
                    'raw_text': raw_text,
                    'messages': messages
                }
            )

            fastapi_result = fastapi_response.json()

            print("=== FastAPI 응답 ===")
            print(fastapi_result)

            return JsonResponse({
                'message': 'Django -> FastAPI 전송 성공',
                'preprocessed_count': len(messages),
                'fastapi_result': fastapi_result
            })

        except Exception as e:
            print("에러:", str(e))
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'POST 요청만 가능합니다.'}, status=405)
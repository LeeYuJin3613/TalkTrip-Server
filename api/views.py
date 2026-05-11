import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .preprocess import parse_kakao_chat
from .models import ChatMessage  # 1. DB 모델 임포트 확인


@csrf_exempt
def receive_kakao_text(request):
    if request.method == 'POST':
        try:
            # 2. 업로드된 파일을 가져옵니다. (프론트에서 'file' 키로)
            chat_file = request.FILES.get('file')

            if not chat_file:
                return JsonResponse({"error": "업로드된 파일이 없습니다."}, status=400)

            # 3. 파일 내용 읽기 및 디코딩 (UTF-8 우선, 실패 시 CP949)
            try:
                raw_text = chat_file.read().decode('utf-8')
            except UnicodeDecodeError:
                chat_file.seek(0)
                raw_text = chat_file.read().decode('cp949')

            # 4. preprocess.py의 파싱 함수 실행 (이름 지우기 등 전처리)
            messages = parse_kakao_chat(raw_text)

            # 5. DB에 대량 저장 (Bulk Create)
            chat_objects = [
                ChatMessage(
                    chat_time=msg['timestamp'],
                    content=msg['message']
                ) for msg in messages
            ]
            ChatMessage.objects.bulk_create(chat_objects)

            print(f"=== DB 저장 완료: {len(chat_objects)}건 ===")

            try:
                fastapi_response = requests.post(
                    'http://127.0.0.1:8001/analyze',
                    json={
                        'raw_text': raw_text,
                        'messages': messages
                    },
                    timeout=5
                )
                fastapi_result = fastapi_response.json()
            except Exception as e:
                fastapi_result = {"warning": f"FastAPI 연결 실패: {str(e)}"}

            return JsonResponse({
                'message': '파일 업로드 및 전처리 성공',
                'preprocessed_count': len(messages),
                'parsed_messages': messages,
                'fastapi_result': fastapi_result
            })

        except Exception as e:
            print("에러:", str(e))
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'POST 요청만 가능합니다.'}, status=405)


# 테스트용 연결 확인 뷰
def test_connection(request):
    data = {
        "message": "백엔드와 성공적으로 연결되었습니다!"
    }
    return JsonResponse(data)
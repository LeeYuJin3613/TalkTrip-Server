import json
import requests
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .preprocess import parse_kakao_chat
from .models import (
    ChatFile,
    ParsedMessage,
    AIExtractionResult,
    TripPlan,
    Day,
    Place,
    Event,
)

from datetime import datetime, timedelta
def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_datetime(base_date, time_value):
    if not base_date or not time_value:
        return None

    try:
        parsed_time = datetime.strptime(
            time_value,
            "%H:%M"
        ).time()

        naive_datetime = datetime.combine(
            base_date,
            parsed_time
        )

        return timezone.make_aware(
            naive_datetime
        )

    except ValueError:
        return None

def search_kakao_place(place_name, region=None):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    headers = {
        "Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"
    }

    query = place_name

    # 지역명 같이 검색하면 정확도 상승
    if region:
        query = f"{region} {place_name}"

    params = {
        "query": query
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
    )
    print(response.status_code)
    print(response.text)

    result = response.json()

    documents = result.get("documents", [])

    if documents:
        place = documents[0]

        return {
            "latitude": float(place["y"]),
            "longitude": float(place["x"]),
        }

    return None

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
                print("=== FastAPI 호출 직전 ===")
                print("FastAPI URL:", "http://127.0.0.1:8001/ai/analyze")
                print("message count:", len(messages))

                fastapi_response = requests.post(
                    "http://127.0.0.1:8001/ai/analyze",
                    json={
                        "chat_file_id": chat_file_obj.id,
                        "raw_text": raw_text,
                        "messages": messages,
                    },
                    timeout=30,
                )

                print("=== FastAPI 응답 상태 ===")
                print("status_code:", fastapi_response.status_code)
                print("response_text:", fastapi_response.text)

                fastapi_result = fastapi_response.json()
                print("=== fastapi_result 타입 ===")
                print(type(fastapi_result))
                print("=== fastapi_result 실제 내용 ===")
                print(json.dumps(fastapi_result, ensure_ascii=False, indent=2))

                # FastAPI 응답 구조 대응
                if isinstance(fastapi_result, dict):
                    result = fastapi_result.get("trip_summaries", [{}])[0]
                else:
                    result = {}

                print("=== DB 저장에 사용할 result ===")
                print(json.dumps(result, ensure_ascii=False, indent=2))

                print("destination:", result.get("destination"))
                print("duration:", result.get("duration"))
                print("start_date:", result.get("start_date"))
                print("days 개수:", len(result.get("days", [])))

                print("=== DB 저장에 사용할 result ===")
                print(json.dumps(result, ensure_ascii=False, indent=2))
                AIExtractionResult.objects.create(
                    chat_file=chat_file_obj,
                    confidence=result.get("confidence"),
                    extracted_json=result,
                )

                start_date = parse_date(result.get("start_date"))

                trip_plan = TripPlan.objects.create(
                    chat_file=chat_file_obj,
                    trip_name=f"{result.get('destination', '여행')} 일정",
                    thumbnail_url=None,
                    destination=result.get("destination"),
                    duration=result.get("duration"),
                    departure_date=start_date,
                    return_date=None,
                    status="planning",
                )

                for day_data in result.get("days", []):
                    day_number = day_data.get("day")

                    actual_date = None
                    if start_date and day_number:
                        actual_date = start_date + timedelta(days=int(day_number) - 1)

                    day_obj = Day.objects.create(
                        trip_plan=trip_plan,
                        day_number=day_number,
                        actual_date=actual_date,
                    )

                    for event_data in day_data.get("events", []):
                        location = event_data.get("location")
                        if not location:
                            continue

                        place_data = search_kakao_place(
                            location,
                            result.get("destination")
                        )

                        latitude = None
                        longitude = None

                        if place_data:
                            latitude = place_data["latitude"]
                            longitude = place_data["longitude"]

                        print("장소:", location)
                        print("검색 결과:", place_data)
                        print("위도:", latitude)
                        print("경도:", longitude)

                        place_obj, created = Place.objects.get_or_create(
                            name=location,
                            region=result.get("destination"),
                            defaults={
                                "type": event_data.get("category"),
                                "latitude": latitude,
                                "longitude": longitude,
                            },
                        )

                        # 이미 존재하면 좌표 업데이트
                        if not created:
                            place_obj.latitude = latitude
                            place_obj.longitude = longitude
                            place_obj.type = event_data.get("category")
                            place_obj.save()

                        Event.objects.create(
                            day=day_obj,
                            place=place_obj,
                            start_datetime=parse_datetime(
                                actual_date,
                                event_data.get("time"),
                            ),
                            end_datetime=None,
                            activity=event_data.get("memo") or event_data.get("source_text"),
                        )

            except Exception as e:
                print("=== FastAPI 연결 실패 ===")
                print(str(e))

                fastapi_result = {
                    "warning": f"FastAPI 연결 실패: {str(e)}"
                }

            return JsonResponse({
                "message": "카카오톡 텍스트 수신, 전처리, DB 저장, AI 일정 저장 성공",
                "chat_file_id": chat_file_obj.id,
                "trip_plan_id": trip_plan.id if "trip_plan" in locals() else None,
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
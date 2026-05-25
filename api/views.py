import json
import math
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
    Route,
    RouteRecommendation
)

from datetime import datetime, timedelta
def calculate_distance_m(lat1, lon1, lat2, lon2):
    R = 6371000

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def get_middle_point(lat1, lng1, lat2, lng2):
    return (
        (lat1 + lat2) / 2,
        (lng1 + lng2) / 2,
    )

def get_route_by_osrm(from_lat, from_lng, to_lat, to_lng):
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{from_lng},{from_lat};{to_lng},{to_lat}"
    )

    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    response = requests.get(url, params=params, timeout=10)

    if response.status_code != 200:
        return None

    data = response.json()
    routes = data.get("routes", [])

    if not routes:
        return None

    route = routes[0]

    return {
        "distance": route.get("distance"),
        "duration": route.get("duration"),
        "route_geometry": route.get("geometry"),
    }


def search_kakao_keyword_places(
    keyword,
    x=None,
    y=None,
    radius=5000,
    size=10,
):
    url = "https://dapi.kakao.com/v2/local/search/keyword.json"

    headers = {
        "Authorization": f"KakaoAK {settings.KAKAO_REST_API_KEY}"
    }

    params = {
        "query": keyword,
        "size": size,
    }

    if x and y:
        params["x"] = x
        params["y"] = y
        params["radius"] = radius

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=10,
    )

    if response.status_code != 200:
        return []

    return response.json().get("documents", [])


def get_min_distance_from_route(place_lat, place_lng, route_geometry):
    coordinates = route_geometry.get("coordinates", [])

    min_distance = None

    for lng, lat in coordinates:
        distance = calculate_distance_m(
            place_lat,
            place_lng,
            lat,
            lng,
        )

        if min_distance is None or distance < min_distance:
            min_distance = distance

    return min_distance
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

def generate_route_recommendations(trip_plan, max_count=3):
    routes = Route.objects.filter(
        from_event__day__trip_plan=trip_plan
    ).select_related(
        "from_event__place",
        "to_event__place",
    )

    used_place_names = set(
        Event.objects.filter(
            day__trip_plan=trip_plan
        ).values_list(
            "place__name",
            flat=True
        )
    )

    keywords = [
        {"keyword": "카페", "category": "CAFE"},
        {"keyword": "음식점", "category": "FOOD"},
        {"keyword": "관광명소", "category": "TOUR"},
    ]

    created_count = 0

    for route in routes:
        if created_count >= max_count:
            break

        from_place = route.from_event.place
        to_place = route.to_event.place

        if not from_place.latitude or not from_place.longitude:
            continue

        if not to_place.latitude or not to_place.longitude:
            continue

        route_data = get_route_by_osrm(
            from_place.latitude,
            from_place.longitude,
            to_place.latitude,
            to_place.longitude,
        )

        if not route_data:
            print("=== 경로 생성 실패 ===")
            continue

        print("=== 경로 생성 성공 ===")
        print(route_data)

        route.distance = route_data["distance"]
        route.duration = route_data["duration"]
        route.route_geometry = route_data["route_geometry"]
        route.save()

        for item in keywords:
            if created_count >= max_count:
                break

            middle_lat, middle_lng = get_middle_point(
                from_place.latitude,
                from_place.longitude,
                to_place.latitude,
                to_place.longitude,
            )

            kakao_places = search_kakao_keyword_places(
                item["keyword"],
                x=middle_lng,
                y=middle_lat,
                radius=5000,
                size=10,
            )
            print("=== 카카오 검색 결과 ===")
            print(kakao_places[:2])

            for kakao_place in kakao_places:
                if created_count >= max_count:
                    break

                name = kakao_place.get("place_name")

                if not name or name in used_place_names:
                    continue

                lat = float(kakao_place["y"])
                lng = float(kakao_place["x"])

                distance_from_route = get_min_distance_from_route(
                    lat,
                    lng,
                    route.route_geometry,
                )
                print("후보 장소:", name)
                print("경로 거리:", distance_from_route)

                if distance_from_route is None:
                    continue

                if distance_from_route > 500:
                    continue

                score = max(0.1, 1 - distance_from_route / 500)

                place_obj, _ = Place.objects.get_or_create(
                    name=name,
                    defaults={
                        "source": "KAKAO",
                        "source_place_id": kakao_place.get("id", ""),
                        "category": item["category"],
                        "address": kakao_place.get("road_address_name") or kakao_place.get("address_name"),
                        "latitude": lat,
                        "longitude": lng,
                    }
                )

                RouteRecommendation.objects.create(
                    route=route,
                    place=place_obj,
                    category=item["category"],
                    distance_from_route=distance_from_route,
                    score=round(score, 3),
                )
                print("=== 추천 저장 완료 ===")
                print(name, score)
                used_place_names.add(name)
                created_count += 1

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

                    saved_events = []

                    for index, event_data in enumerate(day_data.get("events", [])):
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
                            print("=== 장소 좌표 ===")
                            print(location, latitude, longitude)

                        place_obj, created = Place.objects.get_or_create(
                            name=location,
                            defaults={
                                "source": "KAKAO",
                                "source_place_id": "",
                                "category": event_data.get("category") or "ETC",
                                "address": result.get("destination"),
                                "latitude": latitude,
                                "longitude": longitude,
                            },
                        )

                        if not created:
                            place_obj.latitude = latitude
                            place_obj.longitude = longitude
                            place_obj.category = event_data.get("category") or place_obj.category
                            place_obj.address = result.get("destination") or place_obj.address
                            place_obj.save()

                        event_obj = Event.objects.create(
                            day=day_obj,
                            place=place_obj,
                            sequence=index + 1,
                            start_datetime=parse_datetime(
                                actual_date,
                                event_data.get("time"),
                            ),
                            end_datetime=None,
                            activity=event_data.get("memo") or event_data.get("source_text"),
                        )

                        saved_events.append(event_obj)

                    for i in range(len(saved_events) - 1):
                        Route.objects.create(
                            from_event=saved_events[i],
                            to_event=saved_events[i + 1],
                            distance=None,
                            duration=None,
                            route_geometry=None,
                        )

                generate_route_recommendations(trip_plan, max_count=3)

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

def trip_plan_detail(request, trip_plan_id):
    try:
        trip_plan = TripPlan.objects.get(id=trip_plan_id)

        days_data = []

        for day in trip_plan.days.all().order_by("day_number"):
            events_data = []

            for event in day.events.all().order_by("sequence"):
                place = event.place

                events_data.append({
                    "id": event.id,
                    "time": event.start_datetime.strftime("%H:%M") if event.start_datetime else None,
                    "place_name": place.name,
                    "activity": event.activity,
                    "latitude": place.latitude,
                    "longitude": place.longitude,
                    "is_recommended": False,
                })

                routes = Route.objects.filter(
                    from_event=event
                ).prefetch_related(
                    "recommendations__place"
                )

                for route in routes:
                    for rec in route.recommendations.all():
                        rec_place = rec.place

                        events_data.append({
                            "id": rec.id,
                            "time": None,
                            "place_name": rec_place.name,
                            "activity": "추천 장소",
                            "latitude": rec_place.latitude,
                            "longitude": rec_place.longitude,
                            "category": rec.category,
                            "is_recommended": True,
                            "score": rec.score,
                        })
            days_data.append({
                "day": day.day_number,
                "date": str(day.actual_date) if day.actual_date else None,
                "events": events_data,
            })

        return JsonResponse({
            "id": trip_plan.id,
            "trip_name": trip_plan.trip_name,
            "destination": trip_plan.destination,
            "duration": trip_plan.duration,
            "departure_date": str(trip_plan.departure_date) if trip_plan.departure_date else None,
            "return_date": str(trip_plan.return_date) if trip_plan.return_date else None,
            "days": days_data,
        })

    except TripPlan.DoesNotExist:
        return JsonResponse(
            {"error": "일정을 찾을 수 없습니다."},
            status=404
        )
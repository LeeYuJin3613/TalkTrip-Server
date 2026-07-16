import json
import math
import requests
import os
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
def search_tour_location_places(map_x, map_y, radius=3000, content_type_id=None):
    url = "https://apis.data.go.kr/B551011/KorService2/locationBasedList2"

    params = {
        "serviceKey": settings.TOUR_API_SERVICE_KEY,
        "MobileOS": "ETC",
        "MobileApp": "TalkTrip",
        "_type": "json",
        "mapX": map_x,
        "mapY": map_y,
        "radius": radius,
        "numOfRows": 10,
        "pageNo": 1,
        "arrange": "E",
    }

    if content_type_id:
        params["contentTypeId"] = content_type_id

    try:
        response = requests.get(url, params=params, timeout=10)

        print("관광공사 위치기반 요청:", response.url)
        print("상태 코드:", response.status_code)
        print("응답:", response.text[:500])

        if response.status_code != 200:
            return []

        data = response.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        if isinstance(items, dict):
            items = [items]

        if items == "":
            return []

        return items

    except Exception as e:
        print("관광공사 위치기반 API 실패:", str(e))
        return []

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

def build_preference_profile(ai_items):
    profile = {
        "FOOD": 0.0,
        "TOUR": 0.0,
        "ACTIVITY": 0.0,
    }

    intent_weight = {
        "PROPOSE": 1.0,
        "AGREE": 1.5,
        "CONFIRM": 2.0,
        "QUERY": 0.3,
        "DISAGREE": -1.0,
        "CANCEL": -2.0,
        "OTHER": 0.0,
    }

    entity_category_map = {
        "FOOD": "FOOD",
        "LOC": "TOUR",
        "ACTIVITY": "ACTIVITY",
    }

    for item in ai_items:
        if not item.get("in_travel_span", item.get("travel", False)):
            continue

        intent = item.get("intent_primary") or item.get("intent") or "OTHER"
        weight = intent_weight.get(intent, 0.0)

        if weight == 0:
            continue

        for entity in item.get("entities", []):
            entity_type = entity.get("type")
            category = entity_category_map.get(entity_type)

            if category:
                profile[category] += weight

    for key in profile:
        profile[key] = max(0.0, profile[key])

    max_score = max(profile.values())

    if max_score > 0:
        profile = {
            key: round(value / max_score, 3)
            for key, value in profile.items()
        }

    return profile


def calculate_recommendation_score(distance_from_route, category, preference_profile):
    route_score = max(0.1, 1 - distance_from_route / 1500)
    preference_score = preference_profile.get(category, 0.0) * 0.4

    return round(route_score + preference_score, 3)

def generate_route_recommendations(
    trip_plan,
    preference_profile=None,
    max_count=3,
    max_routes=3,
    max_per_route=1,
):
    if preference_profile is None:
        preference_profile = {
            "FOOD": 0.0,
            "TOUR": 0.0,
            "ACTIVITY": 0.0,
        }

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

    content_types = [
        {"content_type_id": "39", "category": "FOOD"},
        {"content_type_id": "12", "category": "TOUR"},
        {"content_type_id": "28", "category": "ACTIVITY"},
    ]

    route_infos = []

    for route in routes:
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
            continue

        route.distance = route_data["distance"]
        route.duration = route_data["duration"]
        route.route_geometry = route_data["route_geometry"]
        route.save()

        route_infos.append({
            "route": route,
            "distance": route.distance or 0,
        })

    route_infos.sort(
        key=lambda x: x["distance"],
        reverse=True,
    )

    route_infos = route_infos[:max_routes]

    candidates = []

    for route_info in route_infos:
        route = route_info["route"]
        from_place = route.from_event.place
        to_place = route.to_event.place


        middle_lat, middle_lng = get_middle_point(
            from_place.latitude,
            from_place.longitude,
            to_place.latitude,
            to_place.longitude,
        )

        for item in content_types:
            tour_places = search_tour_location_places(
                map_x=middle_lng,
                map_y=middle_lat,
                radius=5000,
                content_type_id=item["content_type_id"],
            )

            for tour_place in tour_places:
                name = tour_place.get("title")

                if not name or name in used_place_names:
                    continue

                try:
                    lat = float(tour_place.get("mapy"))
                    lng = float(tour_place.get("mapx"))
                except (TypeError, ValueError):
                    continue

                distance_from_route = get_min_distance_from_route(
                    lat,
                    lng,
                    route.route_geometry,
                )

                if distance_from_route is None:
                    continue

                if distance_from_route > 1500:
                    continue

                score = calculate_recommendation_score(
                    distance_from_route=distance_from_route,
                    category=item["category"],
                    preference_profile=preference_profile,
                )

                candidates.append({
                    "route": route,
                    "tour_place": tour_place,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                    "category": item["category"],
                    "distance_from_route": distance_from_route,
                    "score": score,
                })

    candidates.sort(key=lambda x: x["score"], reverse=True)

    selected_candidates = []
    selected_names = set()
    selected_route_counts = {}

    for candidate in candidates:
        if len(selected_candidates) >= max_count:
            break

        route_id = candidate["route"].id

        if candidate["name"] in selected_names:
            continue

        if selected_route_counts.get(route_id, 0) >= max_per_route:
            continue

        selected_candidates.append(candidate)
        selected_names.add(candidate["name"])
        selected_route_counts[route_id] = selected_route_counts.get(route_id, 0) + 1

    for candidate in selected_candidates:
        tour_place = candidate["tour_place"]

        place_obj, _ = Place.objects.get_or_create(
            name=candidate["name"],
            defaults={
                "source": "TOUR_API",
                "source_place_id": str(tour_place.get("contentid", "")),
                "category": candidate["category"],
                "address": tour_place.get("addr1"),
                "latitude": candidate["lat"],
                "longitude": candidate["lng"],
                "image_url": tour_place.get("firstimage"),
            }
        )

        if RouteRecommendation.objects.filter(
            route=candidate["route"],
            place=place_obj,
        ).exists():
            continue

        RouteRecommendation.objects.create(
            route=candidate["route"],
            place=place_obj,
            category=candidate["category"],
            distance_from_route=candidate["distance_from_route"],
            score=candidate["score"],
        )
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
                        from_event = saved_events[i]
                        to_event = saved_events[i + 1]

                        route_data = get_route_by_osrm(
                            from_event.place.latitude,
                            from_event.place.longitude,
                            to_event.place.latitude,
                            to_event.place.longitude,
                        )

                        Route.objects.create(
                            from_event=from_event,
                            to_event=to_event,
                            distance=route_data.get("distance") if route_data else None,
                            duration=route_data.get("duration") if route_data else None,
                            route_geometry=route_data.get("route_geometry") if route_data else None,
                        )
                ai_items = (
                        fastapi_result.get("analyzed_messages")
                        or fastapi_result.get("results")
                        or fastapi_result.get("messages")
                        or result.get("messages")
                        or result.get("items")
                        or []
                )

                preference_profile = build_preference_profile(ai_items)

                print("=== 취향 프로필 ===")
                print(preference_profile)

                generate_route_recommendations(
                    trip_plan,
                    preference_profile=preference_profile,
                    max_count=3,
                    max_routes=3,
                    max_per_route=1,
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
                            "activity": "이동 중 함께 들러보기 좋은 장소",
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
        routes_data = []

        for route in Route.objects.filter(
                from_event__day__trip_plan=trip_plan
        ).select_related(
            "from_event__place",
            "to_event__place",
            "from_event__day",
        ).order_by(
            "from_event__day__day_number",
            "from_event__sequence",
        ):
            routes_data.append({
                "id": route.id,
                "from_event_id": route.from_event.id,
                "to_event_id": route.to_event.id,
                "from_place": route.from_event.place.name,
                "to_place": route.to_event.place.name,
                "day": route.from_event.day.day_number,
                "distance": route.distance,
                "duration": route.duration,
                "route_geometry": route.route_geometry,
            })
        return JsonResponse({
            "id": trip_plan.id,
            "trip_name": trip_plan.trip_name,
            "destination": trip_plan.destination,
            "duration": trip_plan.duration,
            "departure_date": str(trip_plan.departure_date) if trip_plan.departure_date else None,
            "return_date": str(trip_plan.return_date) if trip_plan.return_date else None,
            "days": days_data,
            "routes": routes_data,
        })

    except TripPlan.DoesNotExist:
        return JsonResponse(
            {"error": "일정을 찾을 수 없습니다."},
            status=404
        )
@csrf_exempt
def confirm_trip_plan(request, trip_plan_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST 요청만 가능합니다."}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8"))
        days = body.get("days", [])

        trip_plan = TripPlan.objects.get(id=trip_plan_id)
        route_cache = {}

        for route in Route.objects.filter(
                from_event__day__trip_plan=trip_plan
        ).select_related(
            "from_event__place",
            "to_event__place",
        ):
            key = (
                route.from_event.place.name,
                route.to_event.place.name,
            )

            if route.route_geometry:
                route_cache[key] = {
                    "distance": route.distance,
                    "duration": route.duration,
                    "route_geometry": route.route_geometry,
                }
        # 기존 Day/Event/Route/Recommendation 삭제
        RouteRecommendation.objects.filter(
            route__from_event__day__trip_plan=trip_plan
        ).delete()

        Route.objects.filter(
            from_event__day__trip_plan=trip_plan
        ).delete()

        Event.objects.filter(
            day__trip_plan=trip_plan
        ).delete()

        Day.objects.filter(
            trip_plan=trip_plan
        ).delete()

        # 프론트에서 보낸 최종 일정 다시 저장
        for day_data in days:
            day_obj = Day.objects.create(
                trip_plan=trip_plan,
                day_number=day_data.get("day"),
                actual_date=day_data.get("date") or None,
            )

            saved_events = []

            for index, event_data in enumerate(day_data.get("events", [])):
                # 추천 장소를 사용자가 선택 안 했다면 저장 제외

                place_obj, _ = Place.objects.get_or_create(
                    name=event_data.get("place_name"),
                    defaults={
                        "source": "TOUR_API" if event_data.get("is_recommended") else "KAKAO",
                        "source_place_id": "",
                        "category": event_data.get("category") or "ETC",
                        "latitude": event_data.get("latitude"),
                        "longitude": event_data.get("longitude"),
                    }
                )

                place_obj.latitude = event_data.get("latitude")
                place_obj.longitude = event_data.get("longitude")
                place_obj.category = event_data.get("category") or place_obj.category
                place_obj.save()

                event_obj = Event.objects.create(
                    day=day_obj,
                    place=place_obj,
                    sequence=len(saved_events) + 1,
                    start_datetime=None,
                    end_datetime=None,
                    activity=event_data.get("activity"),
                )

                saved_events.append(event_obj)

            for i in range(len(saved_events) - 1):
                from_event = saved_events[i]
                to_event = saved_events[i + 1]

                key = (
                    from_event.place.name,
                    to_event.place.name,
                )

                route_data = route_cache.get(key)

                if not route_data:
                    route_data = None

                    if (
                            from_event.place.latitude and from_event.place.longitude and
                            to_event.place.latitude and to_event.place.longitude
                    ):
                        route_data = get_route_by_osrm(
                            from_event.place.latitude,
                            from_event.place.longitude,
                            to_event.place.latitude,
                            to_event.place.longitude,
                        )

                Route.objects.create(
                    from_event=from_event,
                    to_event=to_event,
                    distance=route_data.get("distance") if route_data else None,
                    duration=route_data.get("duration") if route_data else None,
                    route_geometry=route_data.get("route_geometry") if route_data else None,
                )

        trip_plan.status = "confirmed"
        trip_plan.save()

        # generate_route_recommendations(
        #     trip_plan,
        #     max_count=3,
        #     max_routes=3,
        #     max_per_route=1,
        # )

        return JsonResponse({
            "message": "일정이 확정 저장되었습니다.",
            "trip_plan_id": trip_plan.id,
        })

    except TripPlan.DoesNotExist:
        return JsonResponse({"error": "일정을 찾을 수 없습니다."}, status=404)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=400)
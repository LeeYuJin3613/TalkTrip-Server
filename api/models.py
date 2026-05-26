from django.db import models


class ChatFile(models.Model):
    user_id = models.BigIntegerField(null=True, blank=True)
    source = models.CharField(max_length=100, null=True, blank=True)
    message_count = models.BigIntegerField(default=0)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_file"

    def __str__(self):
        return f"{self.source} ({self.message_count} messages)"


class ParsedMessage(models.Model):
    chat_file = models.ForeignKey(
        ChatFile,
        on_delete=models.CASCADE,
        related_name="parsed_messages"
    )
    global_idx = models.BigIntegerField()
    sent_time = models.CharField(max_length=20)
    message = models.TextField()
    is_travel_related = models.BooleanField(default=False)

    class Meta:
        db_table = "parsed_message"

    def __str__(self):
        return f"[{self.sent_time}] {self.message[:20]}"


class AIExtractionResult(models.Model):
    chat_file = models.ForeignKey(
        ChatFile,
        on_delete=models.CASCADE,
        related_name="ai_results"
    )
    confidence = models.FloatField(null=True, blank=True)
    extracted_json = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_extraction_result"


class TripPlan(models.Model):
    chat_file = models.ForeignKey(
        ChatFile,
        on_delete=models.CASCADE,
        related_name="trip_plans"
    )
    trip_name = models.CharField(max_length=100, null=True, blank=True)
    thumbnail_url = models.CharField(max_length=255, null=True, blank=True)
    destination = models.CharField(max_length=100, null=True, blank=True)
    duration = models.CharField(max_length=50, null=True, blank=True)
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, default="planning")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trip_plan"


class Day(models.Model):
    trip_plan = models.ForeignKey(
        TripPlan,
        on_delete=models.CASCADE,
        related_name="days"
    )
    day_number = models.BigIntegerField()
    actual_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "day"


class Place(models.Model):
    SOURCE_CHOICES = [
        ("KAKAO", "카카오맵"),
        ("TOUR_API", "관광데이터 API"),
        ("OSM", "OpenStreetMap"),
        ("USER", "사용자 직접 입력"),
    ]

    CATEGORY_CHOICES = [
        ("FOOD", "식당"),
        ("LODGING", "숙소"),
        ("ACTIVITY", "액티비티"),
        ("TOUR", "관광지"),
        ("CAFE", "카페"),
        ("ETC", "기타"),
    ]

    name = models.CharField(max_length=100)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    source = models.CharField(
        max_length=30,
        choices=SOURCE_CHOICES,
        default="USER"
    )

    source_place_id = models.CharField(
        max_length=100,
        default=""
    )

    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="ETC"
    )

    address = models.CharField(max_length=255, null=True, blank=True)

    image_url = models.CharField(
        max_length=500,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "place"

    def __str__(self):
        return self.name


class Event(models.Model):
    day = models.ForeignKey(
        Day,
        on_delete=models.CASCADE,
        related_name="events"
    )
    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="events"
    )

    sequence = models.BigIntegerField(default=0)

    start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)

    activity = models.CharField(max_length=255, null=True, blank=True)
    memo = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "event"
        ordering = ["sequence"]

    def __str__(self):
        return f"{self.sequence}. {self.place.name}"


class Route(models.Model):
    from_event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="routes_from"
    )
    to_event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="routes_to"
    )

    distance = models.FloatField(null=True, blank=True)
    duration = models.IntegerField(null=True, blank=True)

    route_geometry = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "route"

    def __str__(self):
        return f"{self.from_event} -> {self.to_event}"


class RouteRecommendation(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="recommendations"
    )
    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="route_recommendations"
    )

    category = models.CharField(max_length=50, null=True, blank=True)
    distance_from_route = models.FloatField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "route_recommendation"

    def __str__(self):
        return f"{self.route} - {self.place.name}"
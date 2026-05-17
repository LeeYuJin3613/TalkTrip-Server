from django.db import models


class ChatFile(models.Model):
    user_id = models.BigIntegerField(null=True, blank=True)
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
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=50, null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "place"


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
    start_datetime = models.DateTimeField(null=True, blank=True)
    end_datetime = models.DateTimeField(null=True, blank=True)
    activity = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "event"
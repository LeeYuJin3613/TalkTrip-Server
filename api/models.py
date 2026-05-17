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
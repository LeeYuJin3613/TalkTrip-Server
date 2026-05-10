from django.db import models


# api/models.py
class ChatMessage(models.Model):
    chat_time = models.CharField(max_length=50)  # 정규화된 시간
    content = models.TextField()  # 정제된 내용

    is_travel_span = models.BooleanField(default=False)  # Stage 1 결과
    intent = models.CharField(max_length=20, null=True)  # Stage 3 결과 (PROPOSE, AGREE 등)
    entities = models.JSONField(null=True)  # Stage 2 결과 (LOC, TIME 등 JSON 저장)
    is_confirmed = models.BooleanField(default=False)  # Stage 5 결과 (일정 확정 여부)

    def __str__(self):
        return f"[{self.chat_time}] {self.content[:20]}..."
from django.urls import path
from .views import receive_kakao_text

urlpatterns = [
    path('api/chat-files/upload/', receive_kakao_text),
]
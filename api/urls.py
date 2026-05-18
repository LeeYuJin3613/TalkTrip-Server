from django.urls import path
from .views import receive_kakao_text, trip_plan_detail

urlpatterns = [
    path('api/chat-files/upload/', receive_kakao_text),
    path('api/trip-plans/<int:trip_plan_id>/',trip_plan_detail),
]
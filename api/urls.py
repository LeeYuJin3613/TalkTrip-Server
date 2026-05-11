from django.urls import path
from .views import receive_kakao_text

urlpatterns = [
    path('api/kakao/', receive_kakao_text),
]
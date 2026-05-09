from django.urls import path
from .views import receive_kakao_text
from . import views
urlpatterns = [
    path('api/kakao/', receive_kakao_text),
    path('api/test/', views.test_connection),
]
from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    path('', views.chatbot_view, name='chatbot'),
    path('suggestions/', views.get_suggestions, name='chatbot_suggestions'),
    path('search/', views.search_page, name='search'),
    path('search/api/', views.site_search_api, name='search_api'),
]
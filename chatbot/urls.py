from django.urls import path
from . import views
from . import call_center

app_name = 'chatbot'

urlpatterns = [
    path('', views.chatbot_view, name='chatbot'),
    path('suggestions/', views.get_suggestions, name='chatbot_suggestions'),
    path('session-status/', views.session_status, name='session_status'),
    path('search/', views.search_page, name='search'),
    path('search/api/', views.site_search_api, name='search_api'),

    # Call centre: the queue the bot hands escalations to.
    path('call-center/', call_center.dashboard, name='call_center'),
    path('call-center/api/', call_center.queue_api, name='call_center_api'),
    path('call-center/<int:pk>/', call_center.detail, name='call_center_detail'),
    path('call-center/<int:pk>/claim/', call_center.claim, name='call_center_claim'),
    path('call-center/<int:pk>/release/', call_center.release, name='call_center_release'),
    path('call-center/<int:pk>/reply/', call_center.reply, name='call_center_reply'),

    # The full chat log, read-only. Declared after <int:pk> so the two never
    # compete for the same path.
    path('call-center/chats/', call_center.chats, name='call_center_chats'),
    path('call-center/chats/<str:session_id>/', call_center.chat_detail,
         name='call_center_chat'),
    path('call-center/chats/<str:session_id>/escalate/', call_center.escalate,
         name='call_center_escalate'),
]

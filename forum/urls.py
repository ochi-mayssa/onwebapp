from django.urls import path
from . import views

app_name = 'forum'

urlpatterns = [
    path('', views.forum_home, name='home'),
    path('category/<slug:slug>/', views.category_detail, name='category'),
    path('tag/<slug:slug>/', views.tag_detail, name='tag'),
    path('new/', views.post_create, name='post_create'),
    path('post/<slug:slug>/', views.post_detail, name='post_detail'),
    path('post/<slug:slug>/edit/', views.post_edit, name='post_edit'),
    path('post/<slug:slug>/delete/', views.post_delete, name='post_delete'),
    path('post/<slug:slug>/vote/', views.post_vote, name='post_vote'),
    path('post/<slug:slug>/bookmark/', views.post_bookmark, name='post_bookmark'),
    path('post/<slug:slug>/pin/', views.post_pin, name='post_pin'),
    path('post/<slug:slug>/lock/', views.post_lock, name='post_lock'),
    path('post/<slug:slug>/hide/', views.post_hide, name='post_hide'),
    path('post/<slug:slug>/comment/', views.comment_create, name='comment_create'),
    path('post/<slug:slug>/report/', views.report_create, name='report_create'),
    path('comment/<int:comment_id>/vote/', views.comment_vote, name='comment_vote'),
    path('comment/<int:comment_id>/solution/', views.comment_solution, name='comment_solution'),
    path('comment/<int:comment_id>/delete/', views.comment_delete, name='comment_delete'),
    path('my-posts/', views.my_posts, name='my_posts'),
    path('search/', views.search, name='search'),
    path('user/<str:username>/', views.user_profile, name='user_profile'),
    path('user/<str:username>/follow/', views.follow_user, name='follow_user'),
    path('category/<slug:slug>/follow/', views.follow_category, name='follow_category'),
    path('leaderboard/', views.leaderboard, name='leaderboard'),
    path('events/', views.events, name='events'),
    path('jobs/', views.jobs, name='jobs'),
    path('jobs/new/', views.job_create, name='job_create'),
    path('moderation/', views.moderation, name='moderation'),
    path('moderation/report/<int:report_id>/resolve/', views.resolve_report, name='resolve_report'),
    path('showcase/', views.showcase, name='showcase'),
    path('api/posts.json', views.api_posts_json, name='api_posts_json'),
]
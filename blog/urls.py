from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    # Public
    path('', views.index, name='index'),
    path('articles/', views.articles, name='articles'),
    path('articles/<slug:slug>/', views.article_detail, name='article_detail'),
    path('post/<slug:slug>/', views.blog_detail, name='blog_detail'),

    # Management
    path('manage/articles/', views.manage_articles, name='manage_articles'),
    path('manage/articles/add/', views.add_article, name='add_article'),
    path('manage/articles/<int:pk>/edit/', views.edit_article, name='edit_article'),
    path('manage/articles/<int:pk>/delete/', views.delete_article, name='delete_article'),
    path('manage/posts/', views.manage_blog_posts, name='manage_blog_posts'),
    path('manage/posts/add/', views.add_blog_post, name='add_blog_post'),
    path('manage/posts/<int:pk>/edit/', views.edit_blog_post, name='edit_blog_post'),
    path('manage/posts/<int:pk>/delete/', views.delete_blog_post, name='delete_blog_post'),
]

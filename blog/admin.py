from django.contrib import admin
from .models import Article, BlogPost


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'tag', 'is_published', 'author', 'created_at')
    list_filter = ('tag', 'is_published', 'created_at')
    search_fields = ('title', 'description', 'content')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_published',)
    date_hierarchy = 'created_at'


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'tag', 'is_published', 'author', 'created_at')
    list_filter = ('tag', 'is_published', 'created_at')
    search_fields = ('title', 'description', 'content')
    prepopulated_fields = {'slug': ('title',)}
    list_editable = ('is_published',)
    date_hierarchy = 'created_at'

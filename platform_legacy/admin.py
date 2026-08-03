from django.contrib import admin
from .models import Link


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = ('title', 'link_type', 'url', 'created_at')
    list_filter = ('link_type',)
    search_fields = ('title', 'url')

from django.contrib import admin
from .models import DatabaseInitialization


@admin.register(DatabaseInitialization)
class DatabaseInitializationAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'is_initialized', 'initialized_at', 'created_at')
    list_filter = ('is_initialized',)
    readonly_fields = ('identifier', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

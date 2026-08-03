from django.contrib import admin
from .models import ConsultationRequest

@admin.register(ConsultationRequest)
class ConsultationRequestAdmin(admin.ModelAdmin):
    list_display = ('matricule', 'name', 'email', 'company', 'topic', 'created_at')
    list_filter = ('topic', 'created_at')
    search_fields = ('matricule', 'name', 'email', 'company', 'message')
    readonly_fields = ('matricule', 'created_at',)


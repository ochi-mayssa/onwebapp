from django.contrib import admin

from .models import (
    BillingProfile,
    BillingProfileLineItem,
    Document,
    DocumentEmail,
    DocumentEvent,
    DocumentLineItem,
    DocumentSettings,
    DocumentSignature,
    DocumentType,
)


class DocumentLineItemInline(admin.TabularInline):
    model = DocumentLineItem
    extra = 1


class BillingProfileLineItemInline(admin.TabularInline):
    model = BillingProfileLineItem
    extra = 1


@admin.register(BillingProfile)
class BillingProfileAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'customer', 'trigger', 'frequency', 'next_invoice_date',
        'auto_send', 'is_active', 'last_invoiced_at',
    )
    list_filter = ('trigger', 'frequency', 'auto_send', 'is_active')
    search_fields = ('name', 'customer__name', 'customer__email', 'project__title')
    readonly_fields = ('last_invoiced_at', 'last_document', 'created_at', 'updated_at')
    inlines = [BillingProfileLineItemInline]
    fieldsets = (
        ('Rule', {
            'fields': ('name', 'customer', 'project', 'doc_type', 'trigger',
                       'frequency', 'phase_type', 'is_active'),
        }),
        ('Pricing', {
            'fields': ('pricing_mode', 'default_description', 'default_amount',
                       'currency', 'discount_amount', 'tax_label', 'tax_rate', 'due_days'),
        }),
        ('Invoice content', {
            'fields': ('title_template', 'notes', 'terms'),
        }),
        ('Automation', {
            'fields': ('auto_send', 'next_invoice_date', 'last_invoiced_at',
                       'last_document', 'created_by', 'created_at', 'updated_at'),
        }),
    )


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'prefix', 'requires_acceptance', 'requires_signature', 'is_active')
    list_filter = ('is_active', 'requires_acceptance', 'requires_signature')
    prepopulated_fields = {'code': ('name',)}


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'doc_type', 'client_name', 'status', 'total', 'issue_date', 'due_date')
    list_filter = ('status', 'doc_type', 'currency')
    search_fields = ('reference', 'client_name', 'client_email', 'client_company')
    date_hierarchy = 'issue_date'
    readonly_fields = ('reference', 'pdf_sha256', 'pdf_generated_at', 'created_at', 'updated_at')
    inlines = [DocumentLineItemInline]


@admin.register(DocumentSettings)
class DocumentSettingsAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'signatory_name', 'updated_at')

    def has_add_permission(self, request):
        return not DocumentSettings.objects.exists()


@admin.register(DocumentEvent)
class DocumentEventAdmin(admin.ModelAdmin):
    list_display = ('document', 'event', 'actor_email', 'ip_address', 'created_at')
    list_filter = ('event',)
    search_fields = ('document__reference', 'actor_email')


@admin.register(DocumentEmail)
class DocumentEmailAdmin(admin.ModelAdmin):
    list_display = ('document', 'to_email', 'status', 'is_resend', 'created_at')
    list_filter = ('status', 'is_resend')


@admin.register(DocumentSignature)
class DocumentSignatureAdmin(admin.ModelAdmin):
    list_display = ('document', 'signer_name', 'signer_email', 'signed_at', 'document_version', 'is_valid')
    list_filter = ('is_valid',)
    search_fields = ('document__reference', 'signer_name', 'signer_email')
    readonly_fields = ('pdf_sha256', 'signed_at', 'ip_address', 'user_agent')

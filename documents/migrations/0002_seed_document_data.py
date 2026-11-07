from django.db import migrations


DOCUMENT_TYPES = [
    {
        'code': 'invoice',
        'name': 'Invoice',
        'prefix': 'INV',
        'description': 'Request for payment for delivered work or products.',
        'requires_acceptance': False,
        'requires_signature': False,
        'ordering': 10,
    },
    {
        'code': 'quotation',
        'name': 'Quotation',
        'prefix': 'QTN',
        'description': 'Priced offer the client can accept or reject.',
        'requires_acceptance': True,
        'requires_signature': False,
        'ordering': 20,
    },
    {
        'code': 'contract',
        'name': 'Contract',
        'prefix': 'CTR',
        'description': 'Agreement that requires the client\'s electronic signature.',
        'requires_acceptance': True,
        'requires_signature': True,
        'ordering': 30,
    },
    {
        'code': 'receipt',
        'name': 'Payment Receipt',
        'prefix': 'RCT',
        'description': 'Confirmation that a payment has been received.',
        'requires_acceptance': False,
        'requires_signature': False,
        'ordering': 40,
    },
    {
        'code': 'proposal',
        'name': 'Proposal',
        'prefix': 'PRP',
        'description': 'Scope and commercial proposal for client approval.',
        'requires_acceptance': True,
        'requires_signature': False,
        'ordering': 50,
    },
]


def seed(apps, schema_editor):
    DocumentType = apps.get_model('documents', 'DocumentType')
    DocumentSettings = apps.get_model('documents', 'DocumentSettings')

    for payload in DOCUMENT_TYPES:
        DocumentType.objects.update_or_create(code=payload['code'], defaults=payload)

    DocumentSettings.objects.get_or_create(pk=1, defaults={'company_name': 'OnWebApp'})


def unseed(apps, schema_editor):
    DocumentType = apps.get_model('documents', 'DocumentType')
    DocumentSettings = apps.get_model('documents', 'DocumentSettings')
    DocumentType.objects.filter(code__in=[item['code'] for item in DOCUMENT_TYPES]).delete()
    DocumentSettings.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

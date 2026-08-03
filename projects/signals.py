from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from .models import Project, ProjectPhase, PhaseTask, WorkflowNotification, Invoice
from users.models import ActivityLog, UserProfile
from django.core.mail import send_mail, EmailMessage
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from .utils import render_to_pdf
from django.core.files.base import ContentFile
from services import erp_utils
import threading

User = get_user_model()


def _send_welcome_email_async(username, email, site_url, default_from_email):
    msg = f"Welcome to OnWebApp, {username}! We're excited to start working with you."
    send_mail(
        subject="Welcome to OnWebApp!",
        message=f"Hi {username},\n\n{msg}\n\nAccess your dashboard here: {site_url}/projects/workflow/dashboard/\n\nBest regards,\nThe OnWebApp Team",
        from_email=default_from_email,
        recipient_list=[email],
        fail_silently=True,
    )


@receiver(post_save, sender=User)
def automated_welcome_message(sender, instance, created, **kwargs):
    """
    Trigger: New client added.
    Action: Send welcome message via WorkflowNotification and Email (non-blocking).
    """
    if created and not instance.is_staff and not instance.is_superuser:
        msg = f"Welcome to OnWebApp, {instance.username}! We're excited to start working with you."
        WorkflowNotification.objects.create(
            recipient=instance,
            notification_type='STATUS',
            message=msg,
            severity='LOW'
        )
        if instance.email:
            threading.Thread(
                target=_send_welcome_email_async,
                args=(instance.username, instance.email, settings.SITE_URL, settings.DEFAULT_FROM_EMAIL),
                daemon=True,
            ).start()

@receiver(post_save, sender=ProjectPhase)
def automated_procurement_sync(sender, instance, created, **kwargs):
    """
    Trigger: Project phase enters DEVELOPMENT.
    Action: Check ERPNext for required materials and trigger Material Request.
    """
    if instance.status == 'IN_PROGRESS' and instance.phase_type == 'DEVELOPMENT':
        project = instance.project
        client = project.client
        
        # Enhancement 3: Trigger ERP procurement check
        # This will call the Node.js adapter to check stock and potentially create Material Request
        success = erp_utils.sync_project_procurement(client, project.id, instance.id)
        
        if success:
            WorkflowNotification.objects.create(
                recipient=client,
                notification_type='STATUS',
                message=f"Procurement check completed for Project {project.title}. Necessary materials have been requested in ERP.",
                severity='MEDIUM'
            )

@receiver(post_save, sender=Project)
def automated_invoice_generation(sender, instance, created, **kwargs):
    """
    Trigger: New project started.
    Action: Generate draft Invoice, PDF, and Email.
    """
    if created:
        # Determine amount based on project type
        price_map = {
            'WEBSITE': 1500.00,
            'BRANDING': 800.00,
            'AUTOMATION': 5000.00,
            'IOT': 7500.00,
            'SOCIAL': 1000.00,
            'CUSTOM': 2000.00
        }
        amount = price_map.get(instance.project_type, 1000.00)
        
        invoice = Invoice.objects.create(
            project=instance,
            client=instance.client,
            amount=amount,
            status='DRAFT',
            due_date=timezone.now().date() + timezone.timedelta(days=14)
        )
        
        # Generate PDF
        try:
            context = {'invoice': invoice, 'project': instance}
            pdf_content = render_to_pdf('projects/invoice_detail.html', context)
            
            if pdf_content:
                filename = f"Invoice_{invoice.id}_{instance.client.username}.pdf"
                invoice.pdf_file.save(filename, ContentFile(pdf_content), save=True)
                
                # Send Email with Attachment
                if instance.client.email:
                    email = EmailMessage(
                        subject=f"Invoice Generated: {instance.title}",
                        body=f"Dear {instance.client.username},\n\nA new invoice for {instance.title} has been generated.\nAmount: ${amount}\nDue Date: {invoice.due_date}\n\nPlease find the PDF attached.",
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[instance.client.email],
                    )
                    email.attach(filename, pdf_content, 'application/pdf')
                    email.send(fail_silently=True)
                    
                    # Update status to ISSUED since we sent it
                    invoice.status = 'ISSUED'
                    invoice.save()
                    
        except Exception as e:
            print(f"Error generating invoice PDF: {e}")
        
        # Log activity
        ActivityLog.objects.create(
            user=instance.client,
            action=f"Invoice generated for project {instance.title}",
            metadata={'project_id': instance.id, 'amount': float(amount)}
        )

@receiver(post_save, sender=Project)
def notify_admins_new_project(sender, instance, created, **kwargs):
    """
    Trigger: New project started.
    Action: Notify all Admins (Superusers).
    """
    if created:
        admins = User.objects.filter(is_superuser=True)
        for admin in admins:
            WorkflowNotification.objects.create(
                recipient=admin,
                notification_type='STATUS',
                project=instance,
                message=f"New Project Created: {instance.title} by {instance.client.username}",
                severity='MEDIUM'
            )

@receiver(post_save, sender=WorkflowNotification)
def push_notification_to_websocket(sender, instance, created, **kwargs):
    """
    Trigger: New notification created.
    Action: Push to Django Channels (WebSocket).
    """
    if created:
        channel_layer = get_channel_layer()
        group_name = f"user_{instance.recipient.id}"
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "notification_message",
                "message": instance.message,
                "notification_type": instance.notification_type,
                "severity": instance.severity
            }
        )

@receiver(post_save, sender=ProjectPhase)
def monitor_phase_updates(sender, instance, created, **kwargs):
    project = instance.project
    
    total_phases = project.phases.count()
    fields_to_update = []
    if total_phases > 0:
        completed_phases = project.phases.filter(status='COMPLETED').count()
        new_progress = int((completed_phases / total_phases) * 100)
        
        if project.progress_percentage != new_progress:
            project.progress_percentage = new_progress
            fields_to_update.append('progress_percentage')

        phases = project.phases.all()
        new_status = project.current_status
        new_phase = project.current_phase

        if phases.filter(status='DELAYED').exists():
            new_status = 'DELAYED'
        elif completed_phases == total_phases:
            new_status = 'COMPLETED'
            new_phase = 'COMPLETED'
        else:
            next_phase = phases.exclude(status='COMPLETED').order_by('id').first()
            if next_phase:
                new_phase = next_phase.phase_type
                phase_status_map = {
                    'PLANNING': 'PLANNING',
                    'DESIGN': 'DESIGN',
                    'DEVELOPMENT': 'DEVELOPMENT',
                    'TESTING': 'DEVELOPMENT',
                    'LAUNCH': 'DELIVERY',
                }
                mapped_status = phase_status_map.get(next_phase.phase_type)
                if mapped_status:
                    new_status = mapped_status

        if new_status != project.current_status:
            project.current_status = new_status
            fields_to_update.append('current_status')
        if new_phase != project.current_phase:
            project.current_phase = new_phase
            fields_to_update.append('current_phase')

        if fields_to_update:
            project.save(update_fields=fields_to_update)

    # Status Triggers
    if instance.status == 'IN_PROGRESS':
        # Enhancement 3: Trigger ERP Procurement Sync for Automation/IoT projects
        if project.project_type in ['AUTOMATION', 'IOT']:
            erp_utils.sync_project_procurement(
                user=project.client,
                project_id=project.id,
                phase_id=instance.id
            )

    if instance.status == 'COMPLETED':
        msg = f"Phase Completed: {instance.get_phase_type_display()}"
        WorkflowNotification.objects.create(
            project=project,
            recipient=project.client,
            notification_type='STATUS',
            message=msg,
            severity='LOW'
        )
        
        # Auto-mark as delayed if > 3 days (This logic is usually in tasks, but if status changed to DELAYED manually, we send alert)
        
    elif instance.status == 'DELAYED':
        msg = f"Alert: Phase '{instance.get_phase_type_display()}' is now DELAYED."
        WorkflowNotification.objects.create(
            project=project,
            recipient=project.client,
            notification_type='DELAY',
            message=msg,
            severity='HIGH'
        )
        
        # SMS Notification (New)
        if hasattr(project.client, 'profile') and project.client.profile.sms_notifications_enabled and project.client.profile.phone_number:
            # Placeholder for SMS Gateway (Twilio)
            # send_sms(project.client.profile.phone_number, msg)
            print(f"[SMS SIMULATION] Sent to {project.client.profile.phone_number}: {msg}")

        # Notify Admins
        for admin in User.objects.filter(is_superuser=True):
            WorkflowNotification.objects.create(
                project=project,
                recipient=admin,
                notification_type='DELAY',
                message=f"Project '{project.title}' phase '{instance.get_phase_type_display()}' is DELAYED.",
                severity='HIGH'
            )

    # Approval Triggers
    if instance.approval_status == 'AWAITING_CLIENT':
        msg = f"Action Required: Approval needed for {instance.get_phase_type_display()}"
        WorkflowNotification.objects.create(
            project=project,
            recipient=project.client,
            notification_type='APPROVAL',
            message=msg,
            severity='MEDIUM'
        )
        
        # SMS Notification for Approval
        if hasattr(project.client, 'profile') and project.client.profile.sms_notifications_enabled and project.client.profile.phone_number:
             print(f"[SMS SIMULATION] Sent to {project.client.profile.phone_number}: {msg}")


    # WebSocket Real-time Update (Dashboard Stats)
    channel_layer = get_channel_layer()
    data = {
        "type": "phase_update",
        "project_id": project.id,
        "phase_id": instance.id,
        "status": instance.status,
        "status_display": instance.get_status_display(),
        "progress": project.progress_percentage,
    }

    if project.client:
        async_to_sync(channel_layer.group_send)(
            f"user_{project.client.id}",
            {"type": "dashboard_update", "data": data}
        )
    
    async_to_sync(channel_layer.group_send)(
        "admins",
        {"type": "dashboard_update", "data": data}
    )

@receiver([post_save, post_delete], sender=PhaseTask)
def monitor_task_completion(sender, instance, **kwargs):
    try:
        phase = instance.phase
    except ProjectPhase.DoesNotExist:
        # Phase might be deleted, causing cascade delete of tasks
        return

    total_tasks = phase.tasks.count()
    completed_tasks = phase.tasks.filter(status='COMPLETED').count()
    
    if total_tasks > 0:
        new_phase_progress = int((completed_tasks / total_tasks) * 100)
    else:
        new_phase_progress = 0
        
    if phase.progress != new_phase_progress:
        phase.progress = new_phase_progress
        phase.save(update_fields=['progress'])

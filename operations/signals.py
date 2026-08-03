from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import LeaveRequest, Incident, OperationsTask, EmployeeProfile
from projects.models import WorkflowNotification

User = get_user_model()

from services import erp_utils

@receiver(post_save, sender=EmployeeProfile)
def automated_employee_erp_onboarding(sender, instance, created, **kwargs):
    """
    Trigger: New employee profile created.
    Action: Create account, workstation, and payroll in ERPNext.
    """
    if created:
        user = instance.user
        manager = instance.manager
        
        # Enhancement 6: Automated ERP Onboarding
        # This will call the Node.js adapter to setup the employee in ERPNext
        employee_data = {
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'department': instance.department,
            'job_title': instance.job_title,
            'joining_date': instance.joining_date.isoformat()
        }
        
        # Use the manager's ERP site (or the company admin's site)
        # For this logic, we'll try to find an ERP site associated with the manager
        if manager and hasattr(manager, 'erp_site'):
            success = erp_utils.onboard_employee_to_erp(manager, employee_data)
            if success:
                WorkflowNotification.objects.create(
                    recipient=manager,
                    notification_type='STATUS',
                    message=f"Employee {user.get_full_name()} has been successfully onboarded to ERPNext.",
                    severity='LOW'
                )

@receiver(post_save, sender=LeaveRequest)
def notify_leave_update(sender, instance, created, **kwargs):
    if created:
        # Notify Manager
        manager = instance.employee.employee_profile.manager
        if manager:
            WorkflowNotification.objects.create(
                recipient=manager,
                notification_type='APPROVAL',
                message=f"Leave Request: {instance.employee.get_full_name()} requested {instance.leave_type}",
                severity='MEDIUM'
            )
    else:
        # Notify Employee of status change
        if instance.status in ['APPROVED', 'REJECTED']:
            WorkflowNotification.objects.create(
                recipient=instance.employee,
                notification_type='STATUS',
                message=f"Your leave request for {instance.start_date} was {instance.status}",
                severity='LOW'
            )

@receiver(post_save, sender=Incident)
def notify_incident(sender, instance, created, **kwargs):
    if created:
        # Notify Admins
        admins = User.objects.filter(is_superuser=True)
        for admin in admins:
            WorkflowNotification.objects.create(
                recipient=admin,
                notification_type='ALERT',
                message=f"New Incident Reported: {instance.title} ({instance.severity})",
                severity='HIGH' if instance.severity == 'CRITICAL' else 'MEDIUM'
            )

@receiver(post_save, sender=OperationsTask)
def notify_task_assignment(sender, instance, created, **kwargs):
    if created and instance.assignee:
        WorkflowNotification.objects.create(
            recipient=instance.assignee,
            notification_type='STATUS',
            message=f"New Task Assigned: {instance.title}",
            severity='MEDIUM'
        )

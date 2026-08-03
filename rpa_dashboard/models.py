from django.db import models
from django.conf import settings
from django.utils import timezone

class RPAWorkflow(models.Model):
    STATUS_CHOICES = [
        ('READY', 'Ready'),
        ('FAIL', 'Failing'),
        ('SIMULATION', 'Simulation Mode'),
        ('DISABLED', 'Disabled'),
    ]
    
    wf_id = models.CharField(max_length=20, unique=True, help_text="e.g., WF-001")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='READY')
    last_run_at = models.DateTimeField(null=True, blank=True)
    pass_rate = models.FloatField(default=0.0, help_text="Percentage 0-100")
    step_definitions = models.JSONField(default=list, help_text="List of step names, e.g. ['Init', 'Process', 'Cleanup']")
    
    def __str__(self):
        return f"{self.wf_id}: {self.title}"

class WorkflowRun(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('SUCCESS', 'Success'),
        ('FAILURE', 'Failure'),
    ]
    
    workflow = models.ForeignKey(RPAWorkflow, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    duration_ms = models.IntegerField(default=0)
    progress = models.IntegerField(default=0, help_text="Progress percentage 0-100")
    
    class Meta:
        ordering = ['-started_at']
        
    def __str__(self):
        return f"Run {self.id} for {self.workflow.wf_id}"

class WorkflowStep(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PASS', 'Pass'),
        ('FAIL', 'Fail'),
        ('SKIPPED', 'Skipped'),
    ]
    
    run = models.ForeignKey(WorkflowRun, on_delete=models.CASCADE, related_name='steps')
    step_id = models.CharField(max_length=10)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True)
    duration_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['id']
        
    def __str__(self):
        return f"{self.run.id} - {self.step_id} - {self.status}"

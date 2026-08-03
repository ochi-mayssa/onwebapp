from celery import shared_task
from django.utils import timezone
import time
import random
from .models import WorkflowRun, WorkflowStep

@shared_task
def execute_workflow_task(run_id):
    """
    Executes a workflow run in the background.
    Iterates through all pending steps and simulates execution.
    """
    try:
        run = WorkflowRun.objects.get(id=run_id)
    except WorkflowRun.DoesNotExist:
        return f"Run {run_id} not found."

    run.status = 'RUNNING'
    run.save()

    steps = run.steps.all().order_by('id')
    total_steps = steps.count()
    completed_steps = 0
    failure_occurred = False

    for step in steps:
        # Simulate processing time (0.5s - 2.0s)
        delay = random.randint(500, 2000)
        time.sleep(delay / 1000.0)
        
        # Simulate Execution Logic (Placeholder for real RPA logic)
        # In a real scenario, this would dispatch to a robot or run a script.
        
        # 5% chance of failure for demo purposes
        if random.random() < 0.05: 
            step.status = 'FAIL'
            step.error_message = "Simulated execution failure in background task."
            failure_occurred = True
        else:
            step.status = 'PASS'
        
        step.duration_ms = delay
        step.completed_at = timezone.now()
        step.save()
        
        completed_steps += 1
        
        # Update Run Progress
        run.progress = int((completed_steps / total_steps) * 100)
        run.save()

        # If a critical step fails, we might want to stop the workflow
        # For this demo, we continue but mark the run as FAILURE at the end
    
    run.completed_at = timezone.now()
    run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
    
    if failure_occurred:
        run.status = 'FAILURE'
        run.workflow.status = 'FAIL'
    else:
        run.status = 'SUCCESS'
        run.workflow.status = 'READY'
        
    run.workflow.last_run_at = timezone.now()
    run.workflow.save()
    run.save()

    return f"Run {run_id} completed with status {run.status}"

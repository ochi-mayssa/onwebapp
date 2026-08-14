from celery import shared_task
from django.utils import timezone
import time
import random

from .models import WorkflowRun


@shared_task
def execute_workflow_task(run_id):
    """
    Executes a workflow run in the background.
    Iterates through all steps and simulates execution.
    """
    try:
        run = WorkflowRun.objects.get(id=run_id)
    except WorkflowRun.DoesNotExist:
        return f"Run {run_id} not found."

    run.status = "RUNNING"
    run.save()

    steps = run.steps.all().order_by("id")
    total_steps = steps.count()
    completed_steps = 0
    failure_occurred = False

    for step in steps:
        # Simulate processing time (0.5s - 2.0s)
        delay = random.randint(500, 2000)
        time.sleep(delay / 1000.0)

        # Temporary test mode:
        # Mark every step as successful so we can verify
        # Django + Redis + Celery + RPA workflow integration.
        step.status = "PASS"
        step.error_message = ""
        step.duration_ms = delay
        step.completed_at = timezone.now()
        step.save()

        completed_steps += 1

        # Update run progress
        if total_steps > 0:
            run.progress = int((completed_steps / total_steps) * 100)
        else:
            run.progress = 100

        run.save()

    # Finish the run
    run.completed_at = timezone.now()

    if run.started_at:
        run.duration_ms = int(
            (run.completed_at - run.started_at).total_seconds() * 1000
        )
    else:
        run.duration_ms = 0

    if failure_occurred:
        run.status = "FAILURE"
        run.workflow.status = "FAIL"
    else:
        run.status = "SUCCESS"
        run.workflow.status = "READY"

    run.workflow.last_run_at = timezone.now()
    run.workflow.save()
    run.save()

    return f"Run {run_id} completed with status {run.status}"
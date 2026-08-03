from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Avg, Q
from django.template.loader import render_to_string
from .models import RPAWorkflow, WorkflowRun, WorkflowStep
import time
import random
import csv

@login_required
def dashboard(request):
    workflows = RPAWorkflow.objects.all()
    recent_runs = WorkflowRun.objects.select_related('workflow').order_by('-started_at')[:5]
    
    # Simple stats
    total_runs = WorkflowRun.objects.count()
    success_rate = 0.0
    if total_runs > 0:
        success_runs = WorkflowRun.objects.filter(status='SUCCESS').count()
        success_rate = (success_runs / total_runs) * 100
        
    context = {
        'workflows': workflows,
        'recent_runs': recent_runs,
        'total_runs': total_runs,
        'success_rate': round(success_rate, 1)
    }
    return render(request, 'rpa_dashboard/dashboard.html', context)

@login_required
def workflow_detail(request, wf_id):
    workflow = get_object_or_404(RPAWorkflow, wf_id=wf_id)
    # Get history
    history = WorkflowRun.objects.filter(workflow=workflow).order_by('-started_at')[:10]
    
    context = {
        'workflow': workflow,
        'history': history
    }
    return render(request, 'rpa_dashboard/workflow_detail.html', context)

@login_required
@user_passes_test(lambda u: u.is_staff)
def start_workflow_run(request, wf_id):
    """
    Step 1: Create the run and pending steps, then trigger Celery task.
    """
    if request.method == 'POST':
        workflow = get_object_or_404(RPAWorkflow, wf_id=wf_id)
        
        # Create Run
        run = WorkflowRun.objects.create(
            workflow=workflow,
            status='PENDING', # Start as PENDING until task picks it up
            triggered_by=request.user,
            progress=0
        )
        
        # Create Steps
        steps_data = []
        for i, step_name in enumerate(workflow.step_definitions):
            step = WorkflowStep.objects.create(
                run=run,
                step_id=f"{i+1:02d}",
                name=step_name,
                status='PENDING'
            )
            steps_data.append({'id': step.id, 'name': step.name})
            
        # Trigger Celery Task
        from .tasks import execute_workflow_task
        execute_workflow_task.delay(run.id)
            
        return JsonResponse({
            'status': 'success',
            'run_id': run.id,
            'message': 'Workflow execution started in background.',
            'steps': steps_data
        })
    return JsonResponse({'status': 'invalid_method'}, status=405)

@login_required
def run_step_api(request, step_id):
    """
    Legacy/Manual step runner (synchronous).
    Kept for backward compatibility or individual step testing.
    """
    if request.method == 'POST':
        step = get_object_or_404(WorkflowStep, id=step_id)
        # Simulate work
        time.sleep(random.uniform(0.5, 1.5))
        step.status = 'PASS' if random.random() > 0.1 else 'FAIL'
        step.save()
        return JsonResponse({'status': 'success', 'step_status': step.status})
    return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

@login_required
def export_run_csv(request, run_id):
    run = get_object_or_404(WorkflowRun, id=run_id)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="run_{run.id}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Step ID', 'Name', 'Status', 'Duration'])
    for step in run.steps.all():
        writer.writerow([step.step_id, step.name, step.status, 'N/A'])
        
    return response

@login_required
def export_run_pdf(request, run_id):
    # Handle WeasyPrint missing
    try:
        from weasyprint import HTML
    except ImportError:
        return HttpResponse("PDF generation not available (WeasyPrint missing).", status=501)
        
    run = get_object_or_404(WorkflowRun, id=run_id)
    html_string = render_to_string('rpa_dashboard/pdf_report.html', {'run': run})
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="run_{run.id}.pdf"'
    HTML(string=html_string).write_pdf(response)
    return response

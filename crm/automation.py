import datetime
from django.utils import timezone
from django.db.models import Count, Q
from .models import Customer, Interaction, CRMWorkflow, WorkflowStep, ServiceRequest
from projects.models import Invoice, Project

def calculate_health_score(customer):
    """
    Calculates 0-100 health score, updates the customer record,
    and returns (score, issues_list).
    """
    score = 70  # Baseline
    issues = []
    
    # 1. Lifecycle Stage Impact
    if customer.lifecycle_stage in ['ACTIVE_CLIENT', 'RETAINED_CLIENT']:
        score += 10
    elif customer.lifecycle_stage == 'CHURNED':
        score = 0
        issues.append('Client has churned')
    elif customer.lifecycle_stage == 'LEAD':
        score -= 10
        
    # 2. Activity (Last Interaction)
    last_interaction = customer.interactions.order_by('-date').first()
    if last_interaction:
        days_since = (timezone.now() - last_interaction.date).days
        if days_since < 7:
            score += 10
        elif days_since > 30:
            score -= 15
            issues.append(f"Inactive for {days_since} days")
        elif days_since > 60:
            score -= 30
            issues.append("Critically inactive")
    else:
        score -= 10 # No interactions
        
    # 3. Project Health
    if customer.user:
        active_projects = customer.user.projects.exclude(current_status__in=['COMPLETED', 'CANCELLED'])
        delayed_projects = active_projects.filter(current_status='DELAYED').count()
        
        if delayed_projects > 0:
            score -= (20 * delayed_projects)
            issues.append(f"{delayed_projects} delayed project(s)")
        
        if active_projects.count() > 0 and delayed_projects == 0:
            score += 5
            
    # 4. Billing Health
    if customer.user:
        overdue_invoices = Invoice.objects.filter(
            client=customer.user, 
            status='ISSUED', 
            due_date__lt=timezone.now().date()
        ).count()
        
        if overdue_invoices > 0:
            score -= (25 * overdue_invoices)
            issues.append(f"{overdue_invoices} overdue invoice(s)")

    # Cap score
    score = max(0, min(100, score))
    
    # Determine Trend
    previous_score = customer.current_health_score
    if score > previous_score:
        trend = 'UP'
    elif score < previous_score:
        trend = 'DOWN'
    else:
        trend = 'STABLE'

    # Log Score Change History
    if score != previous_score:
        Interaction.objects.create(
            customer=customer,
            interaction_type='SYSTEM',
            summary=f"Health Score Update: {previous_score} -> {score}",
            details=f"Trend: {trend}. Issues: {', '.join(issues)}"
        )

    # Update Customer Record
    customer.current_health_score = score
    customer.health_trend = trend
    customer.last_health_calc = timezone.now()
    customer.save()
    
    # Trigger Health-based Workflows
    trigger_health_workflows(customer, score, previous_score)
    
    return score, issues

def trigger_health_workflows(customer, current_score, previous_score):
    """
    Checks for health-related triggers.
    """
    # 1. Drop Logic
    # Find workflows that trigger on drop below X
    drop_workflows = CRMWorkflow.objects.filter(trigger_type='HEALTH_SCORE_DROP', is_active=True)
    for wf in drop_workflows:
        try:
            threshold = int(wf.trigger_value)
            if previous_score >= threshold and current_score < threshold:
                execute_workflow(wf, customer)
        except ValueError:
            continue

    # 2. Rise Logic
    rise_workflows = CRMWorkflow.objects.filter(trigger_type='HEALTH_SCORE_RISE', is_active=True)
    for wf in rise_workflows:
        try:
            threshold = int(wf.trigger_value)
            if previous_score <= threshold and current_score > threshold:
                execute_workflow(wf, customer)
        except ValueError:
            continue

def execute_workflow(workflow, customer, context=None):
    """
    Executes all steps in a workflow.
    """
    steps = workflow.steps.all().order_by('step_order')
    for step in steps:
        execute_step(step, customer, context)

def execute_step(step, customer, context):
    """
    Performs the specific action.
    """
    action = step.action_type
    details = step.action_details or {}
    
    if action == 'TASK':
        # Create Interaction as a "Task" (assuming Interaction has a type for it or we create a real task)
        # For now, let's log it as an internal note/system notification
        Interaction.objects.create(
            customer=customer,
            interaction_type='SYSTEM',
            summary=f"Task: {details.get('title', 'System Task')}",
            details=f"Workflow '{step.workflow.name}' triggered this task.\n{details.get('description', '')}"
        )
    elif action == 'EMAIL':
        # Placeholder for email sending logic
        Interaction.objects.create(
            customer=customer,
            interaction_type='SYSTEM',
            summary=f"Email Queued: {details.get('subject', 'No Subject')}",
            details=f"Template: {details.get('template', 'default')}"
        )
    elif action == 'CHANGE_STAGE':
        new_stage = details.get('stage')
        if new_stage in dict(Customer.LIFECYCLE_STAGE_CHOICES):
            customer.lifecycle_stage = new_stage
            customer.save()
            Interaction.objects.create(
                customer=customer,
                interaction_type='SYSTEM',
                summary=f"Stage changed to {new_stage}",
            )

def get_business_insights():
    """
    Returns rule-based insights for the dashboard.
    """
    insights = []
    now = timezone.now()

    # Rule 1: High Churn Risk (Low Health + Overdue Invoices)      
    risky_clients = Customer.objects.filter(current_health_score__lt=50).exclude(lifecycle_stage='CHURNED')
    for client in risky_clients:
        if client.user and Invoice.objects.filter(client=client.user, status='ISSUED', due_date__lt=now.date()).exists():  
             insights.append({
                'type': 'danger',
                'icon': 'exclamation-triangle',
                'text': f"{client.name} is at high risk (Score: {client.current_health_score} + Overdue Invoices).",
                'action_url': f"/crm/customers/{client.id}/"       
            })

    # Rule 2: Upsell Opportunities (High Health + Active Projects) 
    happy_clients = Customer.objects.filter(current_health_score__gt=80)
    for client in happy_clients:
        insights.append({
            'type': 'success',
            'icon': 'chart-line',
            'text': f"{client.name} is a prime upsell candidate (Score: {client.current_health_score}).",
            'action_url': f"/crm/customers/{client.id}/"
        })

    # Rule 3: Zombie Leads (Leads > 30 days old with no recent interaction)
    thirty_days_ago = now - datetime.timedelta(days=30)
    zombie_leads = Customer.objects.filter(
        lifecycle_stage='LEAD',
        created_at__lt=thirty_days_ago
    ).exclude(
        interactions__date__gte=thirty_days_ago
    )
    for lead in zombie_leads:
        insights.append({
            'type': 'warning',
            'icon': 'walking',
            'text': f"{lead.name} is a Zombie Lead (No activity for 30+ days).",
            'action_url': f"/crm/customers/{lead.id}/"
        })

    # Rule 4: Stalled Opportunities (Service Requests stuck > 7 days)
    seven_days_ago = now - datetime.timedelta(days=7)
    stalled_requests = ServiceRequest.objects.filter(
        status__in=['NEW', 'REVIEW', 'PROPOSAL'],
        updated_at__lt=seven_days_ago
    ).select_related('customer')
    
    for req in stalled_requests:
        insights.append({
            'type': 'info',
            'icon': 'hourglass-half',
            'text': f"Opportunity '{req.service_type}' for {req.customer.name} is stalled.",
            'action_url': f"/crm/customers/{req.customer.id}/"
        })

    # Rule 5: Recent Health Drop (Detected via Interaction Logs)
    # Check for drops recorded in the last 7 days
    recent_drops = Interaction.objects.filter(
        interaction_type='SYSTEM',
        summary__startswith='Health Score Update',
        date__gte=now - datetime.timedelta(days=7),
        details__contains='Trend: DOWN'
    ).select_related('customer').order_by('-date')
    
    # De-duplicate by customer (show only latest drop)
    seen_customers = set()
    for drop in recent_drops:
        if drop.customer.id not in seen_customers:
            insights.append({
                 'type': 'danger',
                 'icon': 'level-down-alt',
                 'text': f"{drop.customer.name}'s health score recently dropped.",
                 'action_url': f"/crm/customers/{drop.customer.id}/"
             })
            seen_customers.add(drop.customer.id)

    return insights

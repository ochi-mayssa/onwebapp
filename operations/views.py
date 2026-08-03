from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.contrib.auth import get_user_model
from .models import EmployeeProfile, LeaveRequest, OperationsTask, Incident
from users.models import ActivityLog

User = get_user_model()

@login_required
def ops_dashboard(request):
    """
    Unified Dashboard for HR & Operations.
    """
    user = request.user
    
    # My Tasks
    my_tasks = OperationsTask.objects.filter(assignee=user, status__in=['TODO', 'IN_PROGRESS'])
    
    # My Leave
    my_leaves = LeaveRequest.objects.filter(employee=user).order_by('-created_at')[:5]
    
    # Incidents (All for Admin, Assigned for Staff)
    if user.is_staff:
        active_incidents = Incident.objects.exclude(status='CLOSED')
    else:
        active_incidents = Incident.objects.filter(
            Q(reported_by=user) | Q(assigned_to=user)
        ).exclude(status='CLOSED')
        
    # Pending Approvals (For Managers)
    pending_approvals = LeaveRequest.objects.filter(status='PENDING')
    if not user.is_superuser:
        # Filter only if I am the manager of the requester
        pending_approvals = pending_approvals.filter(employee__employee_profile__manager=user)
        
    context = {
        'my_tasks': my_tasks,
        'my_leaves': my_leaves,
        'active_incidents': active_incidents,
        'pending_approvals': pending_approvals,
    }
    return render(request, 'operations/dashboard.html', context)

@login_required
def submit_leave(request):
    if request.method == 'POST':
        leave_type = request.POST.get('leave_type')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason')
        
        # Determine approver (Manager or Admin fallback)
        try:
            manager = request.user.employee_profile.manager
        except EmployeeProfile.DoesNotExist:
            manager = None
            
        LeaveRequest.objects.create(
            employee=request.user,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            approver=manager
        )
        messages.success(request, "Leave request submitted.")
        return redirect('ops_dashboard')
        
    return render(request, 'operations/leave_form.html')

@login_required
def approve_leave(request, leave_id, action):
    leave = get_object_or_404(LeaveRequest, id=leave_id)
    
    # Security check: Must be manager or admin
    is_manager = False
    if hasattr(leave.employee, 'employee_profile'):
        is_manager = leave.employee.employee_profile.manager == request.user
        
    if not (request.user.is_superuser or is_manager):
        messages.error(request, "Permission denied.")
        return redirect('ops_dashboard')
        
    if action == 'approve':
        leave.status = 'APPROVED'
        messages.success(request, "Leave approved.")
    elif action == 'reject':
        leave.status = 'REJECTED'
        messages.warning(request, "Leave rejected.")
        
    leave.save()
    return redirect('ops_dashboard')

@login_required
def report_incident(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        severity = request.POST.get('severity')
        
        Incident.objects.create(
            title=title,
            description=description,
            severity=severity,
            reported_by=request.user
        )
        messages.success(request, "Incident reported.")
        return redirect('ops_dashboard')
        
    return render(request, 'operations/incident_form.html')

@user_passes_test(lambda u: u.is_superuser)
def onboard_employee(request):
    """
    Admin view to create a new User and EmployeeProfile.
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        username = email.split('@')[0]
        password = User.objects.make_random_password()
        
        dept = request.POST.get('department')
        title = request.POST.get('title')
        manager_id = request.POST.get('manager_id')
        
        user = User.objects.create_user(username=username, email=email, password=password)
        
        manager = None
        if manager_id:
            manager = User.objects.get(id=manager_id)
            
        EmployeeProfile.objects.create(
            user=user,
            department=dept,
            job_title=title,
            manager=manager
        )
        
        # Log it
        ActivityLog.objects.create(user=request.user, action=f"Onboarded employee {email}")
        
        messages.success(request, f"Employee created. Password: {password}")
        return redirect('ops_dashboard')
        
    managers = User.objects.filter(is_active=True)
    return render(request, 'operations/onboard_form.html', {'managers': managers})

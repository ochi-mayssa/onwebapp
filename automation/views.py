from __future__ import annotations

import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from crm.models import Customer

from .billing.base import BillingError, WebhookVerificationError
from .billing.service import process_webhook, start_checkout
from .execution.engine import (
    BillingRequired,
    QuotaExceeded,
    enqueue_workflow_execution,
    quota_status,
)
from .execution.errors import ExecutionRejected
from .forms import AutomationRequestForm
from .models import (
    AutomationExecution,
    AutomationRequest,
    AutomationWorkflow,
    BillingEvent,
    Plan,
    Subscription,
)
from .security.redaction import redact_text

logger = logging.getLogger('automation')


def _customer_for_user(user):
    return Customer.objects.filter(user=user).first()


def _customer_qs_for_user(user):
    return Customer.objects.filter(user=user)


def _wants_json(request) -> bool:
    return 'application/json' in (request.headers.get('Accept') or '') or (
        request.content_type or ''
    ).startswith('application/json')


def _json_error(message: str, *, status: int, code: str):
    return JsonResponse({'ok': False, 'error': message, 'code': code}, status=status)


def _execution_response(execution: AutomationExecution, *, created: bool):
    return JsonResponse({
        'ok': True,
        'created': created,
        'execution': {
            'id': execution.pk,
            'status': execution.status,
            'execution_key': execution.execution_key,
            'attempt_count': execution.attempt_count,
            'usage_count': execution.usage_count,
        },
    }, status=202 if created else 200)


@login_required
def automation_overview(request):
    customer = _customer_for_user(request.user)
    plans = [
        {'name': 'Essential', 'price': '$29/mo', 'limit': '3 workflows / 1k actions'},
        {'name': 'Business', 'price': '$79/mo', 'limit': '10 workflows / 10k actions'},
        {'name': 'Pro', 'price': '$199/mo', 'limit': '25 workflows / 30k actions'},
    ]
    subscription = (
        Subscription.objects.filter(customer=customer).order_by('-created_at').first()
        if customer else None
    )
    context = {
        'customer': customer,
        'plans': plans,
        'subscription': subscription,
        'quota': quota_status(subscription) if subscription else None,
        'request_count': AutomationRequest.objects.filter(customer__user=request.user).count(),
        'workflow_count': AutomationWorkflow.objects.filter(customer__user=request.user).count(),
    }
    return render(request, 'automation/overview.html', context)


@login_required
def automation_request_form(request):
    customer = get_object_or_404(_customer_qs_for_user(request.user), user=request.user)
    if request.method == 'POST':
        form = AutomationRequestForm(request.POST)
        if form.is_valid():
            obj = form.save(customer=customer, requested_by=request.user)
            messages.success(request, 'Your automation request has been submitted for review.')
            return redirect('automation:request_detail', pk=obj.pk)
    else:
        form = AutomationRequestForm()
    return render(request, 'automation/request_form.html', {'form': form, 'customer': customer})


@login_required
def request_detail(request, pk):
    obj = get_object_or_404(AutomationRequest, pk=pk, customer__user=request.user)
    return render(request, 'automation/request_detail.html', {'request': obj})


@login_required
def my_automations(request):
    workflows = AutomationWorkflow.objects.filter(customer__user=request.user).select_related('request')
    return render(request, 'automation/my_automations.html', {'workflows': workflows})


@login_required
def automation_detail(request, pk):
    workflow = get_object_or_404(AutomationWorkflow, pk=pk, customer__user=request.user)
    executions = AutomationExecution.objects.filter(workflow=workflow).order_by('-created_at')[:10]
    subscription = (
        Subscription.objects.filter(customer=workflow.customer).order_by('-created_at').first()
    )
    return render(request, 'automation/automation_detail.html', {
        'workflow': workflow,
        'executions': executions,
        'subscription': subscription,
        'quota': quota_status(subscription) if subscription else None,
    })


@login_required
@require_POST
def workflow_trigger(request, pk):
    """Trigger an owned, active workflow.

    The customer scope is applied in the queryset, not after loading the object,
    so another tenant's workflow is indistinguishable from a missing one.
    """
    workflow = get_object_or_404(AutomationWorkflow, pk=pk, customer__user=request.user)

    payload = {}
    idempotency_key = request.headers.get('Idempotency-Key') or request.POST.get('idempotency_key')
    if (request.content_type or '').startswith('application/json'):
        if len(request.body) > int(getattr(settings, 'AUTOMATION_MAX_PAYLOAD_BYTES', 65536)):
            return _json_error('Payload is too large.', status=413, code='invalid_payload')
        try:
            payload = json.loads(request.body or b'{}')
        except (TypeError, ValueError):
            return _json_error('Invalid JSON payload.', status=400, code='invalid_payload')
        if not isinstance(payload, dict):
            return _json_error('Payload must be a JSON object.', status=400, code='invalid_payload')
    elif request.POST.get('payload'):
        try:
            payload = json.loads(request.POST['payload'])
        except (TypeError, ValueError):
            return _json_error('Invalid JSON payload.', status=400, code='invalid_payload')

    try:
        execution, created = enqueue_workflow_execution(
            workflow,
            trigger='manual',
            payload=payload,
            execution_key=idempotency_key,
        )
    except QuotaExceeded as exc:
        if _wants_json(request):
            return _json_error(str(exc), status=429, code=exc.code)
        messages.error(request, str(exc))
        return redirect('automation:automation_detail', pk=workflow.pk)
    except BillingRequired as exc:
        if _wants_json(request):
            return _json_error(str(exc), status=402, code=exc.code)
        messages.error(request, str(exc))
        return redirect('automation:automation_detail', pk=workflow.pk)
    except ExecutionRejected as exc:
        if _wants_json(request):
            return _json_error(str(exc), status=409 if exc.code == 'execution_key_conflict' else 400, code=exc.code)
        messages.error(request, str(exc))
        return redirect('automation:automation_detail', pk=workflow.pk)

    if _wants_json(request):
        return _execution_response(execution, created=created)
    messages.success(request, f'Execution #{execution.pk} queued.' if created else f'Execution #{execution.pk} already exists.')
    return redirect('automation:automation_detail', pk=workflow.pk)


@login_required
@require_GET
def execution_status(request, pk):
    execution = get_object_or_404(
        AutomationExecution.objects.select_related('workflow'),
        pk=pk,
        workflow__customer__user=request.user,
    )
    logs = execution.logs.order_by('created_at')[:200]
    return JsonResponse({
        'id': execution.pk,
        'workflow_id': execution.workflow_id,
        'status': execution.status,
        'attempt_count': execution.attempt_count,
        'failure_code': execution.failure_code,
        'error_message': redact_text(execution.error_message),
        'next_retry_at': execution.next_retry_at.isoformat() if execution.next_retry_at else None,
        'started_at': execution.started_at.isoformat() if execution.started_at else None,
        'completed_at': execution.completed_at.isoformat() if execution.completed_at else None,
        'logs': [
            {
                'level': log.level,
                'message': log.message,
                'payload': log.payload,
                'created_at': log.created_at.isoformat(),
            }
            for log in logs
        ],
    })


@login_required
def billing_dashboard(request):
    customer = get_object_or_404(_customer_qs_for_user(request.user), user=request.user)
    subscription = Subscription.objects.filter(customer=customer).order_by('-created_at').first()
    events = BillingEvent.objects.filter(subscription__customer=customer).order_by('-created_at')[:10]
    plans = Plan.objects.filter(is_active=True).order_by('price')
    return render(request, 'automation/billing_dashboard.html', {
        'customer': customer,
        'subscription': subscription,
        'quota': quota_status(subscription) if subscription else None,
        'events': events,
        'plans': plans,
    })


@login_required
@require_POST
def billing_checkout(request):
    customer = get_object_or_404(_customer_qs_for_user(request.user), user=request.user)
    plan_id = request.POST.get('plan_id')
    if not plan_id and (request.content_type or '').startswith('application/json'):
        try:
            plan_id = (json.loads(request.body or b'{}') or {}).get('plan_id')
        except (TypeError, ValueError):
            return _json_error('Invalid JSON payload.', status=400, code='invalid_payload')
    if not plan_id:
        return _json_error('plan_id is required.', status=400, code='invalid_plan')

    plan = get_object_or_404(Plan, pk=plan_id, is_active=True)
    site_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    try:
        session = start_checkout(
            customer=customer,
            plan=plan,
            success_url=f'{site_url}{reverse("automation:billing_success")}',
            cancel_url=f'{site_url}{reverse("automation:billing_cancel")}',
        )
    except BillingError as exc:
        return _json_error(str(exc), status=400, code=exc.code)

    return JsonResponse({'ok': True, 'checkout_url': session.url, 'session_id': session.session_id})


@login_required
def billing_success(request):
    """Redirect landing page. Deliberately does not activate access."""
    customer = _customer_for_user(request.user)
    subscription = (
        Subscription.objects.filter(customer=customer).order_by('-created_at').first()
        if customer else None
    )
    return render(request, 'automation/billing_success.html', {
        'subscription': subscription,
        'quota': quota_status(subscription) if subscription else None,
    })


@login_required
def billing_cancel(request):
    messages.info(request, 'Checkout was cancelled. No subscription change was made.')
    return redirect('automation:billing_dashboard')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Signature-verified, idempotent Stripe webhook for automation billing."""
    max_body = int(getattr(settings, 'AUTOMATION_WEBHOOK_MAX_BODY_BYTES', 1048576))
    if len(request.body) > max_body:
        return HttpResponse(status=413)
    try:
        result = process_webhook(
            request.body,
            request.META.get('HTTP_STRIPE_SIGNATURE'),
            provider='stripe',
        )
    except WebhookVerificationError:
        logger.warning('Rejected Stripe automation webhook: signature verification failed.')
        return HttpResponse(status=400)
    except BillingError:
        logger.warning('Stripe automation webhook could not be applied; provider should retry.')
        return HttpResponse(status=500)
    except Exception:
        logger.exception('Unexpected Stripe automation webhook failure.')
        return HttpResponse(status=500)
    logger.info('Stripe automation webhook processed: %s', result)
    return HttpResponse(status=200)


@login_required
def admin_queue(request):
    if not request.user.is_staff:
        return redirect('home:home')
    requests = AutomationRequest.objects.select_related('customer', 'requested_by').order_by('-created_at')
    return render(request, 'automation/admin_queue.html', {'requests': requests})


@login_required
def approve_request(request, pk):
    if not request.user.is_staff:
        return redirect('home:home')
    automation_request = get_object_or_404(AutomationRequest, pk=pk)
    automation_request.approve(request.user)
    workflow = automation_request.workflows.filter(customer=automation_request.customer).first()
    if workflow:
        workflow.status = 'approved'
        workflow.approved_by = request.user
        workflow.save(update_fields=['status', 'approved_by', 'updated_at'])
    messages.success(request, 'Automation request approved.')
    return redirect('automation:admin_queue')


@login_required
def record_execution(request, pk):
    workflow = get_object_or_404(AutomationWorkflow, pk=pk, customer__user=request.user)
    execs = AutomationExecution.objects.filter(workflow=workflow).order_by('-created_at')[:5]
    return render(request, 'automation/execution_history.html', {'workflow': workflow, 'executions': execs})

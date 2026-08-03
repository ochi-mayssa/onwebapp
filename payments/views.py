from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string
import stripe
import json

from .models import PaymentPlan
from users.models import UserSubscription, ActivityLog
from services.decorators import DEFAULT_PLAN_LIMITS, DEFAULT_SERVICES
from projects.models import WorkflowNotification, Project

User = get_user_model()

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

def plans(request):
    """Display pricing plans"""
    plans = PaymentPlan.objects.filter(is_active=True)

    usage_summary = {}
    for code, limits in DEFAULT_PLAN_LIMITS.items():
        items = []
        for service_code, max_usage in limits.items():
            label = DEFAULT_SERVICES.get(service_code, service_code)
            items.append(
                f"{max_usage} uses of {label}"
            )
        usage_summary[code] = items

    free_usage_items = []
    free_limits = DEFAULT_PLAN_LIMITS.get('free', {})
    for service_code, max_usage in free_limits.items():
        label = DEFAULT_SERVICES.get(service_code, service_code)
        if max_usage == 1:
            text = f"1 free try of {label}"
        else:
            text = f"{max_usage} free tries of {label}"
        free_usage_items.append(text)

    context = {
        'plans': plans,
        'usage_summary': usage_summary,
        'free_usage_items': free_usage_items,
    }
    return render(request, 'payments/plans.html', context)

def create_checkout(request, plan_id):
    """
    Create a Stripe Checkout Session for a specific plan.
    """
    plan = get_object_or_404(PaymentPlan, id=plan_id)
    
    try:
        # Build success/cancel URLs
        # Note: In production, ensure settings.SITE_URL is set correctly
        domain_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        success_url = domain_url + reverse('users:dashboard') + '?checkout_success=true'
        cancel_url = domain_url + reverse('payments:plans') + '?checkout_cancelled=true'

        project_id = request.session.get('website_project_id')

        # Calculate amount and description based on payment mode
        # For website packages (one-time payment), we charge 50% upfront
        unit_amount = int(plan.price * 100)
        product_name = plan.name
        product_description = plan.description

        if plan.payment_mode == 'payment':
            unit_amount = int((plan.price / 2) * 100)
            product_name = f"{plan.name} (50% Deposit)"
            product_description = f"Initial 50% deposit for {plan.name}. The remaining 50% is due upon project delivery."

        if not settings.STRIPE_SECRET_KEY:
            # Fallback for demo/development mode without Stripe keys
            return JsonResponse({'checkout_url': cancel_url})

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[
                {
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': product_name,
                            'description': product_description,
                        },
                        'unit_amount': unit_amount, # Amount in cents
                    },
                    'quantity': 1,
                },
            ],
            mode=plan.payment_mode, # Use the model field
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=request.user.id if request.user.is_authenticated else None,
            metadata={
                'plan_id': plan.id,
                'user_id': request.user.id if request.user.is_authenticated else None,
                'project_id': project_id
            }
        )
        return JsonResponse({'checkout_url': checkout_session.url})
    
    except Exception as e:
        print(f"Stripe Checkout Error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def pay_invoice(request, invoice_id):
    """
    Generate a Stripe Payment Link for a one-off Project Invoice.
    """
    from projects.models import Invoice
    invoice = get_object_or_404(Invoice, id=invoice_id, client=request.user)
    
    if invoice.status == 'PAID':
         return JsonResponse({'message': 'Invoice already paid'}, status=400)

    try:
        domain_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        success_url = domain_url + reverse('projects:invoice_detail', args=[invoice.id]) + '?payment_success=true'
        cancel_url = domain_url + reverse('projects:invoice_detail', args=[invoice.id])

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': invoice.currency.lower(),
                    'product_data': {
                        'name': f"Invoice #{invoice.id}",
                        'description': f"Payment for Project: {invoice.project.title if invoice.project else 'Service'}",
                    },
                    'unit_amount': int(invoice.amount * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=request.user.id,
            metadata={
                'internal_invoice_id': invoice.id
            }
        )
        return JsonResponse({'checkout_url': checkout_session.url})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_POST
def webhook(request):
    """
    Handle Stripe Webhooks for successful payments.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    event = None

    if not getattr(settings, 'STRIPE_WEBHOOK_SECRET', None) or (settings.DEBUG and not sig_header):
        try:
            event = json.loads(payload)
        except ValueError as e:
            print("Webhook payload parse error (debug mode):", str(e))
            return HttpResponse(status=400)
    else:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            # Invalid payload
            print("Webhook ValueError:", str(e))
            return HttpResponse(status=400)
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            print("Webhook SignatureVerificationError:", str(e))
            return HttpResponse(status=400)

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_checkout(session)
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        handle_invoice_payment_succeeded(invoice)
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        handle_invoice_payment_failed(invoice)

    return HttpResponse(status=200)

def handle_successful_checkout(session):
    """
    Business logic for successful subscription payment.
    """
    client_reference_id = session.get('client_reference_id')
    stripe_sub_id = session.get('subscription')
    metadata = session.get('metadata', {})
    plan_id = metadata.get('plan_id')
    
    if not client_reference_id or not plan_id:
        print("Missing user or plan ID in webhook metadata")
        return

    try:
        user = User.objects.get(id=client_reference_id)
        plan = PaymentPlan.objects.get(id=plan_id)
        
        # 1. Handle Subscription (if applicable)
        if stripe_sub_id:
            # Deactivate old active subscriptions first
            UserSubscription.objects.filter(user=user, is_active=True).update(is_active=False)
            
            subscription = UserSubscription.objects.create(
                user=user,
                plan=plan,
                stripe_subscription_id=stripe_sub_id,
                start_date=timezone.now(),
                end_date=timezone.now() + timezone.timedelta(days=plan.duration_days),
                is_active=True
            )
            
            # Log Activity
            ActivityLog.objects.create(
                user=user,
                action="Subscription Activated",
                metadata={'plan': plan.name, 'price': float(plan.price)}
            )
            
            message_admin = f"New Subscription: {user.username} bought {plan.name}"

        # 2. Handle Project / One-time Payment
        project_id = metadata.get('project_id')
        if project_id:
            try:
                project = Project.objects.get(id=project_id)
                project.current_status = 'IN_PROGRESS'
                project.save()
                
                # Send Confirmation Email to Client
                subject = f"Project Confirmation: {project.title}"
                email_context = {
                    'user': user,
                    'project': project,
                    'plan': plan,
                    'site_url': getattr(settings, 'SITE_URL', 'http://localhost:8000')
                }
                # Fallback to simple text if template not found (or create template later)
                email_body = (
                    f"Hi {user.first_name},\n\n"
                    f"Thank you for purchasing the {plan.name}!\n"
                    f"We have received your payment and your project '{project.title}' is now officially started.\n\n"
                    f"Next Steps:\n"
                    f"1. Our team will review your intake details.\n"
                    f"2. We will reach out within 24 hours to schedule a kickoff call.\n"
                    f"3. You can track progress in your dashboard.\n\n"
                    f"Welcome aboard!\n"
                    f"The Team"
                )
                
                try:
                    send_mail(subject, email_body, settings.DEFAULT_FROM_EMAIL, [user.email])
                except Exception as e:
                    print(f"Failed to send confirmation email: {e}")

                # Log Activity
                ActivityLog.objects.create(
                    user=user,
                    action="Project Payment",
                    metadata={'project_id': project.id, 'plan': plan.name, 'price': float(plan.price)}
                )
                
                message_admin = f"New Project Payment: {user.username} bought {plan.name}"
                
            except Project.DoesNotExist:
                print(f"Project {project_id} not found during checkout handling")
                message_admin = f"Payment received but Project {project_id} not found for {user.username}"

        
        # Notify Admins (Generic)
        if 'message_admin' in locals():
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                WorkflowNotification.objects.create(
                    recipient=admin,
                    notification_type='STATUS',
                    message=message_admin,
                    severity='LOW'
                )
            
        print(f"Successfully processed checkout for {user.username}")

    except User.DoesNotExist:
        print(f"User {client_reference_id} not found")
    except PaymentPlan.DoesNotExist:
        print(f"Plan {plan_id} not found")
    except Exception as e:
        print(f"Error handling checkout: {e}")

def handle_invoice_payment_succeeded(invoice):
    """
    Handle recurring subscription renewals and one-time invoice payments.
    """
    subscription_id = invoice.get('subscription')
    customer_id = invoice.get('customer')
    metadata = invoice.get('metadata', {})
    
    # 1. Handle Subscription Renewal
    if subscription_id:
        try:
            sub = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
            # Extend end_date by plan duration (e.g. 30 days)
            # Simplified: Assuming monthly. Ideally check plan interval.
            sub.end_date = sub.end_date + timezone.timedelta(days=sub.plan.duration_days)
            sub.is_active = True
            sub.save()
            
            ActivityLog.objects.create(
                user=sub.user,
                action="Subscription Renewed",
                metadata={'invoice_id': invoice['id'], 'amount': invoice['amount_paid'] / 100}
            )
            print(f"Subscription renewed for {sub.user.username}")
        except UserSubscription.DoesNotExist:
            print(f"Subscription {subscription_id} not found for renewal")

    # 2. Handle Project Invoice Payment (One-off)
    # Check if metadata links to our Invoice model
    internal_invoice_id = metadata.get('internal_invoice_id')
    if internal_invoice_id:
        from projects.models import Invoice as ProjectInvoice
        try:
            proj_inv = ProjectInvoice.objects.get(id=internal_invoice_id)
            proj_inv.status = 'PAID'
            proj_inv.save()
            
            # Notify Admin
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                WorkflowNotification.objects.create(
                    recipient=admin,
                    notification_type='STATUS',
                    message=f"Invoice #{proj_inv.id} PAID by {proj_inv.client.username}",
                    severity='LOW'
                )
        except ProjectInvoice.DoesNotExist:
            pass

def handle_invoice_payment_failed(invoice):
    """
    Handle failed payments (dunning).
    """
    subscription_id = invoice.get('subscription')
    
    if subscription_id:
        try:
            sub = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
            user = sub.user
            
            # Notify Admin
            admins = User.objects.filter(is_superuser=True)
            for admin in admins:
                WorkflowNotification.objects.create(
                    recipient=admin,
                    notification_type='ALERT',
                    message=f"Payment Failed: Subscription for {user.username}",
                    severity='HIGH'
                )
                
            ActivityLog.objects.create(
                user=user,
                action="Payment Failed",
                metadata={'invoice_id': invoice['id']}
            )
        except UserSubscription.DoesNotExist:
            pass

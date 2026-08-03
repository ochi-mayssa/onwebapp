import subprocess
import json
import os
import logging
from celery import shared_task
from django.contrib.auth.models import User
from .models import UserERP

logger = logging.getLogger(__name__)

from django.core.mail import EmailMessage
from django.conf import settings
from django.template.loader import render_to_string

@shared_task
def send_verification_email(user_id, verify_url):
    """Celery task to send a verification email."""
    try:
        user = User.objects.get(id=user_id)
        subject = 'Verify your email for AutomationIQ'
        html = render_to_string('emails/verify_email.html', {'user': user, 'verify_url': verify_url})
        EmailMessage(subject, html, settings.DEFAULT_FROM_EMAIL, [user.email]).send(fail_silently=False)
        return f"Email sent to {user.email}"
    except Exception as e:
        logger.error(f"Failed to send verification email: {str(e)}")
        return f"Error sending email: {str(e)}"

@shared_task
def provision_erpnext_instance(user_id):
    """Celery task to provision a new ERPNext site for a user."""
    try:
        user = User.objects.get(id=user_id)
        client_id = f"user_{user.id}"
        
        # Check if already exists
        if UserERP.objects.filter(user=user).exists():
            return f"ERP instance already exists for user {user.username}"

        # Path to the automation script
        script_path = os.path.join(os.getcwd(), 'erpnext_integration', 'scripts', 'site_automation.py')
        
        # Call the Python automation script
        # Note: In a real environment, you'd want to handle timeouts and errors more robustly
        result = subprocess.run(
            ['python', script_path, client_id],
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        
        if data.get('status') == 'success':
            # Create the record in DB
            # Note: data['keys'] format is expected to be parsed from '["api_key", "api_secret"]'
            # site_automation.py currently returns a raw string from bench execute
            # In a real scenario, we'd parse it correctly.
            
            # Simple parsing for example purposes:
            keys_raw = data.get('keys', "('', '')")
            # Expected format: ('api_key', 'api_secret')
            import ast
            keys_tuple = ast.literal_eval(keys_raw)
            
            UserERP.objects.create(
                user=user,
                site_name=data['site'],
                api_key=keys_tuple[0],
                api_secret=keys_tuple[1],
                admin_password=data['admin_password'],
                status='active'
            )
            return f"Successfully provisioned ERP for {user.username}"
        else:
            UserERP.objects.create(user=user, site_name=f"error_{client_id}", status='error')
            return f"Error provisioning ERP for {user.username}: {data.get('message')}"

    except Exception as e:
        logger.error(f"Failed to provision ERP instance: {str(e)}")
        return f"Exception during ERP provisioning: {str(e)}"

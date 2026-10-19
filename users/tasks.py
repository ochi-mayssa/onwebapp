import subprocess
import json
import os
import logging
from celery import shared_task
from django.contrib.auth.models import User
from .models import UserERP

logger = logging.getLogger(__name__)

from django.conf import settings
from home.emails import send_notification_email

@shared_task
def send_verification_email(user_id, verify_url):
    """Send the email-verification message (Celery task; also called directly)."""
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error('send_verification_email: user %s does not exist', user_id)
        return 'Unknown user'
    ok = send_notification_email(
        subject='Verify your email for OnWebApp',
        recipients=[user.email],
        template_name='emails/verify_email.html',
        context={'user': user, 'verify_url': verify_url},
        text_body=(
            f'Hello {user.get_short_name() or user.username},\n\n'
            f'Please verify your email address by opening the link below:\n'
            f'{verify_url}\n\n'
            f'If you did not create this account, you can ignore this message.\n\n'
            f'OnWebApp\n'
        ),
        label='verification',
    )
    return 'Email sent' if ok else 'Email failed'

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

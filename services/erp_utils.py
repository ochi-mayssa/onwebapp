import jwt
import datetime
import requests
from django.conf import settings
from users.models import UserERP

def get_erp_adapter_url():
    return getattr(settings, 'ERP_ADAPTER_URL', 'http://localhost:3000')

def get_erp_token(user):
    """Generates a secure JWT for the Node.js adapter."""
    erp_site = getattr(user, 'erp_site', None)
    if not erp_site or not erp_site.api_key:
        # Fallback to UserERP if linked differently
        erp_site = UserERP.objects.filter(user=user).first()
    
    if not erp_site:
        return None

    payload = {
        'site': erp_site.site_name,
        'api_key': erp_site.api_key,
        'api_secret': erp_site.api_secret,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=15),
        'iat': datetime.datetime.utcnow(),
        'iss': 'onwebapp-core'
    }
    secret = getattr(settings, 'ERP_ADAPTER_SECRET', settings.SECRET_KEY)
    return jwt.encode(payload, secret, algorithm='HS256')

def push_iot_data_to_erp(user, machine_id, metrics):
    """
    Enhancement 2: Pushes IoT/Sensor data to ERPNext.
    In a real scenario, this would hit an endpoint in the Node.js adapter 
    that then calls ERPNext's IoT doctype.
    """
    token = get_erp_token(user)
    if not token:
        return False

    adapter_url = get_erp_adapter_url()
    headers = {'Authorization': f'Bearer {token}'}
    
    # We'll simulate the endpoint for now as it's a new enhancement
    # In production, we'd add POST /iot-data to server.js
    payload = {
        'machine_id': machine_id,
        'metrics': metrics,
        'timestamp': datetime.datetime.now().isoformat()
    }
    
    try:
        # Enhancement: Actually hit the Node.js adapter
        response = requests.post(f"{adapter_url}/iot-data", headers=headers, json=payload, timeout=5)
        if response.status_code == 201:
            print(f"[ERP-IoT] Pushed metrics for {machine_id} to ERPNext.")
            return True
        return False
    except Exception as e:
        print(f"[!] ERP IoT Push Error: {e}")
        return False

def sync_project_procurement(user, project_id, phase_id):
    """
    Enhancement 3: Links project workflow to ERP procurement.
    Triggered when a phase requires materials.
    """
    token = get_erp_token(user)
    if not token:
        return False

    adapter_url = get_erp_adapter_url()
    headers = {'Authorization': f'Bearer {token}'}
    
    # Actually hit the Node.js adapter for procurement check
    try:
        payload = {'project_id': project_id, 'phase_id': phase_id}
        response = requests.post(f"{adapter_url}/procurement-check", headers=headers, json=payload, timeout=5)
        return response.status_code == 201
    except Exception as e:
        print(f"[!] ERP Procurement Error: {e}")
        return False

def onboard_employee_to_erp(user, employee_data):
    """
    Enhancement 6: Creates employee in ERPNext.
    """
    token = get_erp_token(user)
    if not token:
        return False

    adapter_url = get_erp_adapter_url()
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        response = requests.post(f"{adapter_url}/onboard-employee", headers=headers, json=employee_data, timeout=5)
        return response.status_code == 201
    except Exception as e:
        print(f"[!] ERP Onboarding Error: {e}")
        return False

def get_enterprise_analytics(user):
    """
    Enhancement 5: Aggregates data for Advanced Analytics.
    """
    token = get_erp_token(user)
    if not token:
        return None

    adapter_url = get_erp_adapter_url()
    headers = {'Authorization': f'Bearer {token}'}
    
    # Hit the Node.js adapter for aggregated analytics
    try:
        response = requests.get(f"{adapter_url}/analytics", headers=headers, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[!] ERP Analytics Error: {e}")
        
    return {
        'revenue_forecast': 0,
        'stock_value': 0,
        'customer_retention': 'N/A',
        'efficiency_score': 'N/A'
    }

from celery import shared_task
from django.utils import timezone
from .models import Customer
from .automation import calculate_health_score
import logging

logger = logging.getLogger(__name__)

@shared_task
def update_all_customer_health_scores():
    """
    Periodic task to recalculate health scores for all customers.
    This offloads heavy processing from the dashboard view.
    """
    customers = Customer.objects.all()
    count = 0
    for customer in customers:
        try:
            calculate_health_score(customer)
            count += 1
        except Exception as e:
            logger.error(f"Error calculating health score for customer {customer.id}: {str(e)}")
    
    return f"Successfully updated health scores for {count} customers."

@shared_task
def update_single_customer_health(customer_id):
    """
    Task to update a single customer's health score.
    Useful for triggering updates after specific events (e.g., new interaction).
    """
    try:
        customer = Customer.objects.get(id=customer_id)
        calculate_health_score(customer)
        return f"Updated health score for customer {customer.name}"
    except Customer.DoesNotExist:
        return f"Customer {customer_id} not found."

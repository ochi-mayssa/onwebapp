"""
Management command to sync ERP data for all clients
Usage: python manage.py sync_erp_data [--client-id=<id>] [--force]
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from crm.models import Customer
from crm.erp_sync import sync_customer_orders, ERPNextClient
from crm.models import ClientTracking, OrderSnapshot, InvoiceSnapshot, StockAllocation
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync ERP data for all clients or specific client'

    def add_arguments(self, parser):
        parser.add_argument(
            '--client-id',
            type=int,
            help='Sync data for specific client ID only',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sync even if recently synced',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        client_id = options.get('client_id')
        force = options.get('force', False)
        verbose = options.get('verbose', False)

        if client_id:
            # Sync specific client
            try:
                customer = Customer.objects.get(id=client_id)
                self.sync_single_client(customer, force, verbose)
            except Customer.DoesNotExist:
                raise CommandError(f'Client with ID {client_id} does not exist')
        else:
            # Sync all clients
            customers = Customer.objects.filter(user__isnull=False)
            self.stdout.write(f'Syncing {customers.count()} clients...')
            
            success_count = 0
            for customer in customers:
                try:
                    if self.sync_single_client(customer, force, verbose):
                        success_count += 1
                except Exception as e:
                    self.stderr.write(f'Failed to sync {customer.name}: {str(e)}')
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully synced {success_count}/{customers.count()} clients')
            )

    def sync_single_client(self, customer, force=False, verbose=False):
        """Sync data for a single client"""
        if verbose:
            self.stdout.write(f'Syncing client: {customer.name} (ID: {customer.id})')
        
        # Check if we have tracking setup
        try:
            tracking = ClientTracking.objects.get(user=customer.user)
        except ClientTracking.DoesNotExist:
            if verbose:
                self.stdout.write(f'No tracking setup for {customer.name}, skipping')
            return False
        
        # Sync orders
        if sync_customer_orders(customer):
            if verbose:
                self.stdout.write(f'✓ Synced orders for {customer.name}')
        else:
            self.stderr.write(f'✗ Failed to sync orders for {customer.name}')
            return False
        
        # Sync invoices
        try:
            erp_client = ERPNextClient(customer.user)
            invoices = erp_client.get_invoices()
            
            # Clear old snapshots
            InvoiceSnapshot.objects.filter(client=tracking).delete()
            
            # Create new snapshots
            for invoice in invoices:
                InvoiceSnapshot.objects.create(
                    client=tracking,
                    erp_invoice_id=invoice.get('name'),
                    amount=invoice.get('grand_total', 0),
                    status=invoice.get('status', 'ISSUED'),
                    issue_date=invoice.get('posting_date'),
                    due_date=invoice.get('due_date'),
                    payment_date=invoice.get('payment_date')
                )
            
            if verbose:
                self.stdout.write(f'✓ Synced {len(invoices)} invoices for {customer.name}')
        except Exception as e:
            self.stderr.write(f'✗ Failed to sync invoices for {customer.name}: {str(e)}')
            return False
        
        # Sync stock allocations
        try:
            stock = erp_client.get_stock_allocation()
            
            # Clear old allocations
            StockAllocation.objects.filter(client=tracking).delete()
            
            # Create new allocations
            for item in stock:
                StockAllocation.objects.create(
                    client=tracking,
                    item_code=item.get('item_code'),
                    item_name=item.get('item_name'),
                    allocated_qty=item.get('reserved_qty', 0),
                    available_qty=item.get('actual_qty', 0),
                    unit_rate=item.get('standard_rate', 0)
                )
            
            if verbose:
                self.stdout.write(f'✓ Synced {len(stock)} stock items for {customer.name}')
        except Exception as e:
            self.stderr.write(f'✗ Failed to sync stock for {customer.name}: {str(e)}')
            return False
        
        # Update last sync time
        tracking.save()
        
        if verbose:
            self.stdout.write(f'✓ Completed sync for {customer.name}')
        
        return True
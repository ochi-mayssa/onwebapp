# ERP/CRM Real-Time Tracking Setup Guide

## 🎯 Problem Solved
Clients were seeing dashboards with only metadata and counts, but no real operational data from their ERP and CRM systems. This solution provides a unified, real-time tracking portal where clients can monitor their orders, invoices, projects, and resources.

## 🚀 Quick Start

### 1. Database Setup
```bash
# Apply migrations
python manage.py migrate

# Create demo customer
python setup_erp_tracking.py --demo

# Generate mock data for testing
python generate_mock_data.py
```

### 2. Start the Server
```bash
python manage.py runserver
```

### 3. Test the Dashboard
- Visit: http://localhost:8000/crm/my-dashboard/
- Login as: `demo_customer` / `demo123`
- Explore the real-time tracking features

## 📋 Features Implemented

### ✅ Client Dashboard (`/crm/my-dashboard/`)
- **Real-time Order Tracking**: Progress bars, status updates, target dates
- **Invoice Management**: Payment status, due dates, overdue alerts
- **Resource Allocation**: Stock levels, utilization percentages
- **Project Overview**: Active/completed projects, delayed alerts
- **Account Health**: Overall score, payment trends
- **Activity Feed**: Recent interactions and updates

### ✅ Dedicated Views
- **Orders**: `/crm/my-orders/` - Detailed order tracking
- **Invoices**: `/crm/my-invoices/` - Payment management with tabs
- **Projects**: `/crm/my-projects/` - Project status overview
- **Account**: `/crm/my-account/` - Profile and subscription info

### ✅ Data Synchronization
- **Management Command**: `python manage.py sync_erp_data`
- **API Endpoints**: Real-time data refresh
- **Caching**: 5-minute cache for performance
- **Error Handling**: Graceful fallbacks when ERP server unavailable

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Client Portal │    │  ERP Sync Module │    │  ERPNext Server │
│                 │    │                  │    │                 │
│ • Dashboard     │◄──►│ • API Client     │◄──►│ • Orders        │
│ • Orders        │    │ • Data Caching   │    │ • Invoices      │
│ • Invoices      │    │ • JWT Auth       │    │ • Stock         │
│ • Projects      │    │ • Error Handling │    │ • Analytics     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📁 Files Created/Modified

### New Files:
- `crm/erp_sync.py` - ERP API client and data synchronization
- `crm/client_views.py` - Client-facing dashboard views
- `crm/templates/crm/client_tracking_portal.html` - Main dashboard
- `crm/templates/crm/client_invoices.html` - Invoice management
- `crm/management/commands/sync_erp_data.py` - Sync management command
- `setup_erp_tracking.py` - Client setup script
- `generate_mock_data.py` - Mock data generator

### Modified Files:
- `crm/models.py` - Added tracking models
- `crm/urls.py` - Added client routes
- `websity_project/settings.py` - Added ERP settings

## 🔧 Configuration

### Environment Variables:
```bash
# ERP Integration
ERP_GATEWAY_URL=http://localhost:3000
ERP_DOMAIN=onwebapp.com

# Email (optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-password
```

### Client Setup:
Each client needs ERP credentials configured in `ClientTracking` model:
- `erp_customer_id`: Customer ID in ERPNext
- `erp_site_name`: Subdomain (e.g., `client.onwebapp.com`)
- `api_key` & `api_secret`: ERPNext API credentials

## 🔄 Data Synchronization

### Manual Sync:
```bash
# Sync all clients
python manage.py sync_erp_data

# Sync specific client
python manage.py sync_erp_data --client-id=1

# Verbose output
python manage.py sync_erp_data --verbose
```

### Automated Sync:
Set up a cron job to run every 15 minutes:
```bash
*/15 * * * * /path/to/project/manage.py sync_erp_data
```

## 🧪 Testing

### With Mock Data:
```bash
# Generate sample data
python generate_mock_data.py

# Test dashboard at http://localhost:8000/crm/my-dashboard/
# Login: demo_customer / demo123
```

### With Real ERPNext:
1. Start ERPNext server
2. Configure client credentials in admin
3. Run sync command
4. Test dashboard

## 📊 Dashboard Features

### KPI Cards:
- Account Health Score
- Active Orders Count
- Amount Due
- Active Projects

### Order Tracking:
- Progress bars with percentages
- Status badges (Pending/In Progress/Completed)
- Target completion dates
- Overdue indicators

### Invoice Management:
- Paid/Due/Overdue tabs
- Payment action buttons
- Due date warnings
- Amount summaries

### Resource Monitoring:
- Allocated vs Available quantities
- Utilization percentages
- Unit pricing
- Real-time updates

## 🔒 Security

- JWT token authentication for API calls
- User-specific data filtering
- Encrypted API credentials
- Role-based access control
- CSRF protection on forms

## 🚀 Production Deployment

1. **Configure ERP Gateway**:
   ```bash
   cd erpnext_integration/backend
   npm install
   node server.js
   ```

2. **Set Environment Variables**:
   ```bash
   export ERP_GATEWAY_URL=https://your-erp-gateway.com
   export ERP_DOMAIN=yourdomain.com
   ```

3. **Configure Clients**:
   - Set up ERP credentials in Django admin
   - Test API connectivity
   - Run initial sync

4. **Set Up Monitoring**:
   - Configure automated sync jobs
   - Set up error notifications
   - Monitor API rate limits

## 📈 Next Steps

1. **WebSocket Integration**: Real-time push notifications
2. **Email Notifications**: Automated alerts for status changes
3. **Advanced Analytics**: Spending trends, completion rates
4. **Mobile App**: React Native client portal
5. **Multi-tenant ERP**: Support for different ERP systems

## 🐛 Troubleshooting

### Common Issues:

**"No module named 'weasyprint'"**:
- Install WeasyPrint: `pip install weasyprint`
- Or ignore (only affects PDF generation)

**"Connection refused" on sync**:
- ERP gateway server not running
- Check ERP_GATEWAY_URL setting
- Use mock data for testing

**Empty dashboard**:
- Run `python generate_mock_data.py`
- Check client has tracking setup
- Verify user permissions

**Permission denied**:
- User must be a customer (have Customer profile)
- Check user authentication status

## 📞 Support

For issues or questions:
1. Check Django logs: `tail -f logs/django.log`
2. Test API endpoints manually
3. Verify ERP server connectivity
4. Check database for data consistency

---

**🎉 Success!** Clients now have a comprehensive, real-time tracking portal instead of empty dashboards. The solution bridges CRM and ERP systems to provide actionable operational insights.</content>
<parameter name="filePath">c:\Users\DELL Inspiron_2023\Pictures\Desktop\OnWebApp v6\OnWebApp v6\ERP_TRACKING_README.md
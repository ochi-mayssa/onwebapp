# ERP/CRM Real-Time Tracking Solution

## Problem Analysis

Users/Clients cannot track their ERP and CRM data effectively because:

1. **Disconnected Systems**: ERP (ERPNext) and CRM (OnWebApp) are separate platforms with minimal real-time synchronization
2. **Dashboard Shows Only Metadata**: CRM dashboard displays counts and metrics but lacks actual operational data
3. **No Real-Time Data Binding**: The dashboards pull static data without live connections to ERPNext operations
4. **Missing Integration Layer**: No unified view where clients can see their projects, invoices, orders, and customer data side-by-side
5. **Lack of Real-Time Updates**: No WebSocket/polling mechanism to push live updates to dashboards

## Current Architecture Issues

### CRM Dashboard (`crm/views.py`)
- Shows health scores, client counts, and KPIs
- No direct link to actual ERP data (orders, invoices, stock)
- Relies on invoice queries but doesn't sync with ERPNext

### ERPNext Integration (`erpnext_integration/backend/server.js`)
- Backend server exists but APIs are not connected to frontend
- No WebSocket for real-time updates
- Dashboard folder is empty (no UI)

### Platform Dashboard (`platform_app/templates/platform/dashboard.html`)
- Generic "Quick Links" only
- No operational data display

## Solution: Client Tracking Portal

### 1. Create a Real-Time Client Dashboard

**File**: `crm/views.py` - Add new view

```python
@login_required
def client_tracking_portal(request):
    """
    Unified client tracking portal with real-time ERP/CRM data.
    Accessible by clients to track their own operations.
    """
    user = request.user
    
    # Get customer profile
    try:
        customer = Customer.objects.get(user=user)
    except:
        return redirect('home:index')  # Not a customer
    
    # Fetch from ERPNext API via backend server
    erp_data = fetch_erp_customer_data(user)
    
    # Compile unified data
    context = {
        'customer': customer,
        'erp_orders': erp_data.get('orders', []),
        'erp_invoices': erp_data.get('invoices', []),
        'erp_stock': erp_data.get('stock_items', []),
        'projects': Project.objects.filter(client=user),
        'interactions': Interaction.objects.filter(customer=customer).order_by('-date')[:10],
        'health_score': customer.current_health_score,
        'next_renewal': customer.subscription_end_date,
    }
    return render(request, 'crm/client_tracking_portal.html', context)
```

### 2. Create Frontend UI for Client Portal

**File**: `crm/templates/crm/client_tracking_portal.html`

Shows:
- **Active Orders**: Real-time status from ERPNext
- **Invoices & Payment Status**: Due/Overdue/Paid
- **Stock/Services**: What they're using/allocated
- **Project Timeline**: Current projects and deliverables
- **Health Score**: CRM health indicators
- **Next Steps**: Upcoming renewals, milestones

### 3. API Endpoint for Real-Time Updates

**Enhance**: `erpnext_integration/backend/server.js`

```javascript
/**
 * Endpoint: GET /customer-dashboard/:user_id
 * Returns unified view of customer's ERP + CRM data
 */
app.get('/customer-dashboard/:user_id', verifyToken, async (req, res) => {
    const { site, api_key, api_secret } = req.erp_credentials;
    const adapter = new ERPNextAdapter(site, api_key, api_secret);
    
    try {
        const [orders, invoices, stock, customer_info] = await Promise.all([
            adapter.get('Work Order', { 
                filters: '[["customer", "=", "' + user_id + '"]]',
                fields: '["name", "status", "qty", "produced_qty", "planned_start_date"]'
            }),
            adapter.get('Sales Invoice', {
                filters: '[["customer", "=", "' + user_id + '"]]',
                fields: '["name", "status", "grand_total", "due_date"]',
                limit_page_length: 20
            }),
            adapter.get('Item', {
                fields: '["item_code", "item_name", "actual_qty", "reserved_qty", "standard_rate"]',
                limit_page_length: 10
            }),
            adapter.get('Customer', {
                filters: '[["name", "=", "' + user_id + '"]]'
            })
        ]);
        
        res.json({
            customer: customer_info[0],
            orders: orders,
            invoices: invoices,
            stock_allocation: stock,
            last_updated: new Date().toISOString()
        });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});
```

### 4. WebSocket for Real-Time Updates

**New File**: `erpnext_integration/backend/websocket.js`

```javascript
const WebSocket = require('ws');
const jwt = require('jsonwebtoken');

const wss = new WebSocket.Server({ port: 3001 });

// Track connected clients by user_id
const clients = {};

wss.on('connection', (ws, req) => {
    const token = new URL('http://localhost' + req.url).searchParams.get('token');
    
    jwt.verify(token, SHARED_SECRET, (err, decoded) => {
        if (err) {
            ws.close();
            return;
        }
        
        const userId = decoded.user_id;
        if (!clients[userId]) clients[userId] = [];
        clients[userId].push(ws);
        
        ws.on('close', () => {
            clients[userId] = clients[userId].filter(client => client !== ws);
        });
    });
});

// Server sends updates to all connected clients of a user
function notifyClient(userId, event, data) {
    if (clients[userId]) {
        clients[userId].forEach(ws => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ event, data, timestamp: new Date() }));
            }
        });
    }
}

module.exports = { notifyClient };
```

### 5. Create Client-Facing Dashboard View

**File**: `crm/templates/crm/client_tracking_portal.html`

Key sections:
```html
<!-- Active Orders Table -->
<div class="card">
    <h5>Your Active Orders</h5>
    <table class="table">
        <tr>
            <th>Order ID</th>
            <th>Product</th>
            <th>Quantity</th>
            <th>Status</th>
            <th>Target Date</th>
            <th>Progress</th>
        </tr>
        {% for order in erp_orders %}
        <tr>
            <td><a href="#">{{ order.name }}</a></td>
            <td>{{ order.product }}</td>
            <td>{{ order.qty }}</td>
            <td><span class="badge">{{ order.status }}</span></td>
            <td>{{ order.planned_date }}</td>
            <td>
                <div class="progress">
                    <div class="progress-bar" style="width: {{ order.progress }}%"></div>
                </div>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>

<!-- Invoice Status -->
<div class="card">
    <h5>Your Invoices</h5>
    <table class="table">
        <tr>
            <th>Invoice #</th>
            <th>Amount</th>
            <th>Due Date</th>
            <th>Status</th>
            <th>Action</th>
        </tr>
        {% for invoice in erp_invoices %}
        <tr>
            <td>{{ invoice.name }}</td>
            <td>${{ invoice.grand_total }}</td>
            <td>{{ invoice.due_date }}</td>
            <td>
                <span class="badge 
                    {% if invoice.status == 'Paid' %}bg-success
                    {% elif invoice.status == 'Overdue' %}bg-danger
                    {% else %}bg-warning{% endif %}">
                    {{ invoice.status }}
                </span>
            </td>
            <td>
                {% if invoice.status != 'Paid' %}
                    <a href="{% url 'payments:pay_invoice' invoice.id %}" class="btn btn-sm btn-primary">Pay Now</a>
                {% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
</div>

<!-- Resource Allocation -->
<div class="card">
    <h5>Your Allocated Resources</h5>
    <ul>
        {% for item in erp_stock %}
        <li>
            <strong>{{ item.item_name }}</strong>
            <br>Available: {{ item.actual_qty }} units | Reserved: {{ item.reserved_qty }} units
            <br>Unit Price: ${{ item.standard_rate }}
        </li>
        {% endfor %}
    </ul>
</div>

<!-- Activity Feed -->
<div class="card">
    <h5>Recent Updates</h5>
    <div class="timeline" id="realtime-feed">
        <!-- WebSocket will populate this -->
    </div>
</div>
```

### 6. JavaScript for Real-Time Updates

**File**: `crm/static/client_tracking.js`

```javascript
// Connect to WebSocket
const token = document.querySelector('[data-token]').dataset.token;
const ws = new WebSocket(`wss://your-domain.com/ws?token=${token}`);

ws.onmessage = (event) => {
    const { event: eventType, data } = JSON.parse(event.data);
    
    if (eventType === 'order_updated') {
        updateOrderTable(data);
    } else if (eventType === 'invoice_issued') {
        addInvoiceRow(data);
    } else if (eventType === 'payment_received') {
        markInvoicePaid(data);
    } else if (eventType === 'activity') {
        addTimelineEvent(data);
    }
};

function updateOrderTable(order) {
    const row = document.querySelector(`tr[data-order-id="${order.id}"]`);
    if (row) {
        row.querySelector('.status').textContent = order.status;
        row.querySelector('.progress-bar').style.width = order.progress + '%';
    }
}
```

### 7. URL Routing

**Update**: `crm/urls.py`

```python
urlpatterns = [
    path('dashboard/', crm_dashboard, name='dashboard'),
    path('customers/', customer_list, name='customer_list'),
    path('customers/<int:customer_id>/', customer_detail, name='customer_detail'),
    # NEW: Client-facing portal
    path('my-dashboard/', client_tracking_portal, name='client_tracking_portal'),
    path('my-orders/', client_orders_list, name='client_orders'),
    path('my-invoices/', client_invoices_list, name='client_invoices'),
]
```

## Implementation Steps

### Phase 1: Backend Integration (Week 1-2)
1. ✅ Setup ERPNext API authentication
2. ✅ Create aggregation function `fetch_erp_customer_data(user)`
3. ✅ Expose REST API endpoint `/customer-dashboard`
4. ✅ Add WebSocket server for real-time updates

### Phase 2: Frontend Portal (Week 2-3)
1. Create client tracking portal template
2. Build real-time JavaScript updates
3. Style responsive dashboard
4. Test with real ERPNext data

### Phase 3: Notifications (Week 3)
1. Email alerts on order status changes
2. In-app notifications
3. SMS for critical updates (optional)

### Phase 4: Analytics (Week 4)
1. Client spending trends
2. Order fulfillment rates
3. Payment history analysis

## Database Schema Enhancement

Add to `crm/models.py`:

```python
class ClientTracking(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    erp_customer_id = models.CharField(max_length=255)  # Link to ERPNext
    last_sync = models.DateTimeField(auto_now=True)
    api_key = models.CharField(max_length=255, encrypted=True)
    notification_email = models.EmailField()
    realtime_enabled = models.BooleanField(default=True)
    
class OrderSnapshot(models.Model):
    """Cache of ERPNext orders for quick access"""
    client = models.ForeignKey(ClientTracking, on_delete=models.CASCADE)
    erp_order_id = models.CharField(max_length=255)
    product = models.CharField(max_length=255)
    qty = models.IntegerField()
    status = models.CharField(max_length=50)
    progress_percent = models.IntegerField()
    target_date = models.DateField()
    last_updated = models.DateTimeField(auto_now=True)
```

## Access Control

```python
@login_required
def client_tracking_portal(request):
    # Only allow clients to see their own data
    user = request.user
    
    # Check if user is a customer
    if not Customer.objects.filter(user=user).exists():
        messages.error(request, "You must be a customer to access this portal.")
        return redirect('home:index')
    
    # Proceed with portal view
```

## Security Considerations

1. **API Key Management**: Store ERPNext API keys encrypted in database
2. **Rate Limiting**: Limit API calls to prevent abuse
3. **CORS**: Allow only your domain
4. **JWT Tokens**: Use short-lived tokens for WebSocket
5. **Data Filtering**: Ensure users only see their own data

## Expected Outcomes

✅ Clients can see real-time order status  
✅ Invoice tracking with payment status  
✅ Resource allocation visibility  
✅ Activity feed with live updates  
✅ No page refresh needed (WebSocket)  
✅ Better customer satisfaction  
✅ Reduced support tickets  

---

**Next Step**: Start with Phase 1 backend integration

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import json
import uuid
import jwt
import datetime
import requests
from django.conf import settings
from .models import ChatSession, ChatMessage
from users.models import UserERP

def query_erp_adapter(user, endpoint, params=None):
    """Utility to query the Node.js ERP adapter for a specific user."""
    erp_site = getattr(user, 'erp_site', None)
    if not erp_site:
        return None

    # Generate JWT
    payload = {
        'site': erp_site.site_name,
        'api_key': erp_site.api_key,
        'api_secret': erp_site.api_secret,
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')

    # Query Node.js adapter
    adapter_url = getattr(settings, 'ERP_ADAPTER_URL', 'http://localhost:3000')
    headers = {'Authorization': f'Bearer {token}'}
    
    try:
        response = requests.get(f"{adapter_url}/{endpoint}", headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"[!] Chatbot ERP Query Error: {e}")
    
    return None

def chatbot_view(request):
    return render(request, 'chatbot/chatbot.html')

@csrf_exempt
def get_suggestions(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message_text = data.get('message', '').strip()
            session_id = data.get('session_id')
            
            # Create or get session
            if not session_id:
                session_id = str(uuid.uuid4())
                session, created = ChatSession.objects.get_or_create(session_id=session_id)
                if request.user.is_authenticated:
                    session.user = request.user
                    session.save()
            else:
                session, created = ChatSession.objects.get_or_create(session_id=session_id)
                # Update user if authenticated and not set
                if request.user.is_authenticated and not session.user:
                    session.user = request.user
                    session.save()
            
            # Save User Message
            ChatMessage.objects.create(
                session=session,
                sender='USER',
                content=user_message_text
            )
            
            # Logic for response (Enhanced with Context)
            reply, suggestions = generate_response(user_message_text, session)
            
            # Save Bot Message
            ChatMessage.objects.create(
                session=session,
                sender='BOT',
                content=reply
            )
            
            return JsonResponse({
                'reply': reply,
                'suggestions': suggestions,
                'session_id': session.session_id
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def generate_response(message, session):
    """
    Enhanced logic with conversation history context.
    """
    message = message.lower()
    
    # Retrieve last 3 messages for context (simple memory)
    history = session.messages.order_by('-timestamp')[:3]
    
    # 1. Greetings
    if any(word in message for word in ['hi', 'hello', 'hey', 'start', 'begin']):
        return "Hello! I'm the OnWebApp assistant. How can I help you today?", [
            {'title': 'Pricing', 'content': 'See our subscription plans'},
            {'title': 'Services', 'content': 'Explore what we offer'},
            {'title': 'Support', 'content': 'Get technical help'}
        ]

    # 2. Pricing & Plans
    if any(word in message for word in ['price', 'cost', 'pricing', 'how much', 'plan', 'subscription']):
        return "We offer flexible plans starting at $49/mo. You can choose from Basic, Pro, or Enterprise tiers depending on your needs.", [
            {'title': 'Compare Plans', 'content': 'View detailed plan comparison'},
            {'title': 'Enterprise', 'content': 'Contact sales for custom solutions'}
        ]

    # 3. Services / Features
    if any(word in message for word in ['service', 'offer', 'provide', 'feature', 'what do you do']):
        return "We specialize in Industrial Automation Monitoring, Competitor Tracking, and Custom Web Development.", [
            {'title': 'Automation', 'content': 'Learn about our AI monitoring'},
            {'title': 'Competitor Tracking', 'content': 'Market analysis tools'}
        ]

    # 4. Automation Specifics
    if any(word in message for word in ['automation', 'industrial', 'monitoring', 'sensor']):
        return "Our Industrial Automation platform provides real-time monitoring, predictive maintenance alerts, and efficiency reporting for your machinery.", [
            {'title': 'Demo', 'content': 'Request a demo of our automation tools'},
            {'title': 'Case Studies', 'content': 'See how others use our platform'}
        ]

    # 5. ERP / CRM Real-time Queries (New Enhancement)
    if any(word in message for word in ['order', 'production', 'progress']):
        # Extract Order ID (simple regex for #456 or similar)
        import re
        match = re.search(r'#?(\d+)', message)
        if match and session.user:
            order_id = match.group(1)
            # We'll assume the user might mean MWO-00001 format or similar if just a number is provided
            # For this demo, we'll try to find it
            res = query_erp_adapter(session.user, f'orders/{order_id}')
            if res:
                status = res.get('status', 'Unknown')
                produced = res.get('produced_qty', 0)
                total = res.get('qty', 0)
                return f"Order #{order_id} is currently **{status}**. We have produced {produced} out of {total} units.", [
                    {'title': 'Full Report', 'content': 'Show production details'},
                    {'title': 'Contact Manager', 'content': 'Notify floor supervisor'}
                ]
        elif session.user:
            return "Please provide an Order ID (e.g., 'progress for #123') so I can check its status for you.", []

    if any(word in message for word in ['revenue', 'crm', 'leads', 'opportunity']):
        if session.user:
            res = query_erp_adapter(session.user, 'crm-summary')
            if res:
                total = res.get('total_revenue', 0)
                count = res.get('count', 0)
                return f"You currently have {count} open opportunities with a total potential revenue of **${total:,.2f} USD**.", [
                    {'title': 'Sales Pipeline', 'content': 'View all opportunities'},
                    {'title': 'Forecast', 'content': 'Show revenue forecast'}
                ]

    if any(word in message for word in ['stock', 'inventory', 'item', 'available']):
        if session.user:
            stock = query_erp_adapter(session.user, 'stock')
            if stock:
                # Check for low stock mentions
                if 'low' in message or 'below' in message or 'alert' in message:
                    low_stock = [i for i in stock if i.get('actual_qty', 100) < 50] # Simulated threshold
                    if low_stock:
                        items = ", ".join([i['item_name'] for i in low_stock])
                        return f"Alert: The following items are below threshold: {items}. Should I create a material request?", [
                            {'title': 'Yes, Request', 'content': 'Create Material Request'},
                            {'title': 'Not Now', 'content': 'Dismiss alert'}
                        ]
                
                items_list = ", ".join([f"{item['item_name']} ({item['standard_rate']})" for item in stock[:5]])
                return f"I found the following items in your stock: {items_list}. Would you like more details?", [
                    {'title': 'Full Stock', 'content': 'Show full inventory'},
                    {'title': 'Procurement', 'content': 'Request materials'}
                ]
        return "I can check your stock, but I need you to be logged in and have an active ERP site. Would you like to set one up?", [
            {'title': 'ERP Setup', 'content': 'Configure ERPNext integration'}
        ]

    if any(word in message for word in ['customer', 'client', 'contact']):
        if session.user:
            customers = query_erp_adapter(session.user, 'customers')
            if customers:
                customer_names = ", ".join([c['customer_name'] for c in customers[:5]])
                return f"Here are some of your customers: {customer_names}. How can I help you with them?", [
                    {'title': 'Sales Order', 'content': 'Create new order'},
                    {'title': 'CRM', 'content': 'Manage clients'}
                ]
        return "You can manage your customers through the CRM. Would you like to see a demo?", [
            {'title': 'CRM Demo', 'content': 'Show CRM features'}
        ]

    # 6. Support / Contact
    if any(word in message for word in ['support', 'help', 'contact', 'email', 'phone', 'issue', 'problem']):
        return "Our support team is available 24/7. You can reach us at support@onwebapp.com or call +1-555-0123.", [
            {'title': 'Submit Ticket', 'content': 'Open a new support ticket'},
            {'title': 'Knowledge Base', 'content': 'Browse help articles'}
        ]
        
    # 6. Contextual Follow-up (Simple Logic)
    # Check if the previous message was about pricing
    last_bot_msg = history.filter(sender='BOT').first()
    if last_bot_msg:
        if 'plan' in last_bot_msg.content.lower() and ('expensive' in message or 'cheap' in message):
            return "We understand budget is important. Our Basic plan is very affordable for startups. Would you like to see a demo?", [
                 {'title': 'Basic Plan', 'content': 'Show me the Basic plan'},
                 {'title': 'Contact Sales', 'content': 'Talk to a human'}
            ]

    # Default / Fallback
    return "I'm not sure I understand. Could you rephrase that? You can ask me about pricing, services, or support.", [
        {'title': 'Pricing', 'content': 'Check our rates'},
        {'title': 'Services', 'content': 'What we do'},
        {'title': 'Contact', 'content': 'Get in touch'}
    ]

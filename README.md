# Websity — AI-Powered Digital Solutions Platform

A unified SaaS ecosystem for business analytics, industrial automation, and enterprise integration. Websity bridges the gap between digital marketing, project workflows, and enterprise resource planning (ERP) using a modern, multi-tier architecture.

---

## 🚀 Core Modules & Features

### 🏢 Enterprise Integration (White-label ERP & CRM)
- **ERPNext Adapter**: Seamlessly sync customers, stock, and invoices with a dedicated [Node.js adapter](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/erpnext_integration/backend/server.js) that talks to ERPNext REST API.
- **AI Assistant Integration**: Chatbot linked to the ERP adapter for real-time queries about production progress, stock levels, and CRM revenue ([chatbot/views.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/chatbot/views.py)).
- **White-labeled Portals**: Branded client portals for manufacturing order tracking and invoice management ([erpnext_dashboard.html](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/templates/services/erpnext_dashboard.html)).
- **Secure JWT Auth**: Django issues signed tokens for the adapter, ensuring secure cross-service communication ([erp_utils.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/services/erp_utils.py)).

### 📈 Analytics & Intelligence
- **Advanced Forecasting**: Aggregated CRM sales pipelines and ERP production capacity for demand forecasting and financial KPIs ([server.js](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/erpnext_integration/backend/server.js)).
- **Social Proof & Sentiment**: Real-time social event ingestion with sentiment analysis (TextBlob) and live broadcasts via WebSockets ([social_proof](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/social_proof)).
- **Industrial IoT**: Predictive maintenance that automatically creates ERP maintenance requests based on machine health ([processors.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/services/processors.py)).

### 🛠️ Project & Operations
- **Workflow-Driven Procurement**: Automated ERP material requests triggered when project phases enter development ([projects/signals.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/projects/signals.py)).
- **Automated Onboarding**: Instant provisioning of ERPNext user accounts and payroll setup for new factory employees ([operations/signals.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/operations/signals.py)).
- **Workflow & Kanban**: Advanced project tracking with phases, deliverables, and team management dashboards ([projects](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/projects)).

### 💳 Commerce & Subscriptions
- **Stripe Integration**: Productized payment plans with Stripe Checkout and automated webhook handlers ([payments](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/payments)).
- **Plan Limits**: Usage tracking and feature gating based on user subscription levels ([users/models.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/users/models.py)).

---

## 🛠️ Tech Stack

- **Backend**: Python 3.8+ / Django 5.0.6 ([requirements.txt](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/requirements.txt))
- **Real-time**: Django Channels & Daphne (WebSockets)
- **Async Processing**: Celery & Redis for parallel registration, email verification, and ERP provisioning ([users/tasks.py](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/users/tasks.py)).
- **ERP Adapter**: Node.js & Express ([server.js](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/erpnext_integration/backend/server.js))
- **Frontend**: Bootstrap 5, Chart.js, and custom site-wide Dark Mode
- **i18n**: Support for **English**, **French**, and **Arabic** ([settings.py:L162-L170](file:///c:/Users/DELL%20Inspiron_2023/Pictures/Desktop/OnWebApp%20v6/OnWebApp%20v6/websity_project/settings.py#L162-L170))

---

## ⚡ Quick Start

### 1. Prerequisites
- Python 3.8+
- Node.js (for ERP Adapter)
- Redis (required for Celery/Channels)

### 2. Setup & Installation
```bash
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
cd erpnext_integration/backend && npm install && cd ../..

# Initialize database
python manage.py migrate
python manage.py createsuperuser
```

### 3. Running the Platform
For full functionality, start both the Django server and the ERP adapter:
```bash
# Terminal 1: Django
python manage.py runserver

# Terminal 2: ERP Adapter
node erpnext_integration/backend/server.js
```

---

## 📁 Project Structure (Key Apps)

| App | Description |
| :--- | :--- |
| `websity_project/` | Main project config, settings, and routing. |
| `services/` | Primary business tools (SEO, Industrial, ERP logic). |
| `projects/` | Kanban workflows and project deliverables. |
| `social_proof/` | Sentiment analysis and live event broadcasting. |
| `payments/` | Stripe checkout and subscription management. |
| `users/` | User profiles, plan limits, and parallel registration tasks. |
| `erpnext_integration/` | Node.js adapter and site automation scripts. |
| `templates/` | Global layouts and service-specific dashboards. |

---

## ⚙️ Environment Variables

The platform uses environment variables for secure configuration. Copy `.env.example` to `.env`:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DEBUG` | `True` | Set to `False` in production. |
| `SECRET_KEY` | - | Django secret key (crucial for JWTs). |
| `STRIPE_SECRET_KEY` | - | Stripe API secret for payments. |
| `CELERY_BROKER_URL` | `redis://...` | Redis URL for async tasks. |
| `ERP_DOMAIN` | `onwebapp.com` | Base domain for ERPNext sites. |
| `MOCK_ERP` | `true` | Enable mock mode for dashboard demos without live ERP. |

---

## 🛡️ Deployment Checklist

- [ ] **Production Hardening**: Ensure `DEBUG=False` and `SECURE_SSL_REDIRECT` are configured.
- [ ] **Collect Static**: Run `python manage.py collectstatic`.
- [ ] **ERP Adapter**: Deploy the Node.js server with PM2 or a similar process manager.
- [ ] **Worker Nodes**: Start Celery workers: `python -m celery -A websity_project worker --loglevel=info`.

### 🔧 Troubleshooting & Tips
- **Mock ERP Mode**: The platform defaults to `MOCK_ERP=true` in the Node adapter to show populated dashboards and charts for demo purposes even without a live ERP connection.
- **Windows GLib Warnings**: You may see `GLib-GIO-WARNING` in the terminal when starting the server. These are related to the `GTK+` runtime used by WeasyPrint and are harmless.
- **Async Tasks**: Ensure Redis is running for background email verification and ERP provisioning. If Redis is unavailable, these tasks will be logged but skipped.

---

**Last Updated**: April 8, 2026  
**License**: Proprietary — Websity.io  
**Support**: [support@websity.io](mailto:support@websity.io)

# OnWebApp Architecture: Business Automation SaaS

## Product Scope
OnWebApp is a **Business Automation & System Integration SaaS Platform**, similar to Zapier, Make, or UiPath. 
It enables businesses to automate workflows, integrate APIs, crawl web data, and manage projects.

**What OnWebApp is NOT:**
- NOT a Cybersecurity SOC platform.
- NOT a RAG (Retrieval Augmented Generation) system.
- NOT a Multi-Agent AI system.
- Does NOT use LangChain, LangGraph, or Vector Databases.

## Technical Stack
- **Backend Framework**: Django 5.0 (Python).
- **Asynchronous Task Queue**: Celery 5.3 + Redis 4.0.
- **Database**: PostgreSQL (Production) / SQLite (Development).
- **Frontend**: Django Templates + Vanilla JS / HTMX (Server-side rendering).
- **Payment Processing**: Stripe API.
- **Web Server**: Gunicorn / Daphne (ASGI for WebSockets).

## Core Modules Architecture

### 1. Workflow & Automation Engine (`services`)
The heart of the platform. Handles the execution of automated tasks.
- **Crawlers**: `services/crawlers/` (BaseCrawler, Instagram, TikTok, etc.) - For data extraction.
- **Processors**: `services/processors.py` - Logic to transform extracted data.
- **Tasks**: `services/tasks.py` - Celery tasks for background execution (long-running jobs).

### 2. Project Management (`projects`)
Manages the user's workspace and organization.
- **Models**: Projects, Phases, Tasks, Deliverables.
- **Features**: Kanban boards, Team management, Invoicing.
- **Real-time**: WebSocket integration for dashboard updates (using Django Channels).

### 3. Platform Dashboard (`platform_app` & `platform_legacy`)
The main user interface for interacting with automations.
- **Views**: Dashboard analytics, Link management, Service configuration.
- **Analytics**: Visualizations of service usage and performance.

### 4. SaaS Infrastructure
- **Users**: Custom user model, Profile management, Onboarding flow.
- **Payments**: Subscription plans (Basic/Pro/Enterprise), Checkout flows, Webhook handling.
- **SEO Analyzer**: Standalone tool for website audits (`seo_analyzer`).

## Deployment Strategy
- **Type**: Monolithic SaaS Application.
- **Containerization**: Docker & Docker Compose.
- **Environment**: Cloud-agnostic (AWS, DigitalOcean, Hetzner).
- **Static Files**: WhiteNoise or Nginx serving static assets.

## Development Guidelines
1.  **Focus on Reliability**: Automations must be robust and handle API failures gracefully.
2.  **Scalability**: Use Celery for any external API call or long-running process.
3.  **Security**: Standard SaaS security (CSRF, Auth, Permissions). No sensitive SOC data handling.
4.  **No AI Hype**: Focus on deterministic, programmable automation logic.

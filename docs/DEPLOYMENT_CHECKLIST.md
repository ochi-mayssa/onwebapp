# Deployment Checklist — Websity Platform

Use this checklist to prepare the Websity platform for production deployment.

## Pre-Deployment (1-2 days before)

### Code & Dependencies
- [ ] Run `python manage.py check` — verify no Django warnings
- [ ] Run `python manage.py test services` — validate all processors and email logic
- [ ] Review `requirements.txt` — ensure all dependencies are pinned and up-to-date
- [ ] Test locally with production settings: `DEBUG=False SECRET_KEY=...`
- [ ] Check static files: `python manage.py collectstatic --noinput --dry-run`

### Security
- [ ] Generate a new SECRET_KEY (use Django's utility)
- [ ] Audit all `.env` or environment variable files — no secrets should be in code
- [ ] Review `ALLOWED_HOSTS` list — add your production domain
- [ ] Enable HTTPS certificate (Let's Encrypt recommended)
- [ ] Set `SECURE_SSL_REDIRECT=True` (via settings or env)

### Database
- [ ] If migrating from SQLite: prepare PostgreSQL instance
- [ ] Test migration: `python manage.py migrate`
- [ ] Create superuser: `python manage.py createsuperuser`
- [ ] Backup production database before first deploy (if upgrading)

### External Services
- [ ] Stripe: Create webhook endpoint (point to `/payments/webhook/`)
- [ ] Stripe: Copy Live keys (Publishable & Secret), test in sandbox first
- [ ] Email: Set up SMTP credentials (SendGrid, AWS SES, Gmail App Password, etc.)
- [ ] Redis: Provision Redis instance (local, Docker, managed service)
- [ ] Sentry (optional): Create account and copy DSN

---

## Deployment Day

### Before Deploying Code

```powershell
# 1. Set all environment variables on deployment server
$env:DEBUG="False"
$env:SECRET_KEY="django-xxxxxxxxxxxxxxx"  # Use new secret!
$env:ALLOWED_HOSTS="yourdomain.com,www.yourdomain.com"

# 2. Email
$env:EMAIL_HOST="smtp.sendgrid.net"
$env:EMAIL_HOST_USER="apikey"
$env:EMAIL_HOST_PASSWORD="SG.xxxxx"
$env:EMAIL_PORT="587"
$env:EMAIL_USE_TLS="True"
$env:DEFAULT_FROM_EMAIL="admin@yourdomain.com"

# 3. Stripe (use LIVE keys in production)
$env:STRIPE_PUBLISHABLE_KEY="pk_live_xxxxx"
$env:STRIPE_SECRET_KEY="sk_live_xxxxx"
$env:STRIPE_WEBHOOK_SECRET="whsec_xxxxx"

# 4. Celery & Redis
$env:USE_CELERY="True"
$env:CELERY_BROKER_URL="redis://your-redis-host:6379/0"

# 5. Sentry (optional)
$env:SENTRY_DSN="https://xxxxx@xxxxx.ingest.sentry.io/yyyy"
$env:ENVIRONMENT="production"
```

### Deploy Code

```bash
# 1. Pull latest code
git pull origin main  # or your branch

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run migrations
python manage.py migrate

# 4. Collect static files (for production server)
python manage.py collectstatic --noinput

# 5. Run final checks
python manage.py check

# 6. Start services
# Terminal 1: Django + Gunicorn
gunicorn websity_project.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 60

# Terminal 2: Celery worker
celery -A websity_project worker --loglevel=info --concurrency=2

# Terminal 3: Celery beat (optional: for scheduled tasks)
celery -A websity_project beat --loglevel=info
```

### Configure Reverse Proxy (Nginx Example)

```nginx
upstream django {
    server localhost:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Static files
    location /static/ {
        alias /path/to/OnWebApp/staticfiles/;
        expires 1y;
    }
    
    # Media files
    location /media/ {
        alias /path/to/OnWebApp/media/;
        expires 7d;
    }
    
    # Django application
    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Post-Deployment

### Health Checks (Run immediately after deploy)

```bash
# 1. Check homepage loads
curl https://yourdomain.com/

# 2. Check admin panel
curl https://yourdomain.com/admin/

# 3. Check service pages
curl https://yourdomain.com/services/iot-integration/

# 4. Check payment plans page
curl https://yourdomain.com/payments/plans/

# 5. Monitor Celery worker
# Should show something like:
# "[tasks]
# . services.tasks.send_result_email
# - services.tasks.debug_task"
```

### Monitor Logs

```bash
# Django/Gunicorn logs
tail -f /var/log/gunicorn.log

# Celery worker logs
tail -f /var/log/celery.log

# Nginx logs
tail -f /var/log/nginx/access.log
tail -f /var/log/nginx/error.log

# Sentry (if enabled)
# Visit https://sentry.io and check for errors
```

### Test Key Features

1. **Service Pages**
   - Submit a form on `/services/industrial-automation/`
   - Verify result displays with chart
   - If email provided, check console/SMTP for email

2. **Payments**
   - Visit `/payments/plans/`
   - Click "Checkout with Card"
   - (With Stripe keys) should redirect to Stripe
   - (Without Stripe keys) should show demo success

3. **Email**
   - Submit a service form with email address
   - Check that email arrives in inbox (or mailbox provider)
   - Verify admin copy was sent to `DEFAULT_FROM_EMAIL`

4. **Celery Tasks**
   - Check Celery worker terminal logs
   - Should see `send_result_email` task execution if emails are being sent

---

## Monitoring & Maintenance

### Daily

- [ ] Check Sentry dashboard for errors
- [ ] Monitor server CPU/memory usage
- [ ] Verify Redis is running (`redis-cli ping`)
- [ ] Check Celery worker is running (`ps aux | grep celery`)

### Weekly

- [ ] Review Django security updates
- [ ] Check Stripe webhook logs (in Stripe dashboard)
- [ ] Verify backups are running
- [ ] Monitor email delivery (check bounces, spam reports)

### Monthly

- [ ] Update dependencies: `pip list --outdated`
- [ ] Review and rotate API keys (Stripe, email provider, etc.)
- [ ] Analyze Sentry trends and resolve high-priority errors
- [ ] Capacity planning: CPU, memory, Redis, database

---

## Rollback Plan

If something breaks after deployment:

```bash
# 1. Stop services
killall gunicorn celery nginx

# 2. Rollback code
git checkout main
git pull origin main  # Get stable commit

# 3. Revert database (if migrations failed)
python manage.py migrate <previous_migration_name>

# 4. Restart services
# Re-run deployment commands above
```

---

## Troubleshooting

### Stripe Checkout Not Working

- [ ] Verify `STRIPE_PUBLISHABLE_KEY` is correct (starts with `pk_`)
- [ ] Verify `STRIPE_SECRET_KEY` is correct (starts with `sk_`)
- [ ] Check browser console for JavaScript errors
- [ ] Test in Stripe test mode first (use test keys)

### Emails Not Sending

- [ ] Check `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` are correct
- [ ] Test SMTP connection: `python -m smtplib` with credentials
- [ ] Verify email provider allows SMTP access (some providers require app passwords)
- [ ] Check firewall/network allows port 587 or 465

### Celery Tasks Not Running

- [ ] Verify Redis is running: `redis-cli ping` should return `PONG`
- [ ] Check `USE_CELERY=True` is set
- [ ] Check Celery worker is running: `ps aux | grep celery`
- [ ] Check logs: `celery -A websity_project worker --loglevel=debug`

### High CPU/Memory Usage

- [ ] Reduce Gunicorn workers: `--workers 2` (instead of 4)
- [ ] Increase Celery concurrency: `--concurrency 4` (if low)
- [ ] Profile with: `python -m cProfile manage.py runserver`
- [ ] Check for slow database queries in Django logs

---

## Success Criteria

After deployment, verify:

- [ ] Homepage loads in < 2 seconds
- [ ] Service forms accept input and display results
- [ ] Charts render correctly
- [ ] Emails send and arrive in inbox (with or without attachments)
- [ ] Stripe checkout redirects correctly
- [ ] No errors in Sentry dashboard
- [ ] Celery worker is processing tasks (check logs)
- [ ] All dependencies show in `pip list`
- [ ] Database migrations are applied (`python manage.py showmigrations --list`)

---

## Support & Documentation

- **README.md** — Full setup guide, environment variables, running locally
- **IMPLEMENTATION_SUMMARY.md** — Technical details on all enhancements
- **settings.py** — Comments on every environment variable
- **services/tests.py** — Unit test examples (run with `python manage.py test services`)

---

**Last Updated**: November 19, 2025  
**Version**: 1.0

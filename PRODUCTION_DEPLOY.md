# Production Deployment Checklist for TalkEasy

## Pre-Deployment Checklist

### 1. Environment Variables ✅

**CRITICAL:** Verify your production `.env` file has the correct values:

```bash
# Django Settings
DJANGO_SETTINGS_MODULE=talkeasy.settings.production  # NOT development!
DEBUG=False
DJANGO_SECRET_KEY=<your-secure-secret-key>
ALLOWED_HOSTS=core.koottuapp.in,www.koottuapp.in

# Database - MUST be MySQL in production
DB_ENGINE=django.db.backends.mysql
DB_NAME=<your-production-db-name>
DB_USER=<your-db-user>
DB_PASSWORD=<your-db-password>
DB_HOST=<your-rds-endpoint>
DB_PORT=3306

# Razorpay - MUST use LIVE keys in production
RAZORPAY_KEY_ID=rzp_live_XXXXXXXXXXXX  # NOT rzp_test_!
RAZORPAY_KEY_SECRET=<your-live-secret>
RAZORPAY_WEBHOOK_SECRET=<your-webhook-secret>

# RabbitMQ
RABBITMQ_URL=amqp://user:password@your-rabbitmq-host:5672/

# CORS
CORS_ALLOWED_ORIGINS=https://your-frontend.com,https://www.your-frontend.com

# Agora
AGORA_APP_ID=<your-app-id>
AGORA_APP_CERTIFICATE=<your-certificate>
AGORA_TOKEN_TTL_SECONDS=3600

# External Services
TWO_FACTOR_API_KEY=<your-api-key>

# JWT Configuration
JWT_ACCESS_TOKEN_LIFETIME_DAYS=1
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# Coins Configuration
COINS_PER_SECOND=3
```

### 2. Razorpay Configuration ⚠️

**Test vs Live Keys:**
- **Test keys** (`rzp_test_...`): For development/testing only
- **Live keys** (`rzp_live_...`): For production ONLY

**To get LIVE keys:**
1. Log into Razorpay Dashboard
2. Go to Settings → API Keys
3. Generate Live API Keys (requires business verification)
4. Update `.env` with live keys

### 3. Database Setup

```bash
# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser if needed
python manage.py createsuperuser
```

### 4. File Permissions

```bash
# Ensure log directory exists and is writable
mkdir -p /path/to/talkeasy/logs
chmod 755 /path/to/talkeasy/logs

# Ensure media directory is writable
chmod 755 /path/to/talkeasy/media
```

### 5. Web Server Configuration

**Gunicorn Setup:**
```bash
# Install gunicorn
pip install gunicorn

# Test gunicorn
gunicorn talkeasy.wsgi:application --bind 0.0.0.0:8000

# Use systemd service (recommended)
# Create /etc/systemd/system/talkeasy.service
```

**Example systemd service:**
```ini
[Unit]
Description=TalkEasy Gunicorn Service
After=network.target

[Service]
User=your-user
Group=www-data
WorkingDirectory=/path/to/talkeasy
Environment="PATH=/path/to/talkeasy/venv/bin"
ExecStart=/path/to/talkeasy/venv/bin/gunicorn \
          --workers 4 \
          --bind 0.0.0.0:8000 \
          --timeout 120 \
          --access-logfile /path/to/talkeasy/logs/gunicorn-access.log \
          --error-logfile /path/to/talkeasy/logs/gunicorn-error.log \
          talkeasy.wsgi:application

[Install]
WantedBy=multi-user.target
```

**Nginx Configuration:**
- Use the `nginx_config_example.conf` file as a template
- Update SSL certificate paths
- Update project paths
- Test config: `sudo nginx -t`
- Reload: `sudo systemctl reload nginx`

### 6. SSL/HTTPS Setup

Install SSL certificate (Let's Encrypt recommended):
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d core.koottuapp.in
```

### 7. RabbitMQ Setup (for WebSockets)

```bash
# Install RabbitMQ
sudo apt install rabbitmq-server

# Start service
sudo systemctl start rabbitmq-server
sudo systemctl enable rabbitmq-server

# Create user
sudo rabbitmqctl add_user myuser mypassword
sudo rabbitmqctl set_permissions -p / myuser ".*" ".*" ".*"
```

## Deployment Steps

### Step 1: Pull Latest Code
```bash
cd /path/to/talkeasy
git pull origin main
```

### Step 2: Activate Virtual Environment
```bash
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run Migrations
```bash
python manage.py migrate
```

### Step 5: Collect Static Files
```bash
python manage.py collectstatic --noinput
```

### Step 6: Restart Services
```bash
# Restart Gunicorn
sudo systemctl restart talkeasy

# Restart Nginx
sudo systemctl reload nginx

# If using Daphne for WebSockets
sudo systemctl restart daphne
```

## Post-Deployment Verification

### 1. Check Service Status
```bash
# Check Gunicorn
sudo systemctl status talkeasy

# Check Nginx
sudo systemctl status nginx

# Check logs
tail -f /path/to/talkeasy/logs/error.log
tail -f /path/to/talkeasy/logs/payments.log
tail -f /var/log/nginx/talkeasy_error.log
```

### 2. Test Endpoints

```bash
# Health check
curl https://core.koottuapp.in/health/

# Test user registration (should work)
curl -X POST https://core.koottuapp.in/users/register-or-login/ \
  -H "Content-Type: application/json" \
  -d '{"mobile_number": 1234567890}'

# Test payment plans (public endpoint)
curl https://core.koottuapp.in/payments/recharge-plan-list/
```

### 3. Monitor Logs

Watch for errors in real-time:
```bash
tail -f logs/error.log logs/payments.log
```

## Common Production Issues

### Issue 1: 500 Errors on Payment Endpoints

**Cause**: Using test Razorpay keys in production
**Solution**: Update `.env` with LIVE Razorpay keys

### Issue 2: Static Files Not Loading

**Cause**: collectstatic not run or wrong STATIC_ROOT
**Solution**: 
```bash
python manage.py collectstatic
sudo systemctl reload nginx
```

### Issue 3: Database Connection Errors

**Cause**: Wrong database credentials or RDS not accessible
**Solution**: 
- Verify DB credentials in `.env`
- Check RDS security group allows connection from EC2
- Test connection: `mysql -h <RDS_HOST> -u <USER> -p`

### Issue 4: CORS Errors

**Cause**: Frontend domain not in CORS_ALLOWED_ORIGINS
**Solution**: Add frontend domain to `.env`

### Issue 5: WebSocket Connection Fails

**Cause**: RabbitMQ not running or wrong configuration
**Solution**: 
- Check: `sudo systemctl status rabbitmq-server`
- Verify RABBITMQ_URL in `.env`

## Security Checklist

- [ ] DEBUG=False in production
- [ ] SECRET_KEY is unique and secure (not the default)
- [ ] Using LIVE Razorpay keys (not test)
- [ ] SSL certificate installed and auto-renews
- [ ] Firewall configured (only ports 80, 443, 22 open)
- [ ] Database has strong password
- [ ] RabbitMQ has authentication
- [ ] ALLOWED_HOSTS properly configured
- [ ] CORS_ALLOWED_ORIGINS limited to your domains only

## Quick Troubleshooting Commands

```bash
# View recent errors
tail -100 logs/error.log

# View payment-specific logs
tail -100 logs/payments.log

# Check if gunicorn is running
ps aux | grep gunicorn

# Check nginx configuration
sudo nginx -t

# Restart everything
sudo systemctl restart talkeasy nginx

# Monitor live requests
tail -f /var/log/nginx/talkeasy_access.log
```

## Support Contacts

- **Razorpay Support**: https://razorpay.com/support/
- **Django Documentation**: https://docs.djangoproject.com/
- **Project Issues**: Check project logs first

---

**Last Updated**: 2026-02-10

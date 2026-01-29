# Migration Creation & Testing Guide

This document contains the exact commands to run after environment setup.

## Prerequisites

1. Virtual environment must be activated
2. All dependencies must be installed
3. Database connection must be configured

## Step-by-Step Commands

### 1. Activate Virtual Environment

```bash
cd /home/muhammed-fazal/Desktop/talk_easy
source venv/bin/activate
```

Verify activation:
```bash
which python  # Should show path inside venv
```

### 2. Create Migrations

```bash
# Create migrations for payments app
python manage.py makemigrations payments

# Expected output:
# Migrations for 'payments':
#   payments/migrations/0XXX_auto_YYYYMMDD_HHMM.py
#     - Alter field razorpay_order_id on userrecharge
#     - Add field webhook_received_at to userrecharge
#     - Add field retry_count to userrecharge
#     - Add field notes to userrecharge
#     - Create model WebhookEvent
#     - Add index ...
```

### 3. Review Migration

```bash
python manage.py sqlmigrate payments 0XXX  # Replace XXX with migration number
```

### 4. Apply Migrations

```bash
python manage.py migrate
```

### 5. Verify Migration

```bash
python manage.py showmigrations payments

# All should show [X] (applied)
```

### 6. Test Database Connection

```bash
python manage.py dbshell

# In MySQL shell:
SHOW TABLES;
DESCRIBE payments_userrecharge;
DESCRIBE payments_webhookevent;
\q  # Exit
```

### 7. Create Test Superuser (if needed)

```bash
python manage.py createsuperuser
```

### 8. Run Development Server

```bash
python manage.py runserver
```

## Troubleshooting

### Issue: "No module named 'django'"

**Solution:** Activate virtual environment first
```bash
source venv/bin/activate
```

### Issue: "Module not found: decouple"

**Solution:** Install python-decouple
```bash
pip install python-decouple
```

### Issue: Database connection error

**Solution:** Check .env file has correct database credentials
```bash
cat .env | grep DB_
```

### Issue: Migration conflicts

**Solution:** Show current migration state
```bash
python manage.py showmigrations
python manage.py migrate --fake-initial  # Only if needed
```

## After Migration Success

1. Access admin panel: http://localhost:8000/admin/
2. Check WebhookEvent model is registered
3. Test payment API endpoints
4. Configure Razorpay webhook URL

## Production Migration

```bash
# Set production environment
export DJANGO_SETTINGS_MODULE=talkeasy.settings.production

# Backup database first!
mysqldump -u admin -p talkeasytest > backup_$(date +%Y%m%d).sql

# Run migration
python manage.py migrate

# Restart application servers
sudo systemctl restart gunicorn
sudo systemctl restart daphne
```

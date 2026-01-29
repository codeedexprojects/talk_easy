# Talk Easy - Production Video/Audio Calling Platform

<div align="center">

**A scalable SaaS platform connecting users with executives via real-time video/audio calls**

![Django](https://img.shields.io/badge/Django-5.1.4-green)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![License](https://img.shields.io/badge/License-Proprietary-red)

</div>

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Setup Instructions](#setup-instructions)
- [Environment Variables](#environment-variables)
- [Razorpay Integration](#razorpay-integration)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)
- [Common Issues](#common-issues)

---

## 🎯 Overview

Talk Easy is a comprehensive calling platform that enables users to connect with verified executives through video and audio calls using the Agora WebRTC SDK. The platform includes integrated payment processing via Razorpay, real-time communication using WebSockets, and comprehensive admin management.

**Key Capabilities:**
- Real-time video/audio calling via Agora SDK
- Coin-based payment system with Razorpay integration
- Executive earnings and payout management
- Admin dashboard with session tracking
- WebSocket-based call status updates
- Comprehensive analytics and reporting

---

## 🏗️ Architecture

### Django Apps

```
talk_easy/
├── accounts/       # Admin authentication, roles, session management
├── users/          # User profiles, stats, referrals, blacklist
├── executives/     # Executive profiles, stats, earnings, blocking
├── calls/          # Agora call history, WebSocket consumers, ratings
├── payments/       # Razorpay integration, recharges, payouts, webhooks
└── talkeasy/       # Project settings (base, development, production)
```

### Request Flow

```mermaid
graph LR
    A[User/Admin] --> B[Django REST API]
    B --> C[JWT Auth]
    C --> D[Views]
    D --> E[Service Layer]
    E --> F[Models]
    F --> G[MySQL Database]
    
    H[User Call Request] --> I[WebSocket Consumer]
    I --> J[Agora SDK]
    J --> K[Real-time Call]
    
    L[Payment] --> M[Razorpay API]
    M --> N[Webhook]
    N --> E
```

### Authentication Flow

- **Admins**: JWT-based authentication with session tracking
- **Users**: JWT with custom UserProfileJWTAuthentication
- **Executives**: Custom token-based authentication via ExecutiveToken model

---

##  Features

### 💳 Payment System
- **Coin-based recharge** with multiple recharge plans
- **Razorpay integration** with webhook support
- **Secure signature verification** for all transactions
- **Idempotent payment processing** to prevent duplicates
- **Admin-initiated recharges** for customer support
- **Executive payout redemption** with admin approval workflow

### 📞 Calling System
- **Agora WebRTC** for high-quality video/audio calls
- **Real-time call status** via WebSockets (RabbitMQ)
- **Coin deduction** based on call duration
- **Executive earnings** calculated automatically
- **Call ratings** and feedback system
- **Call history** with detailed analytics

### 👥 User Management
- **OTP-based registration** and login
- **Profile management** with photos
- **Referral system** with rewards
- **Favorites** and blocked executives
- **Stats tracking** (coin balance, call duration)

### 🎯 Executive Management
- **Profile verification** workflow
- **Earnings tracking** (daily and lifetime)
- **Payout redemption** requests
- **Online/offline** status management
- **Language preferences**
- **Call statistics**

### 🔐 Admin Features
- **Role-based access** control
- **Session management** with device tracking
- **Analytics dashboard**
- **User and executive management**
- **Payment oversight**
- **System monitoring**

---

## 🛠️ Tech Stack

### Backend
- **Framework**: Django 5.1.4 + Django REST Framework
- **Real-time**: Django Channels + RabbitMQ
- **Database**: MySQL (AWS RDS)
- **Authentication**: JWT (SimpleJWT)
- **API**: RESTful API

### External Services
- **Video/Audio**: Agora SDK
- **Payments**: Razorpay
- **Messaging**: Twilio
- **Notifications**: Firebase Cloud Messaging
- **2FA**: 2Factor API

### Infrastructure
- **Database**: AWS RDS (MySQL)
- **Message Broker**: RabbitMQ
- **Storage**: Local/S3 for media files

---

## 🚀 Setup Instructions

### Prerequisites

- Python 3.11+
- MySQL 8.0+
- RabbitMQ (for WebSocket support)
- Git

### 1. Clone Repository

```bash
git clone <repository-url>
cd talk_easy
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your actual values (see [Environment Variables](#environment-variables) section).

### 5. Database Setup

```bash
# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 6. Run Development Server

```bash
# HTTP server
python manage.py runserver

# WebSocket server (separate terminal)
daphne -b 0.0.0.0 -p 8001 talkeasy.asgi:application
```

### 7. Access Application

- **API**: http://localhost:8000/
- **Admin**: http://localhost:8000/admin/
- **WebSocket**: ws://localhost:8001/

---

## 🔐 Environment Variables

### Core Django Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key (generate new for production) | `your-secret-key-here` |
| `DJANGO_SETTINGS_MODULE` | Settings module to use | `talkeasy.settings.production` |
| `DEBUG` | Debug mode (False in production) | `False` |
| `ALLOWED_HOSTS` | Allowed hostnames (comma-separated) | `talkeasy.com,api.talkeasy.com` |

### Database Configuration

| Variable | Description | Example |
|----------|-------------|---------|
| `DB_ENGINE` | Database backend | `django.db.backends.mysql` |
| `DB_NAME` | Database name | `talkeasytest` |
| `DB_USER` | Database username | `admin` |
| `DB_PASSWORD` | Database password | `your-db-password` |
| `DB_HOST` | Database host | `your-db.rds.amazonaws.com` |
| `DB_PORT` | Database port | `3306` |

### Razorpay Configuration

| Variable | Description | Where to Find |
|----------|-------------|---------------|
| `RAZORPAY_KEY_ID` | Razorpay Key ID | Dashboard > Account & Settings > API Keys |
| `RAZORPAY_KEY_SECRET` | Razorpay Key Secret | Dashboard > Account & Settings > API Keys |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook secret for signature verification | Dashboard > Webhooks > Add Endpoint |

### Agora Configuration

| Variable | Description | Where to Find |
|----------|-------------|---------------|
| `AGORA_APP_ID` | Agora Application ID | Agora Console > Project Management |
| `AGORA_APP_CERTIFICATE` | Agora App Certificate | Agora Console > Project > Edit |
| `AGORA_TOKEN_TTL_SECONDS` | Token validity duration | `3600` (1 hour) |

### Other Services

| Variable | Description | Example |
|----------|-------------|---------|
| `TWO_FACTOR_API_KEY` | 2Factor API key for OTP | Your 2Factor API key |
| `RABBITMQ_URL` | RabbitMQ connection URL | `amqp://user:pass@localhost:5672/` |
| `CORS_ALLOWED_ORIGINS` | Allowed CORS origins | `https://talkeasy.com,https://app.talkeasy.com` |

### JWT Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_ACCESS_TOKEN_LIFETIME_DAYS` | Access token validity (days) | `1` |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | Refresh token validity (days) | `7` |

---

## 💳 Razorpay Integration

### Setup Steps

#### 1. Create Razorpay Account

1. Sign up at [Razorpay Dashboard](https://dashboard.razorpay.com/)
2. Complete KYC verification
3. Get API keys from Settings > API Keys

#### 2. Configure Webhook

1. Go to Dashboard > Webhooks
2. Click "Add New Webhook"
3. Set URL: `https://yourdomain.com/payments/webhook/razorpay/`
4. Select events:
   - `payment.captured`
   - `payment.failed`
   - `order.paid`
5. Set webhook secret and copy it
6. Add secret to `.env` as `RAZORPAY_WEBHOOK_SECRET`

#### 3. Test Integration

**Test Mode:**
```python
RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXX
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxx
```

**Test Cards:**
- Success: `4111 1111 1111 1111`
- Failure: `4000 0000 0000 0002`

### Payment Flow

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Razorpay
    
    User->>Frontend: Select Recharge Plan
    Frontend->>Backend: POST /payments/recharge/initiate/
    Backend->>Razorpay: Create Order
    Razorpay-->>Backend: Order ID
    Backend-->>Frontend: Order Details
    Frontend->>Razorpay: Show Checkout
    User->>Razorpay: Complete Payment
    Razorpay-->>Frontend: Payment Success
    Frontend->>Backend: POST /payments/recharge/verify/
    Backend->>Backend: Verify Signature
    Backend->>Backend: Update Balance
    Backend-->>Frontend: Verification Success
    Razorpay->>Backend: Webhook Event
    Backend->>Backend: Process Webhook
```

### Webhook Events Handled

| Event | Action |
|-------|--------|
| `payment.captured` | Mark payment successful, credit coins |
| `payment.failed` | Mark payment failed |
| `order.paid` | Confirm order completion |

### Testing Webhooks Locally

Use ngrok to expose local server:

```bash
# Install ngrok
npm install -g ngrok

# Expose port 8000
ngrok http 8000

# Copy ngrok URL and set in Razorpay webhook settings
```

---

## 🚢 Deployment

### Pre-Deployment Checklist

- [ ] Set `DEBUG=False` in production .env
- [ ] Configure `ALLOWED_HOSTS` with actual domains
- [ ] Set secure `SECRET_KEY` (generate new)
- [ ] Configure `CORS_ALLOWED_ORIGINS` with frontend domains
- [ ] Set Razorpay production keys
- [ ] Configure webhook URL to production domain
- [ ] Set up HTTPS/SSL certificate
- [ ] Configure production database
- [ ] Set up RabbitMQ for WebSockets
- [ ] Configure logging directory
- [ ] Run `collectstatic` for static files
- [ ] Test payment flow end-to-end

### Environment Settings

**Development:**
```bash
export DJANGO_SETTINGS_MODULE=talkeasy.settings.development
```

**Production:**
```bash
export DJANGO_SETTINGS_MODULE=talkeasy.settings.production
```

### Database Migrations

```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

### Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### Run Production Server

**Option 1: Gunicorn (HTTP)**
```bash
gunicorn talkeasy.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

**Option 2: Daphne (WebSocket)**
```bash
daphne -b 0.0.0.0 -p 8001 talkeasy.asgi:application
```

---

## 🔌 API Documentation

### Authentication

**Admin Login:**
```http
POST /accounts/login/
Content-Type: application/json

{
  "email": "admin@example.com",
  "password": "password"
}

Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
  "user_id": 1,
  "email": "admin@example.com"
}
```

### Payment Endpoints

**Initiate Recharge:**
```http
POST /payments/recharge/initiate/
Authorization: Bearer <token>
Content-Type: application/json

{
  "plan_id": 1
}

Response:
{
  "message": "Razorpay order created successfully",
  "order_id": "order_XXXXXXXXXXXX",
  "amount": 299.00,
  "razorpay_key": "rzp_live_XXXXXXXXXXXX",
  "coins_to_add": 100
}
```

**Verify Payment:**
```http
POST /payments/recharge/verify/
Authorization: Bearer <token>
Content-Type: application/json

{
  "razorpay_order_id": "order_XXXXXXXXXXXX",
  "razorpay_payment_id": "pay_XXXXXXXXXXXX",
  "razorpay_signature": "signature_here"
}

Response:
{
  "message": "Payment verified and recharge successful",
  "coins_added": 100,
  "amount_paid": 299.00,
  "current_coin_balance": 350
}
```

**Razorpay Webhook:**
```http
POST /payments/webhook/razorpay/
X-Razorpay-Signature: <signature>
Content-Type: application/json

{
  "event": "payment.captured",
  "payload": { ... }
}

Response:
{
  "status": "ok"
}
```

---

## ❓ Common Issues & Fixes

### Payment webhook not received

**Symptoms:** Payment successful but coins not credited

**Fixes:**
1. Check Razorpay Dashboard > Webhooks > Event Logs
2. Verify webhook URL is publicly accessible (HTTPS)
3. Check `WebhookEvent` model in admin for received events
4. Check logs: `tail -f logs/payments.log`
5. Verify `RAZORPAY_WEBHOOK_SECRET` is set correctly

### WebSocket connection fails

**Symptoms:** Real-time call updates not working

**Fixes:**
1. Verify RabbitMQ is running: `sudo systemctl status rabbitmq-server`
2. Check CHANNEL_LAYERS configuration in settings
3. Ensure Daphne server is running: `daphne talkeasy.asgi:application`
4. Check WebSocket URL format: `ws://` not `http://`

### Database connection error

**Symptoms:** `OperationalError: (2003, "Can't connect to MySQL server")`

**Fixes:**
1. Verify database credentials in `.env`
2. Check MySQL is running: `sudo systemctl status mysql`
3. Test connection: `mysql -u admin -p -h your-host`
4. Check firewall rules for port 3306

### Import errors after deployment

**Symptoms:** `ModuleNotFoundError` or `ImportError`

**Fixes:**
1. Verify virtual environment is activated
2. Install dependencies: `pip install -r requirements.txt`
3. Check `DJANGO_SETTINGS_MODULE` environment variable
4. Restart application server

### Static files not loading

**Symptoms:** CSS/JS not loading in production

**Fixes:**
1. Run `python manage.py collectstatic`
2. Configure web server (Nginx) to serve `/static/` and `/media/`
3. Check `STATIC_ROOT` and `STATIC_URL` in settings
4. Verify file permissions

---

## 📝 License

Proprietary - All rights reserved

---

## 👥 Support

For technical support or questions:
- Email: support@talkeasy.com
- Documentation: https://docs.talkeasy.com

---

**Built with ❤️ using Django, Agora, and Razorpay**
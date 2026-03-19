# Loan Management System Setup Guide

## 🚀 Quick Setup

### Prerequisites
- Python 3.14.3+
- Django 5.0.2+
- PostgreSQL or SQLite database
- Redis (for caching, optional)

### Installation Steps

1. **Install Dependencies**
```bash
pip install django>=5.0.2
pip install face_recognition>=1.3.0
pip install pillow>=10.0.0
pip install numpy>=1.24.0
pip install opencv-python>=4.8.0
pip install dlib>=19.24.0
```

2. **Database Setup**
```bash
# For SQLite (default)
python manage.py migrate

# For PostgreSQL
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'alba_loans',
        'USER': 'postgres',
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

3. **Create Superuser**
```bash
python manage.py createsuperuser
```

4. **Load Initial Data**
```bash
python manage.py loaddata fixtures/loan_products.json
python manage.py loaddata/fixtures/system_users.json
```

5. **Collect Static Files**
```bash
python manage.py collectstatic
```

6. **Run Development Server**
```bash
python manage.py runserver
```

## 📋 Initial Configuration

### 1. Create Loan Products
```python
# Via Django admin or management command
python manage.py create_loan_products
```

### 2. Setup User Roles
- System Administrator
- Credit Officer
- Finance Officer
- HR Officer
- Customer

### 3. Configure Face Recognition
```python
# settings.py
FACE_RECOGNITION_SETTINGS = {
    'TOLERANCE': 0.6,
    'MAX_PHOTO_SIZE': 5 * 1024 * 1024,  # 5MB
    'ALLOWED_FORMATS': ['jpg', 'jpeg', 'png'],
    'STORAGE_PATH': 'media/face_photos/',
}
```

### 4. Setup Accounting Integration
```python
# settings.py
ACCOUNTING_SETTINGS = {
    'AUTO_SYNC': True,
    'SYNC_INTERVAL': 300,  # 5 minutes
    'JOURNAL_PREFIX': 'LOAN',
    'ERROR_RETRY': 3,
}
```

## 🔧 Configuration Files

### settings.py additions
```python
# Loan system settings
LOAN_SETTINGS = {
    'MAX_APPLICATION_AMOUNT': 1000000,
    'DEFAULT_INTEREST_RATE': 15.0,
    'PROCESSING_FEE_RATE': 2.5,
    'LATE_PAYMENT_PENALTY': 5.0,
}

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

### urls.py updates
```python
# Main urls.py
urlpatterns = [
    path('loans/', include('loans.urls')),
    path('admin/', admin.site.urls),
    # ... other urls
]
```

## 🧪 Testing Setup

### Run Tests
```bash
# Run all tests
python manage.py test loans

# Run specific test
python manage.py test loans.tests.test_models

# With coverage
coverage run --source='.' manage.py test loans
coverage report
```

### Test Database
```bash
# Use separate test database
python manage.py test --settings=config.test_settings
```

## 📊 Performance Optimization

### Database Indexes
```python
# models.py - Add indexes
class LoanApplication(models.Model):
    # ... fields
    
    class Meta:
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['application_number']),
        ]
```

### Caching Setup
```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

## 🔍 Troubleshooting

### Common Issues

1. **Face Recognition Installation**
```bash
# If dlib installation fails
# Install cmake first
sudo apt-get install cmake
# Or use conda
conda install dlib
```

2. **Database Migration Errors**
```bash
# Reset migrations
python manage.py migrate loans zero
python manage.py migrate loans
```

3. **Static Files Not Loading**
```bash
python manage.py collectstatic --noinput
# Check STATIC_URL and STATIC_ROOT settings
```

4. **Permission Errors**
```bash
# Check file permissions
chmod 755 media/
chmod 644 media/*
```

### Debug Mode
```python
# settings.py
DEBUG = True
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'loans': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## 🚀 Production Deployment

### Environment Variables
```bash
export DJANGO_SETTINGS_MODULE=config.production
export SECRET_KEY='your-secret-key'
export DATABASE_URL='postgresql://user:pass@localhost/db'
export REDIS_URL='redis://localhost:6379/0'
```

### Gunicorn Setup
```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### Nginx Configuration
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /static/ {
        alias /path/to/staticfiles/;
    }
    
    location /media/ {
        alias /path/to/media/;
    }
    
    location / {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

## 📞 Support

For technical support:
1. Check the logs: `tail -f logs/django.log`
2. Review the README.md documentation
3. Check the troubleshooting section above
4. Contact the development team

## 🔄 Maintenance

### Regular Tasks
- Daily: Backup database
- Weekly: Review system logs
- Monthly: Update dependencies
- Quarterly: Security audit

### Backup Commands
```bash
# Database backup
pg_dump alba_loans > backup_$(date +%Y%m%d).sql

# Media files backup
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/
```

---

**Note**: This setup guide covers the basic installation and configuration. For detailed customization and advanced features, refer to the main README.md file.

"""Create superuser command"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import User

# Create superuser
email = 'admin@albacapital.com'
if not User.objects.filter(email=email).exists():
    user = User.objects.create_superuser(
        email=email,
        password='admin123',
        first_name='Admin',
        last_name='User'
    )
    print(f'✓ Superuser created: {email} / admin123')
else:
    print(f'✗ Superuser already exists: {email}')

"""
Accounting app configuration
"""

from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounting'
    verbose_name = 'Financial Management & Accounting'
    
    def ready(self):
        """Import signals when app is ready"""
        import accounting.signals

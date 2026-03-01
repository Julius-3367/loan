"""
URL configuration for Alba Capital ERP System
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Core app (authentication, landing page, and dashboards)
    path('', include('core.urls')),
    
    # Loans app
    path('loans/', include('loans.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Customize admin site
admin.site.site_header = 'Alba Capital ERP Administration'
admin.site.site_title = 'Alba Capital ERP'
admin.site.index_title = 'System Administration'


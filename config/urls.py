"""
URL configuration for Alba Capital ERP System
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # Core app (authentication, landing page, dashboards)
    path("", include("core.urls")),
    # Loans app (customer-facing loan portal)
    path("loans/", include("loans.urls")),
]

# Serve media and static files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Customize admin site
admin.site.site_header = "Alba Capital Administration"
admin.site.site_title = "Alba Capital"
admin.site.index_title = "System Administration"

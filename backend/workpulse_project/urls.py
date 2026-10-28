from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]

# Intentionally do not expose MEDIA_URL directly. Screenshots must be accessed
# through /api/screenshots/<id>/view/ or /api/screenshots/<id>/download/ so
# ScreenshotAccessLog is created for every access.

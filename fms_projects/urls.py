from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),

    path('', include('fms_app.urls')),
]

# Uploaded media is served by fms_app.views.protected_media (login + RBAC checked),
# never as a public static directory.

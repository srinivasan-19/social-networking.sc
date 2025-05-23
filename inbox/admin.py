from django.contrib import admin

# Register your models here.

from .models import Inbox, Notification

admin.site.register(Inbox)
admin.site.register(Notification)

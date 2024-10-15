# admin.py
from django.contrib import admin
from .models import Baggage, Transfer, BaggageTransfer

admin.site.register(Baggage)
admin.site.register(Transfer)
admin.site.register(BaggageTransfer)
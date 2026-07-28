from django.contrib import admin
from .models import Location, SystemARecord, SystemBEntry, ImportIssue, Disagreement

admin.site.register(Location)
admin.site.register(SystemARecord)
admin.site.register(SystemBEntry)
admin.site.register(ImportIssue)
admin.site.register(Disagreement)

from django.contrib import admin
from .models import *
# Register your models here.
admin.site.register(Executive),
admin.site.register(ExecutiveStats),
admin.site.register(BlockedusersByExecutive),
admin.site.register(ExecutiveProfilePicture),
admin.site.register(ExecutiveToken),
admin.site.register(Language),



from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(RechargePlanCatogary)
admin.site.register(RechargePlan)
admin.site.register(UserRecharge)
admin.site.register(RedemptionOption)
admin.site.register(ExecutivePayoutRedeem)
admin.site.register(WebhookEvent)

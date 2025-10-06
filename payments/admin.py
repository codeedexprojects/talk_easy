from django.contrib import admin
from payments.models import *

# Register your models here.
admin.site.register(RechargePlanCatogary),
admin.site.register(RechargePlan),
admin.site.register(UserRecharge),
admin.site.register(RedemptionOption),
admin.site.register(ExecutivePayoutRedeem)



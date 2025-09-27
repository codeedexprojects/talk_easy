from django.contrib import admin
from .models import *

admin.site.register(UserProfile),
admin.site.register(UserStats),
admin.site.register(ReferralHistory),
admin.site.register(DeletedUser),
admin.site.register(Favourite),
admin.site.register(Rating),
admin.site.register(Career),
admin.site.register(CarouselImage),


from django.db import models
from decimal import Decimal
# Create your models here.

class RechargePlanCatogary(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    

class RechargePlan(models.Model):
    plan_name = models.CharField(max_length=100)
    coin_package = models.PositiveIntegerField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_percentage = models.FloatField(default=0)
    category_id = models.ForeignKey(RechargePlanCatogary, on_delete=models.CASCADE, related_name='recharge_plans', default=1)
    total_talktime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    def calculate_final_price(self):
        return self.base_price - (self.base_price * Decimal(self.discount_percentage / 100))

    def get_adjusted_coin_package(self):
        bonus_percentage = Decimal(self.discount_percentage) / 100
        return int(self.coin_package + (self.coin_package * bonus_percentage))

    def calculate_talk_time_minutes(self):
        return self.get_adjusted_coin_package() / 180

    def save(self, *args, **kwargs):
        self.total_talktime = self.calculate_talk_time_minutes()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.plan_name

from django.db import models
from decimal import Decimal
from executives.models import Executive
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

from users.models import UserProfile

class UserRecharge(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="recharges")
    plan = models.ForeignKey(RechargePlan, on_delete=models.CASCADE)
    coins_added = models.PositiveIntegerField()
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    is_successful = models.BooleanField(default=True) 

    def save(self, *args, **kwargs):
        if self.is_successful:
            if hasattr(self.user, "stats"):
                self.user.stats.coin_balance += self.coins_added
                self.user.stats.save(update_fields=["coin_balance"])
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} - {self.plan.plan_name} ({self.coins_added} coins)"


class RedemptionOption(models.Model):
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        unique=True,
        help_text="Fixed redemption amount available for executives (e.g., 500, 1000)"
    )
    is_active = models.BooleanField(default=True, help_text="Is this option available?")
    is_deleted = models.BooleanField(default=False, help_text="Soft delete flag")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Redeem ₹{self.amount}"

    class Meta:
        ordering = ["amount"]


class ExecutivePayoutRedeem(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("paid", "Paid"),
    ]

    executive = models.ForeignKey(
        Executive,
        on_delete=models.CASCADE,
        related_name="payout_redeems"
    )
    redemption_option = models.ForeignKey(
        RedemptionOption,
        on_delete=models.CASCADE,
        related_name="redeem_requests"
    )
    approved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Final amount approved by admin"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    notes = models.TextField(blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.executive.name} requested {self.redemption_option.amount} ({self.status})"

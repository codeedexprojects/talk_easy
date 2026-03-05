"""
Pricing utilities for executive rates.
Central place for determining current amount_per_min for executives.
"""
from django.core.cache import cache
from django.utils import timezone
from decimal import Decimal
from .models import GlobalPricing, RateSchedule, ExecutiveStats


def get_current_amount_per_min(executive):
    """
    Get the current amount_per_min for an executive based on:
    1. Executive-level override if use_personal_rate is True
    2. Active RateSchedule matching current time/day (highest priority wins)
    3. GlobalPricing default
    
    Uses caching for performance (1-minute TTL).
    """
    cache_key = f"executive_rate_{executive.id}"
    cached_rate = cache.get(cache_key)
    if cached_rate is not None:
        return Decimal(str(cached_rate))
    
    # Check executive-level override
    if executive.use_personal_rate:
        try:
            exec_stats = executive.stats
            if exec_stats.amount_per_min is not None:
                cache.set(cache_key, str(exec_stats.amount_per_min), timeout=60)  # 1 minute
                return exec_stats.amount_per_min
        except ExecutiveStats.DoesNotExist:
            pass
    
    # Get current time and day
    now = timezone.now()
    current_time = now.time()
    current_weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    # Find matching active schedules, ordered by priority desc
    # Use Python filtering since SQLite doesn't support ANY
    all_schedules = RateSchedule.objects.filter(active=True).order_by('-priority')
    matching_schedules = []
    
    for schedule in all_schedules:
        if schedule.matches_time(current_time, current_weekday):
            matching_schedules.append(schedule)
            break  # Since they're ordered by priority, first match is highest priority
    
    if matching_schedules:
        rate = matching_schedules[0].amount_per_min
        cache.set(cache_key, str(rate), timeout=60)
        return rate
    
    # Fallback to global default
    try:
        global_pricing = GlobalPricing.objects.first()
        if global_pricing:
            rate = global_pricing.default_amount_per_min
        else:
            rate = Decimal('2.0')  # Hardcoded fallback
    except GlobalPricing.DoesNotExist:
        rate = Decimal('2.0')
    
    cache.set(cache_key, str(rate), timeout=60)
    return rate
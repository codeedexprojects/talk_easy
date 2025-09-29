from django.utils import timezone
from .models import AdminSession

class JWTSessionTrackingMiddleware:
    """Middleware to track JWT activity and update last_activity"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Extract JTI from JWT token if present
        if hasattr(request, 'auth') and request.auth:
            jti = request.auth.get('jti')
            if jti:
                # Update last activity
                AdminSession.objects.filter(
                    jwt_jti=jti,
                    is_active=True
                ).update(last_activity=timezone.now())
                
                # Store JTI in request for later use
                request.jwt_jti = jti
        
        response = self.get_response(request)
        return response
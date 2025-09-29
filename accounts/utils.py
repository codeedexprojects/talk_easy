from user_agents import parse
import uuid

def parse_user_agent(user_agent_string):
    """Parse user agent string to extract device info"""
    try:
        user_agent = parse(user_agent_string)
        
        device_type = 'desktop'
        if user_agent.is_mobile:
            device_type = 'mobile'
        elif user_agent.is_tablet:
            device_type = 'tablet'
        elif user_agent.is_bot:
            device_type = 'bot'
        
        device_name = user_agent.device.family
        if device_name == 'Other':
            device_name = f"{user_agent.os.family} Device"
        
        return {
            'device_type': device_type,
            'device_name': device_name,
            'browser': f"{user_agent.browser.family} {user_agent.browser.version_string}",
            'os': f"{user_agent.os.family} {user_agent.os.version_string}",
        }
    except Exception:
        return {
            'device_type': 'unknown',
            'device_name': 'Unknown Device',
            'browser': 'Unknown Browser',
            'os': 'Unknown OS',
        }

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip
"""
Settings package initialization

Loads the appropriate settings module based on DJANGO_SETTINGS_MODULE environment variable.
Defaults to development settings.
"""

import os
from decouple import config

# Determine which settings to use
settings_module = config('DJANGO_SETTINGS_MODULE', default='talkeasy.settings.production')

# Import the appropriate settings
if 'production' in settings_module:
    from .production import *
elif 'development' in settings_module:
    from .development import *
else:
    # Default to development
    from .development import *

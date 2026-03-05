// @ts-check
// Types from @postman/test-script-types-plugin are available

// Global setup for TalkEasy Pricing APIs
console.log('TalkEasy Pricing APIs Collection Loaded');

// Set default base URL if not set
if (!pm.environment.get('base_url')) {
    pm.environment.set('base_url', 'http://localhost:8000');
    console.log('Set default base_url to http://localhost:8000');
}

// Validate environment variables
const requiredVars = ['base_url', 'admin_jwt_token'];
const missingVars = requiredVars.filter(varName => !pm.environment.get(varName));

if (missingVars.length > 0) {
    console.warn('Missing required environment variables:', missingVars.join(', '));
    console.warn('Please set these in your environment before running requests.');
}

// Set collection variables for common values
pm.collectionVariables.set('api_version', 'v1');
pm.collectionVariables.set('decimal_precision', '2');

// Log current environment
console.log('Current environment:', pm.environment.name || 'No environment selected');
console.log('Base URL:', pm.environment.get('base_url'));
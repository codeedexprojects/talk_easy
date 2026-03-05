// @ts-check
// Types from @postman/test-script-types-plugin are available

// Set base URL if not already set
if (!pm.environment.get('base_url')) {
    pm.environment.set('base_url', 'http://localhost:8000');
}

// Check if admin JWT token is available
const token = pm.environment.get('admin_jwt_token');
if (!token) {
    console.warn('Admin JWT token not found in environment variables.');
    console.warn('Please set the "admin_jwt_token" environment variable first.');
    console.warn('You can obtain this by logging in as an admin user.');
}

// Set Authorization header if token exists
if (token) {
    pm.request.headers.add({
        key: 'Authorization',
        value: `Bearer ${token}`
    });
}

// Add Content-Type header for requests with body
if (pm.request.body && pm.request.body.mode === 'raw') {
    pm.request.headers.add({
        key: 'Content-Type',
        value: 'application/json'
    });
}
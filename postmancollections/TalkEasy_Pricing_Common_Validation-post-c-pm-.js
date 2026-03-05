// @ts-check
// Types from @postman/test-script-types-plugin are available

// Common validations for all TalkEasy Pricing API responses

// Check for server errors
pm.test('No server errors', function () {
    pm.expect(pm.response.code).to.not.be.oneOf([500, 501, 502, 503, 504]);
});

// Check response time
pm.test('Response time under 5 seconds', function () {
    pm.expect(pm.response.responseTime).to.be.below(5000);
});

// Check Content-Type header
pm.test('Response has JSON Content-Type', function () {
    const contentType = pm.response.headers.get('Content-Type');
    pm.expect(contentType).to.include('application/json');
});

// Authentication error handling
if (pm.response.code === 401) {
    pm.test('Authentication error details', function () {
        const responseJson = pm.response.json();
        pm.expect(responseJson).to.have.property('detail');
        console.warn('Authentication failed. Check admin_jwt_token.');
    });
}

// Permission error handling
if (pm.response.code === 403) {
    pm.test('Permission error details', function () {
        const responseJson = pm.response.json();
        pm.expect(responseJson).to.have.property('detail');
        console.warn('Permission denied. Ensure user has admin privileges.');
    });
}

// Validation error handling
if (pm.response.code === 400) {
    pm.test('Validation error structure', function () {
        const responseJson = pm.response.json();
        // Could check for specific validation error formats
        console.warn('Validation error:', JSON.stringify(responseJson, null, 2));
    });
}

// Store created resource IDs for follow-up requests
if (pm.request.method === 'POST' && pm.response.code === 201) {
    const responseJson = pm.response.json();
    if (responseJson.id) {
        if (pm.request.url.path.includes('schedules')) {
            pm.environment.set('schedule_id', responseJson.id);
            console.log('Stored schedule_id:', responseJson.id);
        }
    }
}

// Log response summary
console.log(`Response: ${pm.response.code} ${pm.response.status} (${pm.response.responseTime}ms)`);
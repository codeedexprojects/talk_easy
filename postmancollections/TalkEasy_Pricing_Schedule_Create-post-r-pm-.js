// @ts-check
// Types from @postman/test-script-types-plugin are available

// Parse the response body as JSON
const responseBodyJson = pm.response.json();

// Check that the status code is 201 (Created)
pm.test('Status code is 201', function () {
  pm.response.to.have.status(201);
});

// Check that the response has all required fields
pm.test('Response has all required fields', function () {
  pm.expect(responseBodyJson).to.be.an('object');
  pm.expect(responseBodyJson).to.have.property('id');
  pm.expect(responseBodyJson).to.have.property('name');
  pm.expect(responseBodyJson).to.have.property('amount_per_min');
  pm.expect(responseBodyJson).to.have.property('active');
  pm.expect(responseBodyJson).to.have.property('priority');
  pm.expect(responseBodyJson).to.have.property('days_of_week');
  pm.expect(responseBodyJson).to.have.property('start_time');
  pm.expect(responseBodyJson).to.have.property('end_time');
  pm.expect(responseBodyJson).to.have.property('created_at');
  pm.expect(responseBodyJson).to.have.property('updated_at');
});

// Check that amount_per_min is a valid decimal
pm.test('amount_per_min is a valid decimal', function () {
  const amount = parseFloat(responseBodyJson.amount_per_min);
  pm.expect(amount).to.be.a('number');
  pm.expect(amount).to.be.above(0);
});

// Check that priority is a non-negative integer
pm.test('priority is a valid non-negative integer', function () {
  pm.expect(responseBodyJson.priority).to.be.a('number');
  pm.expect(responseBodyJson.priority).to.be.at.least(0);
});

// Check that days_of_week is an array
pm.test('days_of_week is an array', function () {
  pm.expect(responseBodyJson.days_of_week).to.be.an('array');
});

// Store the created schedule ID for future requests
pm.test('Store schedule ID', function () {
  if (responseBodyJson.id) {
    pm.environment.set('schedule_id', responseBodyJson.id);
  }
});
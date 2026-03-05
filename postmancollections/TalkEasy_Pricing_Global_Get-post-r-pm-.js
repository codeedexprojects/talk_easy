// @ts-check
// Types from @postman/test-script-types-plugin are available

// Parse the response body as JSON
const responseBodyJson = pm.response.json();

// Check that the status code is 200
pm.test('Status code is 200', function () {
  pm.response.to.have.status(200);
});

// Check that the response has the expected structure
pm.test('Response has required fields', function () {
  pm.expect(responseBodyJson).to.be.an('object');
  pm.expect(responseBodyJson).to.have.property('id');
  pm.expect(responseBodyJson).to.have.property('default_amount_per_min');
  pm.expect(responseBodyJson).to.have.property('created_at');
  pm.expect(responseBodyJson).to.have.property('updated_at');
});

// Check that default_amount_per_min is a valid decimal
pm.test('default_amount_per_min is a valid decimal', function () {
  const amount = parseFloat(responseBodyJson.default_amount_per_min);
  pm.expect(amount).to.be.a('number');
  pm.expect(amount).to.be.above(0);
});

// Check that timestamps are valid
pm.test('Timestamps are valid', function () {
  pm.expect(responseBodyJson.created_at).to.be.a('string');
  pm.expect(responseBodyJson.updated_at).to.be.a('string');
  // Could add more specific date validation if needed
});
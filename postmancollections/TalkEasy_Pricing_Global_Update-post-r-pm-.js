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

// Check that default_amount_per_min matches what was sent
pm.test('default_amount_per_min was updated', function () {
  const requestBody = JSON.parse(pm.request.body.raw);
  const expectedAmount = requestBody.default_amount_per_min;
  pm.expect(responseBodyJson.default_amount_per_min).to.equal(expectedAmount);
});

// Check that updated_at is newer than created_at
pm.test('updated_at is after created_at', function () {
  const createdAt = new Date(responseBodyJson.created_at);
  const updatedAt = new Date(responseBodyJson.updated_at);
  pm.expect(updatedAt.getTime()).to.be.at.least(createdAt.getTime());
});
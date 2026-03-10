const http = require('http');

const data = JSON.stringify({
    eigenvalues: [0.5, 1.5],
    problemType: 'boundstate'
});

const options = {
    hostname: 'localhost',
    port: 3001,
    path: '/api/physics/explain',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length
    }
};

const req = http.request(options, (res) => {
    console.log(`Status Code: ${res.statusCode}`);
    console.log(`Headers: ${JSON.stringify(res.headers)}`);

    let body = '';
    res.on('data', (chunk) => {
        body += chunk;
    });

    res.on('end', () => {
        console.log('Body:');
        console.log(body);
    });
});

req.on('error', (error) => {
    console.error(error);
});

req.write(data);
req.end();

const http = require('http');

// Create a large fake result (approx 200KB)
const largeArray = new Array(20000).fill(0).map((_, i) => i * 0.001);
const data = JSON.stringify({
    eigenvalues: [0.5, 1.5, 2.5, 3.5, 4.5],
    problemType: 'boundstate',
    wavefunctions: [
        { psi_up: largeArray, psi_down: largeArray },
        { psi_up: largeArray, psi_down: largeArray }
    ]
});

const options = {
    hostname: 'localhost',
    port: 3001,
    path: '/api/physics/explain',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
    }
};

const req = http.request(options, (res) => {
    console.log(`Status Code: ${res.statusCode}`);

    let body = '';
    res.on('data', (chunk) => {
        body += chunk;
    });

    res.on('end', () => {
        try {
            const parsed = JSON.parse(body);
            console.log('Result:', parsed);
        } catch (e) {
            console.log('Body (first 100 chars):', body.substring(0, 100));
        }
    });
});

req.on('error', (error) => {
    console.error(error);
});

req.write(data);
req.end();

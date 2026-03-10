const http = require('http');

const config = {
    engineMode: 'octopus3D',
    moleculeName: 'H2',
    calcMode: 'gs'
};

const req = http.request({
    host: '127.0.0.1',
    port: 8000,
    path: '/solve',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    }
}, (res) => {
    let data = '';
    res.on('data', (chunk) => data += chunk);
    res.on('end', () => {
        const json = JSON.parse(data);
        console.log("Status:", json.status);
        console.log("Message:", json.message);
        console.log("STDOUT TAIL:\n", json.stdout_tail);
        console.log("STDERR TAIL:\n", json.stderr_tail);
    });
});

req.on('error', (e) => console.error(e));
req.write(JSON.stringify(config));
req.end();

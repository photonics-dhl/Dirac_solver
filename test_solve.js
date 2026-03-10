const http = require('http');

const req = http.request({
    host: '127.0.0.1',
    port: 8000,
    path: '/solve',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
}, (res) => {
    let chunks = [];
    res.on('data', d => chunks.push(d));
    res.on('end', () => console.log(Buffer.concat(chunks).toString()));
});
req.write(JSON.stringify({ engineMode: "octopus3D", moleculeName: "H2", calcMode: "td", tdSteps: 50 }));
req.end();

const http = require('http');

const config = {
    unitSystem: 'natural',
    mass: 0.511,
    charge: -1,
    energy: 1,
    dimensionality: '3D',
    spatialRange: 10,
    gridPoints: 200,
    gridSpacing: 0.05,
    boundaryCondition: 'dirichlet',
    potentialType: 'Custom',
    potentialStrength: 10,
    wellWidth: 1,
    equationType: 'Schrodinger',
    problemType: 'molecular',
    picture: 'schrodinger',
    numTimeSteps: 100,
    totalTime: 10,
    gaussianCenter: -2,
    gaussianWidth: 0.5,
    gaussianMomentum: 5,
    scatteringEnergyMin: 0.1,
    scatteringEnergyMax: 20,
    scatteringEnergySteps: 200,
    engineMode: 'octopus3D',
    moleculeName: 'H2',
    calcMode: 'td',
    tdSteps: 50
};

const query = encodeURIComponent(JSON.stringify(config));
const url = `http://localhost:3001/api/physics/stream?config=${query}`;

http.get(url, (res) => {
    res.on('data', (d) => process.stdout.write(d));
}).on('error', (e) => console.error(e));

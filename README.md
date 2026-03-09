# Dirac Solver

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)

A web-based solver for the Dirac and Schrödinger equations in quantum mechanics and photonics applications.

## Overview

**Dirac Solver** provides a browser-accessible interface for numerically solving the Dirac equation (relativistic quantum mechanics) and the Schrödinger equation (non-relativistic quantum mechanics). It is aimed at researchers and students working in quantum physics, photonics, and condensed matter.

## Features

- Numerical solution of the 1D/2D Dirac equation
- Numerical solution of the Schrödinger equation
- Interactive web interface for parameter input and visualization
- Export of results (eigenvalues, wavefunctions)

## Directory Structure

```
Dirac_solver/
├── src/              # Source code (solver core and web application)
├── tests/            # Unit and integration tests
├── docs/             # Documentation and references
├── CHANGELOG.md      # Version history
└── README.md         # This file
```

## Getting Started

### Prerequisites

- Python 3.8 or higher
- `pip` package manager

### Installation

```bash
git clone https://github.com/photonics-dhl/Dirac_solver.git
cd Dirac_solver
pip install -r requirements.txt
```

### Running the Web Solver

```bash
python src/app.py
```

Then open your browser at `http://localhost:5000`.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

This project is licensed under the [MIT License](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

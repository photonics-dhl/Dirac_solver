# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- 3D Octopus DFT engine integration via Docker MCP server
- LangGraph orchestration pipeline (auditParameters → validateSchema → dispatchMcpCompute)
- Vite proxy to bypass Alibaba Cloud firewall on ports 3001/8000
- systemd service for persistent Node.js API management
- VisIt headless rendering pipeline (planned)

## [0.1.0] - 2026-03-10

### Added
- Initial project structure with React/Vite frontend and Node.js backend
- Local 1D quantum well solver (demo/fallback path)
- Docker-based Octopus binary integration
- Python MCP server for Jinja2 inp templating and HDF5/NetCDF parsing
- LLM-powered physical sanity check via zchat

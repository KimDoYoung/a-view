# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A-View is a LibreOffice-based document viewer service for AssetERP that converts Office documents (Excel, Word, PowerPoint) to PDF/HTML for web viewing. The application replaces Google's gview service which is no longer reliably supported.

## Common Development Commands

### Docker Development

```bash
# Redis setup (required dependency)
docker run -d --name redis-container -p 6379:6379 redis

# Using deploy.sh script (recommended)
./deploy.sh up local                    # Start development environment
./deploy.sh build local --no-cache      # Build without cache
./deploy.sh logs local -f               # View real-time logs
./deploy.sh down local                  # Stop services
./deploy.sh clean-all local             # Complete cleanup

# Direct docker-compose commands
docker compose -f docker-compose.local.yml build
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml logs -f aview
```

### Python Environment

```bash
# Run directly (for development)
python app/main.py

# Using uv (Python package manager)
uv sync  # Install dependencies from uv.lock
```

### Testing

```bash
# API testing scripts in code_sample/
./code_sample/check.sh     # Test successful conversions
./code_sample/error.sh     # Test error cases
```

## Architecture

### Core Components

**FastAPI Application Structure:**

- `app/main.py` - Application entry point with startup/shutdown lifecycle management
- `app/core/` - Core utilities and configuration
  - `config.py` - Environment-based configuration using `.env.{AVIEW_MODE}` files
  - `view_lib.py` - Main document conversion logic using LibreOffice
  - `convert_lib.py` - File conversion utilities
  - `utils.py` - General utilities for Redis, file handling, caching
  - `stats_db.py` - SQLite-based statistics database
  - `stat_scheduler.py` - Background scheduler for daily/weekly statistics
- `app/endpoints/` - API route handlers
- `app/domain/` - Data schemas and file type definitions
- `app/templates/` - Jinja2 HTML templates

### Key APIs

**Main Conversion APIs:**

- `/convert` - Converts Office files to PDF/HTML, returns JSON with download URL
- `/view` - Displays converted documents in web viewer (auto-detects output format)

**Supporting APIs:**

- `/aview/health` - System health check (LibreOffice + Redis status)
- `/stats/*` - Statistics endpoints for dashboard
- `/cache/*` - Cache management endpoints
- `/aview/run-test` - Built-in testing interface

### Environment Configuration

The application uses environment-based configuration:

- `AVIEW_MODE` environment variable determines which `.env.{mode}` file to load
- Supported modes: `local`, `test`, `real`
- Key settings in `app/core/config.py`

### Dependencies

**Required Services:**

- Redis - For caching (runs on localhost:6379 in development)
- LibreOffice - For document conversion (must be installed on system)

**Key Python Dependencies:**

- FastAPI with Uvicorn
- Redis client
- aiohttp for file downloads
- Jinja2 for templating
- SQLite for statistics (no external DB required)

### File Processing Flow

1. File input via URL or local path
2. Download/cache original file (Redis + filesystem)
3. Convert using LibreOffice subprocess calls
4. Cache converted file with TTL (default 24 hours)
5. Serve via `/aview/pdf/{hash}` or `/aview/html/{hash}` endpoints

### Docker Deployment

Three environments supported:

- **local** - Windows development with Docker Desktop
- **test** - Linux test server (`/data1/aview`)
- **real** - Linux production with SSL (`/opt/aview`)

Each environment has its own Dockerfile and docker-compose configuration.

## Development Notes

- Application supports both direct Python execution and Docker deployment
- Built-in file upload/testing interface at `/aview/run-test`
- Statistics are automatically collected daily via background scheduler
- Cache cleanup happens automatically on application shutdown
- SSL configuration required for production environment
- Graceful shutdown handling with signal management

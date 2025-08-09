# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python CLI tool for downloading photos and videos from Brightwheel, a daycare communication platform. The tool authenticates with Brightwheel's API, retrieves student media, and saves it locally with proper EXIF metadata.

## Development Commands

### Package Management
This project uses `uv` for package management (with fallback to Poetry).

```bash
# Install dependencies
uv sync

# Run the CLI tool
uv run brightwheel-photos

# Run tests
uv run pytest

# Format code with black
uv run black brightwheel_photos tests

# Lint code
uv run pylint brightwheel_photos
```

### Poetry Alternative Commands
If using Poetry instead of uv:

```bash
poetry install
poetry run brightwheel-photos
poetry run pytest
poetry run black brightwheel_photos tests
poetry run pylint brightwheel_photos
```

## Architecture

### Core Components

1. **CLI Entry Point** (`brightwheel_photos/cli.py`):
   - Main entry point via `main()` function
   - Handles argument parsing and environment variable loading via python-dotenv
   - Manages authentication flow including 2FA support
   - Orchestrates the photo/video download process

2. **Authentication Flow**:
   - `trigger_2fa()`: Initiates 2FA if required by the account
   - `login()`: Completes authentication and sets up session with CSRF token
   - Sessions persist authentication state for subsequent API calls

3. **Data Retrieval**:
   - `find_students()`: Retrieves list of students associated with the guardian account
   - `find_activities()`: Generator that paginates through all activities for a student
   - Activities are saved as JSONL for debugging/archival purposes

4. **Media Processing**:
   - Photos: Downloaded and saved as JPEG with EXIF metadata (creation date, comments)
   - Videos: Downloaded as MP4 files (requires new session due to API quirk)
   - `build_exif_bytes()`: Constructs proper EXIF data including timestamps and activity notes

### API Integration

The tool interfaces with Brightwheel's private API at `schools.mybrightwheel.com`:
- Requires specific headers including X-Client-Name and X-Client-Version
- Uses CSRF tokens for authenticated requests
- Handles paginated responses for activity feeds

### Configuration

Credentials and settings can be provided via:
1. Environment variables in `.env` file (recommended)
2. Command-line arguments (override env vars)

Supported environment variables:
- `BRIGHTWHEEL_EMAIL`: Account email
- `BRIGHTWHEEL_PASSWORD`: Account password  
- `BRIGHTWHEEL_DIRECTORY`: Download directory
- `BRIGHTWHEEL_STUDENT_ID`: Optional specific student ID

### Dependencies

Key Python packages:
- `requests`: HTTP client for API interactions
- `Pillow` & `piexif`: Image processing and EXIF manipulation
- `python-dotenv`: Environment variable management
- `certifi`, `urllib3`: SSL/TLS certificate handling
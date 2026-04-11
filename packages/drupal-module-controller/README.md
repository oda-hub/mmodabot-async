# Drupal Module Controller

A FastAPI service for managing Drupal modules in the MMODA platform.

## Features

- REST API for creating and deleting Drupal modules
- Automatic module reinstallation for updates
- Background job processing with status tracking
- OpenAPI schema generation for API documentation

## Installation

```bash
pip install -e .
```

## Usage

### Running the Service

```bash
uvicorn mmoda_drupal_module_controller.main:app --reload
```

### API Endpoints

- `POST /modules` - Create/install a new module
- `DELETE /modules/{instr_name}` - Delete/uninstall a module
- `GET /jobs/{job_id}` - Check job status

### OpenAPI Schema Generation

Generate OpenAPI schema for CI/CD integration:

```bash
python scripts/generate_openapi_schema.py --output openapi.json
```

## Development

### Running Tests

```bash
pytest tests/
```

### Environment Variables

- `ODA_JWT_SECRET` - JWT secret for authentication

## License

MIT
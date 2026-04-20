# mmoda-kg-registrar

A knowledge graph registrar for the MMODA system. Provides a REST API to register, lookup, and manage workflow service metadata in an RDF knowledge graph with support for both local Turtle files and remote SPARQL endpoints.

## Installation

Install from this directory:

```bash
pip install .
```

## Usage

### Running the API server

```bash
mmoda-kg-registrar --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000` with interactive docs at `/docs`.

### Registering a workflow service

```bash
curl -X POST http://localhost:8000/register \
  -H 'Content-Type: application/json' \
  -d '{
    "project_repo": "https://github.com/user/myproject.git",
    "project_title": "My Project",
    "project_slug": "myproject",
    "last_activity_timestamp": "2026-04-01T10:00:00+00:00",
    "last_deployed_timestamp": "2026-04-01T10:00:00+00:00",
    "service_endpoint": "http://myproject-backend:8000",
    "deployment_name": "myproject-backend",
    "deployment_namespace": "default",
    "creative_work_status": "development"
  }'
```

### Looking up a service

```bash
curl -X GET "http://localhost:8000/lookup?repo=https://github.com/user/myproject.git"
```

### Unregistering a service

```bash
curl -X DELETE "http://localhost:8000/unregister?repo=https://github.com/user/myproject.git"
```

## API Endpoints

### POST /register

Register or update a workflow service record.

**Request body:**

```json
{
  "project_repo": "https://github.com/user/myproject.git",
  "project_title": "My Project",
  "project_slug": "myproject",
  "last_activity_timestamp": "2026-04-01T10:00:00+00:00",
  "last_deployed_timestamp": "2026-04-01T10:00:00+00:00",
  "service_endpoint": "http://myproject-backend:8000",
  "deployment_name": "myproject-backend",
  "deployment_namespace": "default",
  "creative_work_status": "development"
}
```

**Response (201 Created):**

```json
{
  "status": "ok",
  "project_repo": "https://github.com/user/myproject.git",
  "record": {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": "http://odahub.io/ontology#WorkflowService",
    "http://odahub.io/ontology#project_title": "My Project",
    "http://odahub.io/ontology#service_endpoint": "http://myproject-backend:8000",
    ...
  }
}
```

### GET /lookup

Retrieve a registered service by repository URL.

**Query parameters:**

- `repo` (required): URL of the project repository

**Response (200 OK):**

```json
{
  "project_repo": "https://github.com/user/myproject.git",
  "record": {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#type": "http://odahub.io/ontology#WorkflowService",
    ...
  }
}
```

**Response (404 Not Found):** Repository not registered

### DELETE /unregister

Remove a registered service.

**Query parameters:**

- `repo` (required): URL of the project repository

**Response (200 OK):**

```json
{
  "status": "ok",
  "project_repo": "https://github.com/user/myproject.git"
}
```

**Response (404 Not Found):** Repository not found

## Architecture

### Core Components

- **`KGClient`** (abstract): Interface for knowledge graph backends
- **`TurtleFileKGClient`**: Local file-based RDF storage (Turtle format)
- **`SparqlKGClient`**: Remote SPARQL endpoint support
- **`WorkflowServicePayload`**: Input validation schema
- **Response models**: `RegisterResponse`, `WorkflowServiceRecord`, `UnregisterResponse`

### Key Features

- No duplicate records per repository (upsert with subject deletion)
- Pluggable backends (local or SPARQL)
- Type-safe Pydantic models for requests/responses
- FastAPI with automatic OpenAPI documentation
- Support for ODA ontology (`http://odahub.io/ontology#`) and schema.org predicates

## Configuration

By default, the registrar uses a local Turtle file (`kg.ttl`) stored in the current working directory.

To use a SPARQL endpoint instead, modify `get_kg_client()` in `api.py`:

```python
def get_kg_client() -> KGClient:
    return SparqlKGClient(
        query_endpoint="http://sparql.example.com/query",
        update_endpoint="http://sparql.example.com/update"
    )
```

## License

MIT
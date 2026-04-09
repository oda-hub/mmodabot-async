import uvicorn
import argparse

parser = argparse.ArgumentParser(description="Run the API server")
parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on")
parser.add_argument("--port", type=int, default=8000, help="Port to run the server on")
parser.add_argument("--reload", action="store_true", help="Reload the server on code changes")

def run_api() -> None:
    args = parser.parse_args()
    uvicorn.run("mmoda_kg_registrar.api:app", host=args.host, port=args.port, reload=args.reload)


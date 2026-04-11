#!/usr/bin/env python3
"""
Generate OpenAPI schema from the FastAPI application.

This script can be used in CI/CD pipelines to automatically generate
API documentation from the FastAPI application.

Usage:
    python scripts/generate_openapi_schema.py [--output OUTPUT_FILE]

Arguments:
    --output OUTPUT_FILE: Path to output file (default: stdout)
"""

import argparse
import json
from mmoda_drupal_module_controller.main import app


def main():
    parser = argparse.ArgumentParser(description="Generate OpenAPI schema from FastAPI app")
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path (default: stdout)",
        default=None
    )
    parser.add_argument(
        "--indent",
        type=int,
        help="JSON indentation (default: 2)",
        default=2
    )

    args = parser.parse_args()

    # Generate OpenAPI schema
    schema = app.openapi()

    # Convert to JSON
    schema_json = json.dumps(schema, indent=args.indent, ensure_ascii=False)

    # Output to file or stdout
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(schema_json)
        print(f"OpenAPI schema written to {args.output}")
    else:
        print(schema_json)


if __name__ == "__main__":
    main()
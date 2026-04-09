"""mmoda_kg_registrar package."""

__version__ = "0.1.0"

from .api import app  # noqa: F401
from .graph import KGClient, TurtleFileKGClient, SparqlKGClient  # noqa: F401

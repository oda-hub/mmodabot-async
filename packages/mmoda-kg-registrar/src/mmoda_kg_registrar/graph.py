from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Mapping, Optional

import rdflib
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore


class KGClient(ABC):
    @abstractmethod
    def upsert_repository(self, project_repo: str, properties: Mapping[str, str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_repository(self, project_repo: str) -> Dict[str, str]:
        raise NotImplementedError

    @abstractmethod
    def delete_repository(self, project_repo: str) -> bool:
        raise NotImplementedError


class TurtleFileKGClient(KGClient):
    ODA = Namespace("http://odahub.io/ontology#")
    SCHEMA_CREATIVE_WORK_STATUS = URIRef("https://schema.org/creativeWorkStatus")

    def __init__(self, filepath: str, default_fn: str = "kg.ttl"):
        p = Path(filepath)
        if p.is_dir():
            p = p / default_fn
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)

        self.filepath = str(p)
        self.graph = Graph()
        self.graph.bind("oda", self.ODA)
        self._load_graph()

    def _load_graph(self) -> None:
        try:
            self.graph.parse(self.filepath, format="turtle")
        except Exception:
            # empty or invalid file can be ignored for startup
            pass

    def _save_graph(self) -> None:
        self.graph.serialize(destination=self.filepath, format="turtle")

    def _map_attrs(self, properties: Mapping[str, str]) -> Dict[str, URIRef]:
        return {
            "project_title": self.ODA.project_title,
            "last_activity_timestamp": self.ODA.last_activity_timestamp,
            "last_deployed_timestamp": self.ODA.last_deployed_timestamp,
            "service_name": self.ODA.service_name,
            "deployment_name": self.ODA.deployment_name,
            "deployment_namespace": self.ODA.deployment_namespace,
            "creative_work_status": self.SCHEMA_CREATIVE_WORK_STATUS,
        }

    def upsert_repository(self, project_repo: str, properties: Mapping[str, str]) -> None:
        subject = URIRef(project_repo)

        # remove existing triples for this repo
        self.graph.remove((subject, None, None))

        self.graph.add((subject, rdflib.RDF.type, self.ODA.WorkflowService))

        predicate_map = self._map_attrs(properties)
        for key, value in properties.items():
            if key in predicate_map and value is not None and value != "":
                self.graph.add((subject, predicate_map[key], Literal(value)))

        self._save_graph()

    def get_repository(self, project_repo: str) -> Dict[str, str]:
        subject = URIRef(project_repo)
        result: Dict[str, str] = {}
        for predicate, obj in self.graph.predicate_objects(subject=subject):
            result[str(predicate)] = str(obj)
        return result

    def delete_repository(self, project_repo: str) -> bool:
        subject = URIRef(project_repo)
        present = bool(self.graph.triples((subject, None, None)))
        self.graph.remove((subject, None, None))
        self._save_graph()
        return present


class SparqlKGClient(KGClient):
    ODA = Namespace("http://odahub.io/ontology#")
    SCHEMA_CREATIVE_WORK_STATUS = URIRef("https://schema.org/creativeWorkStatus")

    def __init__(self, query_endpoint: str, update_endpoint: Optional[str] = None, graph_uri: Optional[str] = None):
        self.store = SPARQLUpdateStore()
        self.store.open((query_endpoint, update_endpoint or query_endpoint))
        if graph_uri:
            self.graph = Graph(store=self.store, identifier=URIRef(graph_uri))
        else:
            self.graph = Graph(store=self.store)

    def upsert_repository(self, project_repo: str, properties: Mapping[str, str]) -> None:
        # SPARQL UPDATE path; delete existing triples for subject, then insert new
        delete_template = f"DELETE {{ <{project_repo}> ?p ?o }} WHERE {{ <{project_repo}> ?p ?o }}"
        self.graph.update(delete_template)

        inserts = [f"<{project_repo}> a <{self.ODA.WorkflowService}>"]
        predicate_map = {
            "project_title": self.ODA.project_title,
            "last_activity_timestamp": self.ODA.last_activity_timestamp,
            "last_deployed_timestamp": self.ODA.last_deployed_timestamp,
            "service_name": self.ODA.service_name,
            "deployment_name": self.ODA.deployment_name,
            "deployment_namespace": self.ODA.deployment_namespace,
            "creative_work_status": self.SCHEMA_CREATIVE_WORK_STATUS,
        }

        for key, value in properties.items():
            if key in predicate_map and value is not None and value != "":
                inserts.append(f"<{project_repo}> <{predicate_map[key]}> \"{value}\"")

        if inserts:
            query = "INSERT DATA { " + ". ".join(inserts) + " . }"
            self.graph.update(query)

    def get_repository(self, project_repo: str) -> Dict[str, str]:
        subject = URIRef(project_repo)
        return {str(pred): str(obj) for pred, obj in self.graph.predicate_objects(subject)}

    def delete_repository(self, project_repo: str) -> bool:
        existing = self.get_repository(project_repo)
        if not existing:
            return False
        delete_query = f"DELETE {{ <{project_repo}> ?p ?o }} WHERE {{ <{project_repo}> ?p ?o }}"
        self.graph.update(delete_query)
        return True

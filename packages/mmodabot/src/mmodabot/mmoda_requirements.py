# TODO: pretty hacky module, but needed for compatibility with the current way of defining external resources
# it requires nb2workflow (expanding the dependencies) and contains copy-pasted code from oda-api (to avoid even more heavy dependencies) 
# can we do all this in a cleaner, less convoluted way?
import logging
import os
import re
import tempfile
import yaml
import rdflib
from typing import TypedDict
from collections.abc import Generator
from contextlib import contextmanager,redirect_stderr,redirect_stdout

from nb2workflow.nbadapter import NotebookAdapter

from mmodabot.git_interface import GitServerInterface


logger = logging.getLogger()

class TypedResources(TypedDict):
    resource: str
    required: bool
    env_vars: set[str]


# https://stackoverflow.com/questions/11130156/suppress-stdout-stderr-print-from-python-functions
@contextmanager
def suppress_stdout_stderr():
    """A context manager that redirects stdout and stderr to devnull"""
    with open(os.devnull, 'w') as fnull:
        with redirect_stderr(fnull) as err, redirect_stdout(fnull) as out:
            yield (err, out)


@contextmanager
def temporary_log_level(level):
    logger = logging.getLogger()
    original_level = logger.level
    logger.setLevel(level)
    try:
        yield
    finally:
        logger.setLevel(original_level)


# yes, this is mostly copy-pasted from oda_api to avoid yet another heavy dependency
ontology_path = "https://odahub.io/ontology/ontology.ttl" # TODO: hardcoded

base_graph = rdflib.Graph()
base_graph = base_graph.parse(ontology_path)
base_graph.bind('oda', rdflib.Namespace("http://odahub.io/ontology#"))
base_graph.bind('odas', rdflib.Namespace("https://odahub.io/ontology#"))

def verify_base_class(graph, cls_uri, base_class_uri):
    if cls_uri == base_class_uri:
        return True
    for superclass in graph.objects(cls_uri, rdflib.RDFS.subClassOf):
        if superclass == base_class_uri:
            return True
        if verify_base_class(graph, superclass, base_class_uri):
            return True
    return False

def verify_object_base_class(graph, obj, class_uri):
    for objclass in graph.objects(obj, rdflib.RDF.type):
        if verify_base_class(graph, objclass, class_uri):
            return True
    return False

def get_requested_resources(graph, base_class_uri=None) -> Generator[TypedResources]:
    usesRequiredResource = rdflib.URIRef('http://odahub.io/ontology#usesRequiredResource')
    usesOptionalResource = rdflib.URIRef('http://odahub.io/ontology#usesOptionalResource')
    binding_env = rdflib.URIRef('http://odahub.io/ontology#resourceBindingEnvVarName')

    if base_class_uri is None:
        base_class_uri = rdflib.URIRef('http://odahub.io/ontology#Resource')

    def resources():
        for s, p, o in graph.triples((None, usesRequiredResource, None)):
            yield o, True
        for s, p, o in graph.triples((None, usesOptionalResource, None)):
            yield o, False

    g_combined = graph + base_graph

    for resource, required in resources():
        if base_class_uri and not verify_object_base_class(g_combined, resource, base_class_uri):
            continue
        env_vars = set()
        for s, p, o in graph.triples((resource, binding_env, None)):
            env_vars.add(str(o))
        yield TypedResources(resource=str(resource).split('#')[-1], required=required, env_vars=env_vars)

class RequirementsAnalyser:
    def __init__(self, git_interface: GitServerInterface):
        self.git_interface = git_interface # with project defined in it

    def external_resources(self, git_ref: str):
        with tempfile.TemporaryDirectory() as tmpd:
            repo_files = self.git_interface.list_repo_files(git_ref=git_ref, recursive=True)

            if 'mmoda.yaml' in [f['path'] for f in repo_files]:
                mmoda_config = self.git_interface.get_repo_file_content(path='mmoda.yaml', git_ref=git_ref)
                mmoda_config = yaml.safe_load(mmoda_config)
            else:
                mmoda_config = {}

            nb_path = mmoda_config.get('notebook_path', '')
            fn_pattern = mmoda_config.get('filename_pattern', r'(?P<fn>[^/]+\.ipynb)')
            pattern = re.compile(os.path.join(nb_path, fn_pattern))

            notebooks = []
            for f in repo_files:
                if m := pattern.match(f['path']):
                    with open(os.path.join(tmpd, m.group('fn')), 'wb') as fd:
                        fd.write(self.git_interface.get_repo_file_content(f['path'], git_ref=git_ref))
                    notebooks.append(os.path.join(tmpd, m.group('fn')))

            resources = {}

            for nb_file in notebooks:
                logger.info(f'Analysing notebook for requirements: {nb_file}')

                with suppress_stdout_stderr(), temporary_log_level(logging.ERROR):
                    nba = NotebookAdapter(nb_file)
                    
                g = nba._graph
                for r in get_requested_resources(g):
                    resource_name = r['resource'].lower()
                    if resource_name in resources:
                        resource_settings = resources[resource_name]
                        resource_settings['required'] = resource_settings['required'] or r['required']
                        resource_settings['env_vars'] = r['env_vars'].union(resource_settings['env_vars'])
                    else:
                        resources[resource_name] = r

            return resources


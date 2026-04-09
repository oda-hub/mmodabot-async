import pytest
from unittest.mock import MagicMock, patch
from rdflib import URIRef
from mmodabot.mmoda_requirements import (
    suppress_stdout_stderr, temporary_log_level,
    verify_base_class, verify_object_base_class, get_requested_resources
)


class TestMmodaRequirements:
    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_verify_base_class_same_uri(self, mock_graph):
        """Test verify_base_class when URIs are the same"""
        result = verify_base_class(mock_graph, "http://example.com/Class", "http://example.com/Class")

        assert result is True
        # Should not call objects when URIs are the same
        mock_graph.objects.assert_not_called()

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_verify_base_class_direct_subclass(self, mock_graph):
        """Test verify_base_class with direct subclass relationship"""
        mock_graph.objects.return_value = ["http://example.com/BaseClass"]

        result = verify_base_class(mock_graph, "http://example.com/SubClass", "http://example.com/BaseClass")

        assert result is True
        mock_graph.objects.assert_called_once()

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_verify_base_class_indirect_subclass(self, mock_graph):
        """Test verify_base_class with indirect subclass relationship"""
        # Mock recursive calls
        def mock_objects(subject, predicate):
            if subject == "http://example.com/MiddleClass":
                return ["http://example.com/BaseClass"]
            return ["http://example.com/MiddleClass"]

        mock_graph.objects.side_effect = mock_objects

        with patch('mmodabot.mmoda_requirements.verify_base_class') as mock_verify:
            mock_verify.return_value = True
            result = verify_base_class(mock_graph, "http://example.com/SubClass", "http://example.com/BaseClass")

            assert result is True

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_verify_base_class_no_relationship(self, mock_graph):
        """Test verify_base_class with no subclass relationship"""
        mock_graph.objects.return_value = []

        result = verify_base_class(mock_graph, "http://example.com/SubClass", "http://example.com/BaseClass")

        assert result is False

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_verify_object_base_class(self, mock_graph):
        """Test verify_object_base_class"""
        mock_graph.objects.return_value = ["http://example.com/MyClass"]

        with patch('mmodabot.mmoda_requirements.verify_base_class', return_value=True) as mock_verify:
            result = verify_object_base_class(mock_graph, "http://example.com/MyObject", "http://example.com/BaseClass")

            assert result is True
            mock_verify.assert_called_once_with(mock_graph, "http://example.com/MyClass", "http://example.com/BaseClass")

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_verify_object_base_class_no_match(self, mock_graph):
        """Test verify_object_base_class with no matching class"""
        mock_graph.objects.return_value = ["http://example.com/OtherClass"]

        with patch('mmodabot.mmoda_requirements.verify_base_class', return_value=False) as mock_verify:
            result = verify_object_base_class(mock_graph, "http://example.com/MyObject", "http://example.com/BaseClass")

            assert result is False

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_get_requested_resources(self, mock_graph):
        """Test get_requested_resources"""
        resource_uri = URIRef("http://example.com/Resource1")
        uses_required = URIRef('http://odahub.io/ontology#usesRequiredResource')
        binding_env = URIRef('http://odahub.io/ontology#resourceBindingEnvVarName')

        def mock_triples(pattern):
            if pattern == (None, uses_required, None):
                return [(None, None, resource_uri)]
            if pattern == (None, URIRef('http://odahub.io/ontology#usesOptionalResource'), None):
                return []
            if pattern == (resource_uri, binding_env, None):
                return [(None, None, "env_var1"), (None, None, "env_var2")]
            return []

        mock_graph.triples.side_effect = mock_triples

        with patch('mmodabot.mmoda_requirements.verify_object_base_class', return_value=True):
            resources = list(get_requested_resources(mock_graph, "http://example.com/BaseClass"))

        assert len(resources) == 1
        assert resources[0]["resource"] == "http://example.com/Resource1"
        assert resources[0]["required"] is True
        assert resources[0]["env_vars"] == {"env_var1", "env_var2"}

    @patch('mmodabot.mmoda_requirements.base_graph')
    def test_get_requested_resources_no_base_class(self, mock_graph):
        """Test get_requested_resources without base class filter"""
        resource_uri = URIRef("http://example.com/Resource1")
        uses_optional = URIRef('http://odahub.io/ontology#usesOptionalResource')
        binding_env = URIRef('http://odahub.io/ontology#resourceBindingEnvVarName')

        def mock_triples(pattern):
            if pattern == (None, URIRef('http://odahub.io/ontology#usesRequiredResource'), None):
                return []
            if pattern == (None, uses_optional, None):
                return [(None, None, resource_uri)]
            if pattern == (resource_uri, binding_env, None):
                return [(None, None, "env_var1")]
            return []

        mock_graph.triples.side_effect = mock_triples

        with patch('mmodabot.mmoda_requirements.verify_object_base_class', return_value=True):
            resources = list(get_requested_resources(mock_graph))

        assert len(resources) == 1
        assert resources[0]["required"] is False
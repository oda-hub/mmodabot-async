from unittest.mock import MagicMock
from mmodabot.notifier import CompositeNotificationHandler
import pytest

class TestCompositeNotificationHandler:
    def test_empty_handlers(self, mock_commit):
        """Test that CompositeNotificationHandler with no handlers does not raise errors"""
        composite = CompositeNotificationHandler([])
        # Should not raise any exceptions
        composite.on_build_started("repo", mock_commit, "tag")
        composite.on_build_completed("repo", mock_commit, "image", "tag")
        composite.on_build_failed("repo", mock_commit, "tag", {"error": "details"})
        composite.on_deployment_failed("repo", mock_commit , "tag", "error")
        # Should raise for unknown method
        with pytest.raises(AttributeError):
            composite.on_unknown_event("repo", mock_commit)
        # Should raise with correct method name but wrong signature
        with pytest.raises(TypeError):
            composite.on_build_started("repo", mock_commit)  # Missing image_tag
            
    def test_composite_handler_delegation(self, mock_commit):
        """Test that CompositeNotificationHandler delegates to all handlers"""
        handler1 = MagicMock()
        handler2 = MagicMock()
        composite = CompositeNotificationHandler([handler1, handler2])

        # Test delegation
        composite.on_build_started("repo", mock_commit, "tag")

        handler1.on_build_started.assert_called_once_with("repo", mock_commit, "tag")
        handler2.on_build_started.assert_called_once_with("repo", mock_commit, "tag")

    def test_composite_handler_multiple_calls(self, mock_commit):
        """Test multiple method calls on composite handler"""
        handler1 = MagicMock()
        handler2 = MagicMock()
        composite = CompositeNotificationHandler([handler1, handler2])

        composite.on_build_completed("repo", mock_commit, "image", "tag")
        composite.on_deployment_failed("repo", mock_commit , "tag", "error")

        # Check that both handlers received both calls
        handler1.on_build_completed.assert_called_once_with("repo", mock_commit, "image", "tag")
        handler2.on_build_completed.assert_called_once_with("repo", mock_commit, "image", "tag")
        handler1.on_deployment_failed.assert_called_once_with("repo", mock_commit, "tag", "error")
        handler2.on_deployment_failed.assert_called_once_with("repo", mock_commit, "tag", "error")
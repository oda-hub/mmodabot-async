import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mmodabot.registry_interface import tag_exists, _parse_www_authenticate, _get_bearer_token


class TestRegistryInterface:
    def test_parse_www_authenticate(self):
        """Test parsing WWW-Authenticate header"""
        header = 'Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/ubuntu:pull"'
        result = _parse_www_authenticate(header)

        expected = {
            "realm": "https://auth.docker.io/token",
            "service": "registry.docker.io",
            "scope": "repository:library/ubuntu:pull"
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_bearer_token(self):
        """Test getting bearer token from auth server"""
        params = {
            "realm": "https://auth.example.com/token",
            "service": "registry.example.com",
            "scope": "repository:test/repo:pull"
        }

        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"token": "test-token"})
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        token = await _get_bearer_token(params, "test/repo", mock_session)

        assert token == "test-token"
        mock_session.get.assert_called_once_with(
            "https://auth.example.com/token",
            params={"service": "registry.example.com", "scope": "repository:test/repo:pull"}
        )

    @pytest.mark.asyncio
    async def test_get_bearer_token_access_token(self):
        """Test getting bearer token with access_token field"""
        params = {
            "realm": "https://auth.example.com/token",
            "service": "registry.example.com"
        }

        mock_response = MagicMock()
        mock_response.json = AsyncMock(return_value={"access_token": "access-token-123"})
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_response

        token = await _get_bearer_token(params, "test/repo", mock_session)

        assert token == "access-token-123"

    @pytest.mark.asyncio
    async def test_tag_exists_true(self):
        """Test tag_exists returns True when tag exists"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession.head', return_value=mock_response):
            result = await tag_exists("registry.example.com", "test/repo", "v1.0.0")

            assert result is True

    @pytest.mark.asyncio
    async def test_tag_exists_false_404(self):
        """Test tag_exists returns False when tag doesn't exist (404)"""
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession.head', return_value=mock_response):
            result = await tag_exists("registry.example.com", "test/repo", "v1.0.0")

            assert result is False

    @pytest.mark.asyncio
    async def test_tag_exists_with_basic_auth(self):
        """Test tag_exists with username/password authentication"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession.head', return_value=mock_response):
            result = await tag_exists(
                "registry.example.com", "test/repo", "v1.0.0",
                username="testuser", password="testpass"
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_tag_exists_with_bearer_auth(self):
        """Test tag_exists with Bearer token authentication"""
        # First response: 401 with WWW-Authenticate header
        mock_response_401 = MagicMock()
        mock_response_401.status = 401
        mock_response_401.headers = {"WWW-Authenticate": 'Bearer realm="https://auth.example.com/token",service="registry.example.com"'}
        mock_response_401.raise_for_status = MagicMock()
        mock_response_401.__aenter__ = AsyncMock(return_value=mock_response_401)
        mock_response_401.__aexit__ = AsyncMock(return_value=None)

        # Second response: 200 OK
        mock_response_200 = MagicMock()
        mock_response_200.status = 200
        mock_response_200.raise_for_status = MagicMock()
        mock_response_200.__aenter__ = AsyncMock(return_value=mock_response_200)
        mock_response_200.__aexit__ = AsyncMock(return_value=None)

        # Mock token response
        mock_token_response = MagicMock()
        mock_token_response.json = AsyncMock(return_value={"token": "bearer-token"})
        mock_token_response.raise_for_status = MagicMock()
        mock_token_response.__aenter__ = AsyncMock(return_value=mock_token_response)
        mock_token_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession.head') as mock_head, \
             patch('aiohttp.ClientSession.get', return_value=mock_token_response):

            mock_head.side_effect = [mock_response_401, mock_response_200]

            result = await tag_exists("registry.example.com", "test/repo", "v1.0.0")

            assert result is True
            assert mock_head.call_count == 2  # First call gets 401, second gets 200

    @pytest.mark.asyncio
    async def test_tag_exists_exception_handling(self):
        """Test tag_exists propagates network errors"""
        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.raise_for_status.side_effect = Exception("Network error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch('aiohttp.ClientSession.head', return_value=mock_response):
            with pytest.raises(Exception, match="Network error"):
                await tag_exists("registry.example.com", "test/repo", "v1.0.0")

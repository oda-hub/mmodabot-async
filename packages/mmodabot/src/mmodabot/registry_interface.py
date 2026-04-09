import aiohttp
import re

MANIFEST_ACCEPT = ",".join([
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json"
])


def _parse_www_authenticate(header):
    """
    Parse WWW-Authenticate header for Bearer auth parameters
    """
    return dict(re.findall(r'(\w+)="(.*?)"', header))


async def _get_bearer_token(auth_params, repository, session):
    """
    Request Bearer token from registry auth server
    """
    realm = auth_params["realm"]
    service = auth_params.get("service")
    scope = f"repository:{repository}:pull"

    params = {"service": service, "scope": scope}

    async with session.get(realm, params=params) as r:
        r.raise_for_status()
        data = await r.json()
        return data.get("token") or data.get("access_token")


async def tag_exists(registry, repository, tag,
                     username=None, password=None, verify=True):
    """
    Check if image tag exists in container registry.
    """

    url = f"https://{registry}/v2/{repository}/manifests/{tag}"
    headers = {"Accept": MANIFEST_ACCEPT}

    token = None
    auth = None
    if username and password:
        auth = aiohttp.BasicAuth(username, password)

    connector = aiohttp.TCPConnector(ssl=verify)

    async with aiohttp.ClientSession(auth=auth, connector=connector) as session_tokenauth:

        async with session_tokenauth.head(url, headers=headers) as r:
            if r.status == 200:
                return True
            if r.status == 404:
                return False

            if r.status == 401 and "WWW-Authenticate" in r.headers:
                auth_header = r.headers["WWW-Authenticate"]

                if auth_header.lower().startswith("bearer"):
                    params = _parse_www_authenticate(auth_header)

                    token = await _get_bearer_token(params, repository, session_tokenauth)
                    headers["Authorization"] = f"Bearer {token}"

                    async with aiohttp.ClientSession(connector=connector) as session_tokenauth:
                        async with session_tokenauth.head(url, headers=headers, auth=None) as r2:
                            if r2.status == 200:
                                return True
                            if r2.status == 404:
                                return False
                            
                            r2.raise_for_status()
                            
            r.raise_for_status()

    
import json
import uuid
import subprocess as sp
import requests
from git import Git, GitCommandError

import os
import re
from typing import Any
from urllib.parse import urlsplit

from markdown import markdown
from markdown.postprocessors import Postprocessor
from markdown.extensions import Extension


def get_pypi_package_info(package_name: str) -> dict:
    url = f"https://pypi.org/pypi/{package_name}/json"
    resp = requests.get(url, timeout=10)

    if resp.status_code == 404:
        raise ValueError(f"Package '{package_name}' not found")

    resp.raise_for_status()
    return resp.json()

def _parse_git_spec(version_spec: str) -> tuple[str, str]:
    """Parse a git version spec into (url, ref)."""
    if not version_spec.startswith(("git+", "http")):
        return version_spec, ""

    git_url = version_spec[4:] if version_spec.startswith("git+") else version_spec

    if "@" in git_url:
        url, ref = git_url.rsplit("@", 1)
    else:
        url, ref = git_url, "HEAD"

    return url, ref

def resolve_git_reference(url: str, ref: str, token: str|None = None) -> str:
    try:
        g = Git()

        if token and url.startswith("https://"):
            url = url.replace("https://", f"https://oauth2:{token}@")

        remote_refs = g.ls_remote(url, ref)

        if not remote_refs.strip():
            raise RuntimeError(f"Reference '{ref}' not found in {url}")

        # ls-remote may return multiple matches (e.g., tag + deref)
        for line in remote_refs.splitlines():
            sha, ref_name = line.split("\t", 1)

            # Prefer exact matches
            if ref_name.endswith(f"/{ref}") or ref_name == ref:
                return sha

        # Fallback: return first match
        return remote_refs.splitlines()[0].split("\t")[0]

    except GitCommandError as e:
        raise RuntimeError(f"Git command failed for {url}@{ref}: {e}") from e
    except Exception as e:
        raise RuntimeError(f"Unexpected error resolving {url}@{ref}: {e}") from e

def get_unique_spec(version_spec: str):
    """
    Resolve a Git reference (branch, tag, or HEAD) to a commit SHA.
    Returns the resolved SHA or the original string if not a Git spec.
    """
    url, ref = _parse_git_spec(version_spec)

    if not ref:
        return url
    
    return resolve_git_reference(url, ref)


def split_registry_image_ref(image: str):
    if not image or not isinstance(image, str):
        raise ValueError("Invalid image reference")

    parts = image.split('/')

    # Single component image (e.g. "ubuntu")
    if len(parts) == 1:
        return "docker.io", parts[0]

    first = parts[0]

    if '.' in first or ':' in first or first == "localhost":
        return first, '/'.join(parts[1:])

    return "docker.io", '/'.join(parts[1:])

def get_registry_api_base(image: str) -> str:
    registry = split_registry_image_ref(image)[0]

    if registry == "docker.io":
        return "registry-1.docker.io"
    else:
        return f"{registry}"

def get_registry_auth_key(image: str) -> str:
    registry = split_registry_image_ref(image)[0]

    if registry == "docker.io":
        return "https://index.docker.io/v1/"
    else:
        return f"{registry}"

def repo_id(repo_url: str) -> str:
    # used to avoid name clashes in build jobs, deployments, as repo_url is too long for k8s resources, and slug may not be unique
    return uuid.uuid5(uuid.NAMESPACE_URL, repo_url).hex[:8]

def list_bot_helm_deployments(namespace: str) -> list[str]:
    res = sp.check_output(["helm", "-n", namespace, "list", "-l", "managed-by=mmodabot", "-o", "json"])
    return [x['name'] for x in json.loads(res)]

def gitlab_instance_url_from_full_url(url: str):
    return '/'.join(url.split("/")[:3]) # NOTE: fragile, doesn't allow subpath in gitlab instance url


# BEGIN: markdown helper
img_src_pattern = r'(?P<pref><img[^>]*\bsrc\s*=\s*["\'])(?P<url>.*?)(?P<suff>["\'][^>]*\/{0,1}>)'

def _parse_url(url):
    scheme, netloc, path, query, fragment = urlsplit(url)
    
    is_rel_path = True
    if scheme != '':
        is_rel_path = False
    elif url.startswith('//') or scheme == 'file':
        is_rel_path = False
    elif path == '' and netloc == '':
        # url fragment? can't be used as path
        is_rel_path = False
    
    return scheme, netloc, path, query, fragment, is_rel_path

def _append_url_base(m, url_base):
    link = m.group(0)
    
    scheme, netloc, path, query, fragment, is_relative = _parse_url(m.group('url'))
    
    if is_relative:
        base_spl = urlsplit(url_base)
        
        new_path = os.path.normpath(os.path.join(base_spl.path, path))
        
        new_url = base_spl._replace(path=new_path).geturl()
        
        link = f"{m.group('pref')}{new_url}{m.group('suff')}"
    
    return link
    

class ImgBasePostprocessor(Postprocessor):
    config: dict
    
    def run(self, text):
        
        url_base = self.config['url_base'] # pyright: ignore[reportAttributeAccessIssue]
        
        text = re.sub(img_src_pattern, lambda m: _append_url_base(m, url_base), text)
        
        return text
        
class ImgBase(Extension):
    def __init__(self, **kwargs: Any) -> None:
        self.config = {'url_base': ["", "Base to prepend to image pathes"]}
        super().__init__(**kwargs)
    
    def extendMarkdown(self, md):
        ibpp = ImgBasePostprocessor(md)
        ibpp.config = self.getConfigs()
        
        md.postprocessors.register(ibpp, 'imgbase', 2)
   

def convert_help(text_md, url_base=''):
    text_html = markdown(text_md, 
                         extensions=['attr_list', 'markdown_katex', 
                                     ImgBase(url_base=url_base)], 
                         extension_configs = {'markdown_katex': {'insert_fonts_css': True}})
    return text_html
# END: markdown helper
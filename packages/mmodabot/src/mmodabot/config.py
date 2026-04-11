from functools import cached_property
from importlib.resources import files
import hashlib
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, DirectoryPath, Field, HttpUrl, FilePath, AnyUrl
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, TomlConfigSettingsSource

import mmodabot.notifier as mmnt
from mmodabot.utils import get_pypi_package_info, get_unique_spec

class GroupConfig(BaseModel):
    url: HttpUrl
    gitlab_base: HttpUrl | None = None
    git_token_secret_name: str
    git_token_secret_key: str
    registry_secret_name: str | None = None
    target_image_base_tmpl: str

class RepoConfig(BaseModel):
    url: HttpUrl
    gitlab_base: HttpUrl | None = None
    git_token_secret_name: str
    git_token_secret_key: str
    registry_secret_name: str | None = None
    target_image_base: str

class MonitorConfig(BaseModel):
    triggering_topics: list[str] = ['mmoda-live-service']
    groups_poll_timeout: int = 300
    repo_poll_timeout: int = 60
    groups: list[GroupConfig] = Field(default_factory=list)
    repos: list[RepoConfig] = Field(default_factory=list)


class BuilderConfig(BaseModel):
    enabled: bool = True
    nb2w_version_spec: str = ""
    dockerfile_path: FilePath = cast(Path, files("mmodabot").joinpath("templates", "Dockerfile.builder"))
    job_tmpl_path: FilePath = cast(Path, files("mmodabot").joinpath("templates", "builder-job.yaml"))
    job_concurrency: int = 3
    job_queue_size: int = 100

    @cached_property
    def dockerfile_content(self) -> str:
        return self.dockerfile_path.read_text()

    @cached_property
    def job_tmpl(self) -> str:
        return self.job_tmpl_path.read_text()


class BackendDeployerConfig(BaseModel):
    enabled: bool = True
    mechanism: Literal['helm-cli'] = 'helm-cli'
    helm_chart: FilePath | DirectoryPath | AnyUrl = cast(Path, files("mmodabot").joinpath("templates", "mmoda-backend-chart"))
    values: dict[str, Any] = Field(default_factory=dict)
    timeout: str = "5m"


class RegistrarConfig(BaseModel):
    enabled: bool = False
    url: HttpUrl = HttpUrl('http://oda-dispatcher:8181')


class FrontendControllerConfig(BaseModel):
    enabled: bool = False
    url: HttpUrl = HttpUrl('http://frontend:8181')


class NotifierConfig(BaseModel):
    handler_name: str
    params: dict[str, str]


class Config(BaseSettings):
    namespace: str = "default"
    monitor: MonitorConfig = MonitorConfig()
    builder: BuilderConfig = BuilderConfig()
    backend_deployer: BackendDeployerConfig = BackendDeployerConfig()
    registrar: RegistrarConfig = RegistrarConfig()
    frontend_controller: FrontendControllerConfig = FrontendControllerConfig()
    notifiers: list[NotifierConfig] = Field(default_factory=list)

    model_config = {
        "env_prefix": "MMODABOT_",
        "env_nested_delimiter": "__"
    }

    def model_post_init(self, __context: Any) -> None:
        self._make_hash_base()

    def _make_hash_base(self):
        if self.builder.nb2w_version_spec:
            nb2w_version_hashable_bytes = get_unique_spec(self.builder.nb2w_version_spec).encode()
        else:
            # latest version in pypi
            pkgdata = get_pypi_package_info('nb2workflow')
            nb2w_version_hashable_bytes = pkgdata['info']['version'].encode()

        builder_dockerfile_bytes = self.builder.dockerfile_path.read_bytes()

        self._hash_base = hashlib.sha256()
        self._hash_base.update(builder_dockerfile_bytes)
        self._hash_base.update(nb2w_version_hashable_bytes)

    @property
    def composite_notifier(self):
        handlers = []
        for notifier in self.notifiers:
            handlers.append(mmnt.__dict__[notifier.handler_name](**notifier.params))
        return mmnt.CompositeNotificationHandler(handlers=handlers)

    @property
    def hash_base(self):
        return self._hash_base.copy()


    @classmethod
    def from_toml_file(cls, toml_path: Path | str) -> "Config":
        class SettingsFromFile(cls):
            @classmethod
            def settings_customise_sources(
                cls,
                settings_cls: type[BaseSettings],
                init_settings: PydanticBaseSettingsSource,
                env_settings: PydanticBaseSettingsSource,
                dotenv_settings: PydanticBaseSettingsSource,
                file_secret_settings: PydanticBaseSettingsSource,
            ):
                return (
                    TomlConfigSettingsSource(settings_cls, toml_file=toml_path),
                    init_settings,
                    env_settings,
                    dotenv_settings
                )

        return SettingsFromFile()            

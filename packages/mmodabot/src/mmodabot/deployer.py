import json
import logging
import os
import sys
import subprocess as sp
import tempfile
from mmodabot.git_interface import CommitType
import yaml
from mmodabot.status import DeploymentStatus
from mmodabot.config import Config
from mmodabot.k8s_interface import K8SInterface
from mmodabot.notifier import NotificationHandler


logger = logging.getLogger(__name__)


class HelmDeployer:
    def __init__(self,
                 project_slug: str,
                 repo_id: str,
                 repo_url: str,
                 target_image_base: str,
                 config: Config,
                 k8interface: K8SInterface,
                 image_pull_secret: str | None = None,
                 notifier: NotificationHandler | None = None):
        self.project_slug = project_slug
        self.repo_id = repo_id
        self.target_image_base = target_image_base
        self.config = config
        self.image_pull_secret = image_pull_secret
        self.k8interface = k8interface
        self.notifier = notifier
        self.repo_url = repo_url # only really used in notification

    def _release_name(self):
        return f"{self.project_slug}-{self.repo_id}"

    def _build_deployment_values(self, image_tag: str, commit_id: str, mmoda_external_resources: dict = {}):
        values: dict[str, object] = {
            "image": {"repository": self.target_image_base, "tag": image_tag},
            "appVersion": commit_id,
        }
        if self.image_pull_secret:
            values["imagePullSecrets"] = [{'name': self.image_pull_secret}]
        
        if mmoda_external_resources:
            values['extraEnv'] = []
            for name, resource in mmoda_external_resources:
                secret_name = f"{self.project_slug}-{self.repo_id}-{name}"
                secret_is_defined = self.k8interface.verify_secret(secret_name=secret_name)
                if resource["required"] and not secret_is_defined:
                    raise RuntimeError(f"Secret {secret_name} is required to deploy {self.target_image_base}")
                if secret_is_defined:
                    for env in resource['env_vars']:
                        values['extraEnv'].append({
                            'name': env,
                            'valueFrom': {
                                'secretKeyRef': {
                                    'name': secret_name,
                                    'key': 'credentials'
                                }
                            }
                        })

        # TODO: repo-specific config for: volumes (pvc or ephemeral), resource restrictions 
        return values

    def deploy(self, image_tag: str, commit: CommitType, mmoda_external_resources: dict = {}) -> DeploymentStatus:
        if self.config.backend_deployer.mechanism != "helm-cli":
            logger.error(f"Unsupported backend_deployer mechanism: {self.config.backend_deployer.mechanism}")
            raise NotImplementedError("Only helm cli deployment is implemented.")

        logger.info(f"Deploy called for {self.target_image_base}:{image_tag} on {self._release_name()}")
        release_name = self._release_name()

        with tempfile.TemporaryDirectory() as tmpd:
            extra_values_fn = os.path.join(tmpd, "extra-values.yaml")
            inj_values_fn = os.path.join(tmpd, "inj-values.yaml")

            with open(extra_values_fn, "w") as fd:
                extra_values = yaml.dump(self.config.backend_deployer.values)
                fd.write(extra_values)

            with open(inj_values_fn, "w") as fd:
                inj_values = yaml.dump(self._build_deployment_values(
                    image_tag, 
                    commit_id=commit.id, 
                    mmoda_external_resources=mmoda_external_resources))
                fd.write(inj_values)

            diff_args = [
                "helm",
                "-n", self.config.namespace,
                "diff",
                "upgrade",
                "--allow-unreleased",
                "--values", extra_values_fn,
                "--values", inj_values_fn,
                release_name,
                str(self.config.backend_deployer.helm_chart)
            ]

            diff = sp.check_output(diff_args)
            if not diff:
                logger.info(f"Helm release {self._release_name()} was not changed.")
                return DeploymentStatus.NOT_CHANGED
            
            if self.notifier is not None:
                self.notifier.on_deployment_started(repo_url=self.repo_url, commit=commit, image_tag=image_tag)
            args = [
                "helm",
                "-n", self.config.namespace,
                "upgrade",
                "--install",
                "-l", "managed-by=mmodabot",
                #"--rollback-on-failure", # manually for better reporting
                "--wait",
                f"--timeout={self.config.backend_deployer.timeout}",
                "--values", extra_values_fn,
                "--values", inj_values_fn,
                release_name,
                str(self.config.backend_deployer.helm_chart)
            ]

            res = sp.run(args, stderr=sys.stderr, stdout=sys.stdout)
            try:
                res.check_returncode()
            except sp.CalledProcessError as e:
                logger.error(f"Helm upgrade failed for {release_name}: {e}.")
                self.rollback() 
                return DeploymentStatus.FAILED
            
            return DeploymentStatus.SUCCEEDED
        
    def get_deployment_details(self):
        release_name = self._release_name()
        res = sp.run(["helm", "-n", self.config.namespace,"get", "manifest", release_name], stderr=sp.PIPE, stdout=sp.PIPE)

        res.check_returncode()

        return {"manifests": [x for x in yaml.safe_load_all(res.stdout.decode())]}

    def rollback(self) -> DeploymentStatus:
        release_name = self._release_name()
        logger.info(f"Attempting rollback for {release_name}")
        res = sp.check_output(["helm", "-n", self.config.namespace, "history", release_name, "-o", "json"])
        if len(json.loads(res)) == 1:
            logger.warning(f"Can't rollback the first release of {release_name}, uninstalling.")
            self.remove()

        res = sp.run(["helm", "-n", self.config.namespace, "rollback", release_name], stderr=sys.stderr, stdout=sys.stdout)
        if res.returncode != 0:
            logger.error(f"Rollback failed for {release_name}, returncode={res.returncode}")
            return DeploymentStatus.ROLLBACK_FAILED

        logger.info(f"Rollback completed for {release_name}")
        return DeploymentStatus.ROLLED_BACK

    def remove(self) -> None:
        release_name = self._release_name()
        res = sp.run(["helm", "-n", self.config.namespace, "uninstall", release_name], stderr=sp.PIPE, stdout=sys.stdout)
        res.check_returncode()


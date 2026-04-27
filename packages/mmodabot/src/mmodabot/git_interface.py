import logging
from typing import Any, Protocol, cast

import gitlab
from gitlab.v4.objects import ProjectCommit, ProjectCommitManager

class CommitProtocol(Protocol):
    id: str
    committed_date: str
    web_url: str
    manager: ProjectCommitManager
    short_id: str

type CommitType = CommitProtocol | ProjectCommit


logger = logging.getLogger()


def needs_project_preset(func):
    def wrapper(*args, **kwargs):
        self = args[0]
        if self.project is None:
            raise RuntimeError("Gitlab project is not set")
        return func(*args, **kwargs)
    return wrapper
    
    
class GitServerInterface:
    def __init__(self, instance: str | gitlab.Gitlab, kind='gitlab', token=None):
        if kind == 'gitlab':
            if hasattr(instance, 'projects') and hasattr(instance, 'url'):
                self.git = cast(gitlab.Gitlab, instance)
                instance_url = self.git.url
            else:
                instance_url = instance
                self.git = gitlab.Gitlab(instance_url, private_token=token)  # type: ignore[union-attr]

            logger.debug(f"Initializing Gitlab interface for instance {instance_url}")

            self.project = None
        else:
            raise NotImplementedError(f"Git provider '{kind}' is not supported yet.")

    def preset_project_by_repo_url(self, repo_url: str):
        project_name_with_ns = repo_url.replace(self.git.url, "").replace(".git", "").strip("/") 
        self.project = self.git.projects.get(project_name_with_ns)

    @needs_project_preset
    def get_latest_commit(self, git_ref='HEAD'):
        commits = self.project.commits.list(ref_name=git_ref, get_all=False) # pyright: ignore[reportOptionalMemberAccess]
        if commits:
            return commits[0]
        else:
            raise ValueError(f"No commits found for ref '{git_ref}' in repository '{self.project.http_url_to_repo}'.") # pyright: ignore[reportOptionalMemberAccess]

    @needs_project_preset
    def get_project_title(self):
        return self.project.name # pyright: ignore[reportOptionalMemberAccess]
    
    @needs_project_preset
    def get_project_slug(self):
        return self.project.path # pyright: ignore[reportOptionalMemberAccess]
    
    @needs_project_preset
    def get_commit_link(self, commit: CommitType):
        return commit.web_url
    
    @needs_project_preset
    def list_repo_files(self, git_ref: str, path: str | None = None, recursive=False) -> list[dict[str, Any]]:
        if path is not None:
            items = self.project.repository_tree(ref=git_ref, path=path, recursive=recursive, get_all=True) # pyright: ignore[reportOptionalMemberAccess]
        else:
            items = self.project.repository_tree(ref=git_ref, recursive=recursive, get_all=True) # pyright: ignore[reportOptionalMemberAccess]

        return items
    
    @needs_project_preset
    def get_repo_file_content(self, path:str, git_ref: str) -> bytes:
        return self.project.files.raw(file_path=path, ref=git_ref)  # pyright: ignore[reportOptionalMemberAccess]   

    @needs_project_preset
    def visibility_setting(self):
        return self.project.visibility   # pyright: ignore[reportOptionalMemberAccess]   
    
    @needs_project_preset
    def get_topics(self):
        return self.project.topics  # pyright: ignore[reportOptionalMemberAccess]   


    @classmethod
    def from_commit_object(cls, commit: CommitType):
        if isinstance(commit, ProjectCommit):
            gl = commit.manager.gitlab
            project = gl.projects.get(commit.project_id)
            repo_url = project.http_url_to_repo
            this = cls(instance=gl)
            this.preset_project_by_repo_url(repo_url)
            return this
        else:            
            raise NotImplementedError("Only ProjectCommit type is supported for now.")

    def list_group(self, group_link: str, get_all=False, iterator=True):
        group_path = group_link.replace(self.git.url, '').strip('/')
        group = self.git.groups.get(group_path)
        return group.projects.list(get_all=get_all, iterator=iterator)

    @staticmethod
    def set_commit_status(
        commit: CommitType,
        name: str,
        status: str,
        target_url: str | None = None,
        description: str | None = None,
    ):
        if isinstance(commit, ProjectCommit):
            commit.statuses.create({
                'state': status,
                'target_url': target_url,
                'name': name,
                'description': description
            })
        else:
            raise NotImplementedError("Only ProjectCommit type is supported for now.")
        


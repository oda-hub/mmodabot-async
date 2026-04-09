from enum import Enum


class BuildStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentStatus(Enum):
    STARTING = "starting"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    NOT_CHANGED = "not_changed"
    FAILED = "failed"
    ROLLBACK_FAILED = "rollback_failed"
    ROLLED_BACK = "rolled_back"


class RepoChangeStatus(Enum):
    WAITING_IMAGE = "waiting_image"
    NO_ACTION = "no_action"
    BUILDING = "building"
    DEPLOYED = "deployed"
    BUILD_FAILED = "build_failed"
    DEPLOY_FAILED = "deploy_failed"
    REGISTERED = "registered"
    REGISTER_FAILED = "register_failed"
    FRONTEND_UPDATED = "frontend_updated"
    FRONTEND_UPDATE_FAILED = "frontend_failed"
    CANCELLED = "cancelled"
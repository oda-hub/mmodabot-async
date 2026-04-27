import logging
import os
import sentry_sdk

from kubernetes import config as kube_config
from sentry_sdk.integrations.logging import LoggingIntegration

logging_level = logging.INFO
if os.environ.get('MMODABOT_DEBUG'):
    logging_level = logging.DEBUG

logging.basicConfig(
    level=logging_level, # TODO: configurable
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

sentry_dsn = os.environ.get('SENTRY_DSN')
if sentry_dsn is not None:
    os.environ['SENTRY_URL'] = sentry_dsn # this one is for nb2workflow

    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,
        enable_logs=True,
        integrations=[
            LoggingIntegration(
                sentry_logs_level=None,          # Don't send Sentry structured logs
                level=logging.INFO,              # Capture INFO and above as breadcrumbs
                event_level=logging.ERROR,       # Send ERROR records as events
            ),
        ],
        ignore_errors=[KeyboardInterrupt]
    )

try:
    kube_config.load_incluster_config()
except kube_config.config_exception.ConfigException:
    kube_config.load_kube_config()

"""Read-only Celery inspection command; performs no application jobs."""
from celery.worker.control import inspect_command
from photostore.build_info import read_build_info


@inspect_command()
def photostore_build_info(state, **kwargs):
    return read_build_info('worker')

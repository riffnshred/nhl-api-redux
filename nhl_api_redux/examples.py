"""
Access to the sample API payloads bundled with the package.

These are captured responses kept for offline development and tests. They are
read through importlib.resources so they resolve wherever the package is
installed, rather than relative to the caller's working directory.
"""

import json
from importlib import resources

PACKAGE_DATA = "nhl_api_redux.endpoint_exemples"


def load_exemple(name):
    """
    Load a bundled example payload by file name.

    Args:
        name: File name inside endpoint_exemples, e.g. "scores_exemple.json".

    Returns:
        The decoded JSON payload.
    """
    with resources.files(PACKAGE_DATA).joinpath(name).open("r", encoding="utf-8") as f:
        return json.load(f)

"""CoOps — Collaboration & Ops metrics for GitHub organizations.

A Medallion (Bronze → Silver → Gold) ETL pipeline that extracts GitHub
organization activity and turns it into analytics-ready data products.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: `version` in pyproject.toml.
    __version__ = version("coops")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"

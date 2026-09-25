"""
List of extracted repositories for the dashboard's repository selectors.
"""


from coops.utils.data_helpers import strip_metadata
from coops.utils.github_api import load_json_data, save_json_data

OUTPUT_FILE = "data/silver/available_repos.json"


def process_available_repos() -> list[str]:
    """Write data/silver/available_repos.json: a sorted JSON array of repository names.

    The file is always written (an empty array when nothing was extracted) and
    has no `_metadata` entry, because the dashboard reads it as a plain list.
    """
    repos = load_json_data("data/bronze/repositories_filtered.json") or []
    names = sorted(
        {repo["name"] for repo in strip_metadata(repos) if isinstance(repo, dict) and repo.get("name")},
        key=str.lower,
    )
    print(f"Available repositories: {len(names)}")
    return [save_json_data(names, OUTPUT_FILE, timestamp=False)]

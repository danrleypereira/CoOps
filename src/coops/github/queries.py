"""The GitHub queries extracted from ``coops.utils.github_api`` (#28).

Everything here knows *what to ask GitHub*: the REST URL templates and the
GraphQL documents. Nothing here knows *how to send it* — that is
:class:`coops.github.client.GitHubTransport` — or *what to do with the
answer*: the response shaping (pagination loops, the REST fallback's
circuit breaker, ``_standardize_tree_node``, ``_empty_tree_response``)
stayed with the callers in ``coops.utils.github_api``.

Two invariants kept the move behaviour-preserving:

* The GraphQL documents moved byte-for-byte, inner indentation and all.
  The transport hashes the whole query text into its cache key
  (``GitHubTransport._graphql_cache_key``), so an edit here — even pure
  whitespace — would orphan every cache entry and raw-layer document
  written before #28, and an offline replay (#199) would stop on its
  first miss. The odd-looking deep indentation inside the literals below
  is the original method-body indentation, preserved for that reason.
* Each URL builder returns the exact f-string template of its original,
  placeholder names included, so a rendered URL is indistinguishable from
  the one the inline literal produced. Query parameters a caller assembles
  per call (``?recursive=1``, ``per_page``/``page``, ``since``/``until``)
  stayed with the caller: they are request state, not endpoint knowledge.
"""

from __future__ import annotations

# -- REST URL templates --------------------------------------------

def repository_url(owner: str, repo: str) -> str:
    """The repository object: default branch, visibility, fork flag."""
    return f"https://api.github.com/repos/{owner}/{repo}"

def compare_url(owner: str, repo: str, default_branch: str, branch: str) -> str:
    """Compare ``branch`` against ``default_branch`` (ahead/behind counts)."""
    return f"https://api.github.com/repos/{owner}/{repo}/compare/{default_branch}...{branch}"

def commit_url(owner: str, repo: str, sha: str) -> str:
    """One commit with its stats — the REST commit-detail fetch."""
    return f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"

def commits_url(owner: str, repo: str) -> str:
    """The commit listing that the REST fallback of
    ``graphql_commit_history`` pages through."""
    return f"https://api.github.com/repos/{owner}/{repo}/commits"

def branch_url(owner: str, repo: str, branch: str) -> str:
    """The branch object — the commit SHA ``get_repository_tree`` walks from."""
    return f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"

def tree_url(owner: str, repo: str, tree_sha: str) -> str:
    """The git-tree listing for a SHA (the caller appends ``?recursive=1``)."""
    return f"https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_sha}"


# -- GraphQL documents ------------------------------------------------
#
# Moved byte-for-byte, inner indentation included: the transport hashes
# the whole query text into the cache key, so any edit — even whitespace
# — orphans every cache entry written before #28 (and stops an offline
# replay on its first miss).

ACTIVE_BRANCHES_QUERY = """
        query($owner: String!, $name: String!, $cursor: String) {
          repository(owner: $owner, name: $name) {
            refs(refPrefix: "refs/heads/", first: 100, after: $cursor, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
              pageInfo { hasNextPage endCursor }
              nodes {
                name
                target {
                  ... on Commit {
                    oid
                    committedDate
                  }
                }
              }
            }
          }
          rateLimit { remaining resetAt limit cost }
        }
        """

COMMIT_HISTORY_BRANCH_QUERY = """
                    query($owner: String!, $name: String!, $branch: String!, $pageSize: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp) {
                      repository(owner: $owner, name: $name) {
                        ref(qualifiedName: $branch) {
                          target {
                            ... on Commit {
                              history(first: $pageSize, after: $cursor, since: $since, until: $until) {
                                pageInfo { hasNextPage endCursor }
                                nodes {
                                  oid
                                  message
                                  messageHeadline
                                  committedDate
                                  author { name email user { login databaseId } }
                                  committer { name email date user { login databaseId } }
                                  additions
                                  deletions
                                  parents(first: 100) { nodes { oid } }
                                }
                              }
                            }
                          }
                        }
                      }
                      rateLimit { remaining resetAt limit cost }
                    }
                    """

COMMIT_HISTORY_DEFAULT_BRANCH_QUERY = """
                    query($owner: String!, $name: String!, $pageSize: Int!, $cursor: String, $since: GitTimestamp, $until: GitTimestamp) {
                      repository(owner: $owner, name: $name) {
                        defaultBranchRef {
                          name
                          target {
                            ... on Commit {
                              history(first: $pageSize, after: $cursor, since: $since, until: $until) {
                                pageInfo { hasNextPage endCursor }
                                nodes {
                                  oid
                                  message
                                  messageHeadline
                                  committedDate
                                  author { name email user { login databaseId } }
                                  committer { name email date user { login databaseId } }
                                  additions
                                  deletions
                                  parents(first: 100) { nodes { oid } }
                                }
                              }
                            }
                          }
                        }
                      }
                      rateLimit { remaining resetAt limit cost }
                    }
                    """

REPOSITORY_TREE_QUERY = """
                query($owner: String!, $repo: String!, $expression: String!) {
                  repository(owner: $owner, name: $repo) {
                    object(expression: $expression) {
                      ... on Tree {
                        entries {
                          name
                          type
                          mode
                          path
                          extension
                          object {
                            ... on Blob {
                              byteSize
                              isBinary
                              oid
                            }
                          }
                        }
                      }
                    }
                  }
                }
                """

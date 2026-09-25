"""The GitHub transport extracted from ``coops.utils.github_api`` (#27).

Everything here moves a request from process to wire and back: REST with
ETag revalidation and retry/backoff (``get_with_cache``), GraphQL
(``graphql``), pagination over list endpoints (``get_paginated``), the
URL-keyed body cache with its ETag sidecars, the MongoDB raw layer, the
raw-corpus capture (#109), the offline replay mode whose miss is
:class:`OfflineCacheMiss` (#199), and the run-summary accounting over all
of it. No GitHub *query* lives here — the query methods stayed in
``coops.utils.github_api`` and move behind this transport in #28.

:class:`GitHubAPIClient` (in ``coops.utils.github_api``) inherits this
class, so every existing import path keeps working; nothing outside the
two files knows the split exists.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlsplit

import requests

from coops.storage.raw import PROVIDER_GITHUB, is_fresh

if TYPE_CHECKING:
    # Import-time only: ``coops.utils``'s package init eagerly imports
    # ``github_api``, which inherits from this module — so a module-level
    # import of anything under coops.utils here is a cycle whenever this
    # module is the entry point. The runtime import lives in offline_fold.
    from coops.utils.cache_fold import CacheFold


class OfflineCacheMiss(RuntimeError):
    """Offline mode was asked for a URL that has no cached body.

    Offline mode exists to replay a run against a fixed cache (#199): every
    response must come from that cache, or the run must stop. A miss must not
    return ``None`` (the network-failure path) or fall through to an empty
    result — either would silently drop part of the corpus and report a
    plausible-looking partial answer. The message names the URL so the missing
    cache entry can be identified and produced.
    """

    def __init__(self, url: str):
        super().__init__(f"offline mode: no cached response for {url}")
        self.url = url

class GitHubTransport:
    """The transport half of the former :class:`GitHubAPIClient` (#27).

    Construction configures the transport only — token, cache, raw layer,
    capture, offline replay — and every method below is a moved, unedited
    member of that class. The query methods that used to share the class
    remain on ``GitHubAPIClient`` in ``coops.utils.github_api`` until #28.
    """

    def __init__(
        self,
        token: str,
        cache_dir: str = "cache",
        capture_dir: str | None = None,
        tenant_id: Any | None = None,
        provider: str = "github",
        raw_store: Any | None = None,
        raw_max_age_seconds: float | None = None,
        offline: bool = False,
    ):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        # GraphQL endpoint
        self.graphql_url = "https://api.github.com/graphql"
        # Managed raw-corpus capture (issue #109). Off unless capture_dir is
        # given; when it is, tenant_id is required because the capture shape
        # is tenant-scoped. See coops.raw_capture.capture.
        self.capture_dir = capture_dir
        self.tenant_id = tenant_id
        self.provider = provider
        self._capture = None
        if capture_dir is not None:
            if not tenant_id:
                raise ValueError("capture_dir requires a tenant_id")
            from coops.raw_capture.capture import RawCaptureWriter
            self._capture = RawCaptureWriter(capture_dir, tenant_id, provider)
        # Raw layer (MongoDB): a read-through/write-through cache in front of
        # the API. When configured, a fresh raw document short-circuits the
        # network so re-processing is free, and a successful fetch is captured
        # back into the raw layer. Both are best-effort: the raw layer is an
        # optimisation, so a down MongoDB must not break the extraction.
        self.raw_store = raw_store
        self.raw_max_age_seconds = raw_max_age_seconds
        # Offline mode (the #199 replay): when set, the cache is the only
        # source of responses. A cached body is served without revalidation
        # regardless of its ETag (a blocked network must not turn a warm,
        # revalidatable entry into `None`), and a cache miss raises
        # OfflineCacheMiss instead of falling through to a request that
        # cannot happen. Nothing is written: see get_with_cache.
        self.offline = offline
        # Content index over the cache (see coops.utils.cache_fold), built
        # lazily and only for offline runs. Online runs revalidate; a live
        # full listing is authoritative and complete on its own.
        self._cache_fold: CacheFold | None = None
        # Run-summary accounting: a "hit" is a request served from cache (a 304
        # or a short-circuited body) without consuming a rate-limit slot; a
        # "miss" is a billed network fetch (a 200) that populates the cache.
        self.cache_hits = 0
        self.cache_misses = 0
        # Most recent REST rate-limit window (remaining/limit/reset), if any.
        self.last_rate_limit: dict[str, Any] | None = None

    # -- Raw layer (MongoDB) ---------------------------------------------
    #
    # The raw layer is a read-through/write-through cache keyed by
    # (tenant, provider, endpoint, params_hash). Reads only short-circuit the
    # network when a document is fresh enough; the tenant scope is enforced by
    # the store, so the client just forwards the tenant it was given.

    @staticmethod
    def _split_url(url: str) -> tuple[str, dict[str, str]]:
        """Split a URL into (endpoint without query, query params as a dict)."""
        from urllib.parse import parse_qsl, urlsplit, urlunsplit

        parts = urlsplit(url)
        endpoint = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        return endpoint, params

    def _raw_read(self, provider: str, endpoint: str, params: dict[str, Any]) -> Any | None:
        """Return a fresh raw payload for the key, or None to fall through."""
        if self.raw_store is None or self.tenant_id is None:
            return None
        try:
            document = self.raw_store.get(self.tenant_id, provider, endpoint, params)
        except Exception:  # noqa: BLE001 — best-effort raw layer: a store failure falls through to the API
            # The raw layer is best-effort; a failure here must not stop the run.
            return None
        if document is None:
            return None
        if not is_fresh(document.fetched_at, self.raw_max_age_seconds):
            return None
        return document.payload

    def _raw_write(
        self,
        provider: str,
        endpoint: str,
        params: dict[str, Any],
        etag: str | None,
        payload: Any,
    ) -> None:
        """Capture a fetched payload into the raw layer (best-effort)."""
        if self.raw_store is None or self.tenant_id is None:
            return
        # The raw layer is a bonus, never the reason for the run: a store
        # failure here must not fail the extraction that produced the payload.
        with contextlib.suppress(Exception):
            self.raw_store.save(self.tenant_id, provider, endpoint, params, etag, payload)

    def _get_cache_key(self, key: str) -> str:
        """Create a stable cache key from an arbitrary string."""
        # Content-addressed cache filename, not a security hash; the digest
        # must stay md5 or every existing cache entry would miss.
        return hashlib.md5(key.encode(), usedforsecurity=False).hexdigest() + ".json"

    def _cache_get(self, cache_key: str) -> Any | None:
        """Get response from cache if exists"""
        cache_file = os.path.join(self.cache_dir, self._get_cache_key(cache_key))
        if os.path.exists(cache_file):
            with open(cache_file, encoding='utf-8') as f:
                return json.load(f)
        return None

    def _cache_set(self, cache_key: str, data: Any) -> None:
        """Save response to cache"""
        cache_file = os.path.join(self.cache_dir, self._get_cache_key(cache_key))
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # -- ETag sidecar ------------------------------------------------------
    #
    # The response body keeps its original format in ``<md5(url)>.json``; the
    # ``ETag`` header is stored verbatim in a sibling ``<md5(url)>.etag`` file.
    # A sidecar (rather than an envelope around the body) keeps the on-disk body
    # format untouched, so entries written before ETag support — and any other
    # reader of the JSON — keep working. A body with no sidecar simply has no
    # ETag, so the client falls back to serving it directly (the pre-ETag
    # behaviour) instead of sending a conditional request. GraphQL responses
    # have no ETag and never write a sidecar.

    def _get_etag_path(self, cache_key: str) -> str:
        """Path of the ETag sidecar file for a cache key."""
        return os.path.join(
            self.cache_dir,
            hashlib.md5(cache_key.encode(), usedforsecurity=False).hexdigest() + ".etag",
        )

    def _etag_get(self, cache_key: str) -> str | None:
        """Read the stored ETag for a cache key, or None if there is none."""
        etag_file = self._get_etag_path(cache_key)
        if not os.path.exists(etag_file):
            return None
        with open(etag_file, encoding='utf-8') as f:
            value = f.read().strip()
        return value or None

    def _etag_set(self, cache_key: str, etag: str) -> None:
        """Store the ETag for a cache key."""
        with open(self._get_etag_path(cache_key), 'w', encoding='utf-8') as f:
            f.write(etag)

    def _etag_delete(self, cache_key: str) -> None:
        """Remove the ETag sidecar for a cache key (best effort)."""
        etag_file = self._get_etag_path(cache_key)
        if os.path.exists(etag_file):
            os.remove(etag_file)

    # -- Content-indexed cache fold (#199) -----------------------------------
    #
    # The URL-keyed cache holds the same logical record under several URLs
    # (unconditional listings and ?since= watermarks), so reading one URL can
    # serve a months-old body while newer versions sit under keys nothing asks
    # for. In offline mode the extractors therefore also read the cache *by
    # content*: every cached response holding records for the repository and
    # family, unioned, newest version per record. See cache_fold.py.

    def offline_fold(self) -> CacheFold | None:
        """The content index over the cache, or None outside offline mode.

        Built once per client; the first family query scans the cache
        directory. Callers gate on ``offline`` themselves — extractors go
        through :func:`coops.utils.cache_fold.client_fold`, which is strict
        about the flag so a mocked client cannot trip the fold by accident.
        """
        if not self.offline:
            return None
        if self._cache_fold is None:
            # Deferred, not stylistic: importing coops.utils.* at module
            # level would make this module unimportable as an entry point
            # (see the TYPE_CHECKING note above). Paid once per client.
            from coops.utils.cache_fold import CacheFold

            self._cache_fold = CacheFold(self.cache_dir)
        return self._cache_fold

    # -- Run-summary accounting -------------------------------------------

    def _record_cache_hit(self) -> None:
        self.cache_hits += 1

    def _record_cache_miss(self) -> None:
        self.cache_misses += 1

    def _record_rate_limit(self, response: requests.Response) -> None:
        """Remember the most recent REST rate-limit window for the run summary."""
        remaining = response.headers.get('X-RateLimit-Remaining')
        if remaining is None:
            return
        # A malformed header (proxy, enterprise appliance) must not break the
        # fetch; the run summary then simply reports no rate-limit window.
        with contextlib.suppress(TypeError, ValueError):
            self.last_rate_limit = {
                'remaining': int(remaining),
                'limit': int(response.headers.get('X-RateLimit-Limit', '0') or 0),
                'reset': response.headers.get('X-RateLimit-Reset'),
            }

    # -- Raw-corpus capture (issue #109) -----------------------------------
    #
    # When capture is enabled (capture_dir + tenant_id), every REST and
    # GraphQL 200 is written as a {tenant_id, provider, endpoint, params,
    # etag, fetched_at, payload} record. The payload is unmodified and
    # contains personal data, so the writer keeps it mode 700/600 and the
    # result must never be published. Sanitization into the shareable
    # corpus-fixtures is done separately (coops.raw_capture.sanitize).

    @staticmethod
    def _split_url_path(url: str) -> tuple[str, dict[str, str]]:
        """Split a REST URL into its path (endpoint) and query params.

        Distinct from :meth:`_split_url`, which returns the full URL minus its
        query. The raw-corpus capture (#109) indexes on the path so that the
        same endpoint requested from different hosts collapses to one key,
        while the Mongo raw layer (#113) keys on the full URL.
        """
        parts = urlsplit(url)
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        return parts.path, params

    def _capture_rest(self, url: str, data: Any, etag: str | None) -> None:
        if self._capture is None:
            return
        endpoint, params = self._split_url_path(url)
        self._capture.write(endpoint, params, etag, data)

    def _capture_graphql(self, query: str, variables: dict[str, Any] | None, data: Any) -> None:
        if self._capture is None:
            return
        # GraphQL has no ETag; the query text and variables travel in params.
        self._capture.write(
            "graphql", {"query": query, "variables": variables or {}}, None, data
        )

    def get_with_cache(self, url: str, use_cache: bool = True, retries: int = 3, backoff_base: float = 1.0, return_headers: bool = False, silent: bool = False, log_prefix: str = "REST") -> Any:
        """Get data from GitHub API with caching, ETag revalidation, retries, and backoff.

        When a cached body has a stored ETag, the request is sent with
        ``If-None-Match``. A 304 then serves the cached body and does not
        consume a rate-limit slot; a 200 replaces the cached body (and its
        ETag). A cached body with no ETag (an entry written before ETag
        support, or a response that carried no ``ETag`` header) is served
        directly, without a conditional request.

        In offline mode (``offline=True``) the cache is the only source: a
        cached body is served directly — even one with an ETag, which online
        would revalidate — and a miss raises OfflineCacheMiss. ``use_cache``
        is deliberately not honoured here: offline is the strongest form of
        "use the cache", and the refresh ``use_cache=False`` asks for is
        impossible without a network. Nothing is read from or written to the
        network, so the cache-writing code below (reachable only after a
        successful response) is unreachable.
        """
        cached = None
        etag = None

        # Raw layer first: a fresh document short-circuits the API entirely, so
        # re-processing is free. The payload returned here is the *unmodified*
        # API body (it may carry personal data); the Bronze scrub runs later,
        # on the projection that is written to the public branch.
        if use_cache and self.raw_store is not None and self.tenant_id is not None:
            endpoint, params = self._split_url(url)
            raw_payload = self._raw_read(PROVIDER_GITHUB, endpoint, params)
            if raw_payload is not None:
                if not silent:
                    print(f"Using raw layer for: {url}")
                self._record_cache_hit()
                return raw_payload if not return_headers else (raw_payload, None)

        # Offline mode: the cache is the only source (the raw layer above, or
        # the file cache here). An ETag'd entry must NOT go to revalidation —
        # with the network blocked, the RequestException path below returns
        # None and the entry silently disappears from the replay (#199). A
        # miss raises so the run stops rather than producing a partial answer.
        if self.offline:
            cached = self._cache_get(url)
            if cached is None:
                raise OfflineCacheMiss(url)
            if not silent:
                print(f"Using cached data (offline) for: {url}")
            self._record_cache_hit()
            return cached if not return_headers else (cached, None)

        if use_cache:
            cached = self._cache_get(url)
            if cached is not None:
                etag = self._etag_get(url)

        # A warm body with no ETag cannot be revalidated: keep the pre-ETag
        # behaviour of serving it directly, with no network round-trip.
        if use_cache and cached is not None and etag is None:
            if not silent:
                print(f"Using cached data for: {url}")
            self._record_cache_hit()
            return cached if not return_headers else (cached, None)

        headers = dict(self.headers)
        if etag is not None:
            headers["If-None-Match"] = etag

        if not silent:
            if etag is not None:
                print(f"Revalidating with ETag for: {url}")
            else:
                print(f"Fetching from API: {url}")
        attempt = 0
        while attempt < retries:
            try:
                response = requests.get(url, headers=headers, timeout=35)

                if response.status_code == 200:
                    data = response.json()
                    self._capture_rest(url, data, response.headers.get("ETag"))
                    new_etag = response.headers.get("ETag")
                    if use_cache:
                        self._cache_set(url, data)
                        if new_etag:
                            self._etag_set(url, new_etag)
                        else:
                            self._etag_delete(url)
                    self._record_cache_miss()
                    self._record_rate_limit(response)
                    # Capture the unmodified body into the raw layer so the next
                    # run can read it instead of fetching again.
                    if use_cache and self.raw_store is not None and self.tenant_id is not None:
                        endpoint, params = self._split_url(url)
                        self._raw_write(PROVIDER_GITHUB, endpoint, params, new_etag, data)
                    if not return_headers and not silent:
                        self._log_rate_limit(response, prefix=log_prefix)
                    return data if not return_headers else (data, response.headers)
                if response.status_code == 304:
                    # Not Modified: the cached body is still current, and a 304
                    # does not count against the rate limit.
                    if not silent:
                        print(f"304 Not Modified - serving cached data for: {url}")
                    self._record_cache_hit()
                    self._record_rate_limit(response)
                    if not return_headers and not silent:
                        self._log_rate_limit(response, prefix=log_prefix)
                    return cached if not return_headers else (cached, response.headers)
                if response.status_code == 403:
                    print(f"[ERROR] API request forbidden (403) - might be private or rate limited: {response.text}")
                    if "rate limit" in response.text.lower():
                        print("Rate limit exceeded. Waiting 60 seconds...")
                        time.sleep(60)
                        # After sleep, continue loop to retry
                    else:
                        print("Access forbidden - resource might be private or require different permissions")
                        return None
                elif response.status_code == 404:
                    print(f"[ERROR] Resource not found (404): {url}")
                    return None
                elif 500 <= response.status_code < 600:
                    attempt += 1
                    wait = backoff_base * (2 ** (attempt - 1))
                    print(f"[WARN] API {response.status_code} - retrying in {wait:.1f}s (attempt {attempt}/{retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"[ERROR] API request failed: {response.status_code} - {response.text}")
                    return None
            except requests.exceptions.Timeout:
                attempt += 1
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"[ERROR] Request timeout for: {url} - retrying in {wait:.1f}s (attempt {attempt}/{retries})")
                time.sleep(wait)
                continue
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Request error for {url}: {e!s}")
                return None
        print(f"[ERROR] Exhausted retries for: {url}")
        return None

    # ----------------------
    # GraphQL support (API v4)
    # ----------------------
    def _graphql_cache_key(self, payload: dict[str, Any]) -> str | None:
        """Deterministic cache key for a GraphQL query + its variables."""
        try:
            return "graphql:" + hashlib.md5(
                (payload["query"] + "::" + json.dumps(payload["variables"], sort_keys=True, ensure_ascii=False)).encode("utf-8"),
                usedforsecurity=False,  # cache key, not a security hash
            ).hexdigest()
        except Exception:  # noqa: BLE001 — cache is optional: unserializable variables mean no cache, not an error
            # Unserializable variables: no cache key, so no cache.
            return None

    def graphql(self, query: str, variables: dict[str, Any] | None = None, use_cache: bool = True, timeout: int = 4) -> Any:
        """Execute a GraphQL query against GitHub's v4 API with simple timeout handling.

        In offline mode the cache is the only source, exactly as in
        get_with_cache: a cached response is served with no POST, and a miss
        raises OfflineCacheMiss naming the endpoint and the cache key. A mode
        that covered REST but not GraphQL would read as covered while
        silently dropping every commit-history page of a replay.
        """
        # Type-only declaration, added when this method moved under strict
        # mypy (#27): local annotations are not evaluated at runtime (PEP
        # 526), and without it the literal below joins its value types into
        # dict[str, Collection[str]], which requests' json= rejects.
        payload: dict[str, Any]
        payload = {"query": query, "variables": variables or {}}

        # Raw layer first: a fresh document short-circuits the API.
        if use_cache and self.raw_store is not None and self.tenant_id is not None:
            raw_params = {"query": query, "variables": variables or {}}
            raw_payload = self._raw_read(PROVIDER_GITHUB, self.graphql_url, raw_params)
            if raw_payload is not None:
                print("[GRAPHQL] Using raw layer response")
                self._record_cache_hit()
                return raw_payload

        # Offline mode: same guarantee as the REST path. GraphQL bodies carry
        # no ETag, so there is no revalidation to skip — what is skipped is
        # the POST itself, and a miss raises instead of returning None.
        if self.offline:
            cache_key = self._graphql_cache_key(payload)
            cached = self._cache_get(cache_key) if cache_key else None
            if cached is None:
                raise OfflineCacheMiss(f"{self.graphql_url} (cache key {cache_key})")
            print("[GRAPHQL] Using cached response (offline)")
            self._record_cache_hit()
            return cached

        # Build a deterministic cache key based on query + variables
        cache_key = None
        if use_cache:
            try:
                cache_key = self._graphql_cache_key(payload)
                if cache_key:
                    cached = self._cache_get(cache_key)
                    if cached is not None:
                        print("[GRAPHQL] Using cached response")
                        self._record_cache_hit()
                        return cached
            except Exception:  # noqa: BLE001 — cache is optional: a cache failure falls back to a live request
                # Fallback to no-cache if serialization fails
                cache_key = None

        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"

        try:
            response = requests.post(self.graphql_url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if "errors" in data:
                    # Check if errors are SERVICE_UNAVAILABLE (commit stats unavailable)
                    errors = data.get('errors', [])
                    has_stats_unavailable = any(
                        err.get('type') == 'SERVICE_UNAVAILABLE' and
                        ('additions' in str(err.get('path', [])) or 'deletions' in str(err.get('path', [])))
                        for err in errors
                    )

                    if has_stats_unavailable:
                        # Stats unavailable - treat as failure to trigger REST fallback
                        print("[GRAPHQL][WARN] Commit stats unavailable (SERVICE_UNAVAILABLE)")
                        return None  # Trigger REST fallback
                    # Other critical errors
                    print(f"[GRAPHQL][ERROR] Returned errors: {data['errors']}")
                    return None
                self._record_cache_miss()
                if use_cache and cache_key:
                    self._cache_set(cache_key, data)
                self._capture_graphql(query, variables, data)
                # Capture the unmodified body into the raw layer.
                if use_cache and self.raw_store is not None and self.tenant_id is not None:
                    self._raw_write(
                        PROVIDER_GITHUB,
                        self.graphql_url,
                        {"query": query, "variables": variables or {}},
                        None,
                        data,
                    )
                # Don't log rate limit for GraphQL - already logged after processing commits
                return data
            if response.status_code == 403:
                if "rate limit" in response.text.lower():
                    print("[GRAPHQL][WARN] Rate limit exceeded")
                else:
                    print("[GRAPHQL][ERROR] Forbidden (403)")
                return None
            if response.status_code == 502:
                print("[GRAPHQL][WARN] 502 (server overload)")
                return None
            if response.status_code in [500, 503]:
                print(f"[GRAPHQL][WARN] {response.status_code}")
                return None
            print(f"[GRAPHQL][ERROR] Request failed: {response.status_code}")
            return None
        except requests.exceptions.Timeout:
            print(f"[GRAPHQL][WARN] Timeout ({timeout}s)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[GRAPHQL][ERROR] Request error: {e!s}")
            return None

    def get_paginated(
        self,
        base_url: str,
        use_cache: bool = True,
        per_page: int = 50,
        start_page: int = 1,
        max_pages: int | None = None,
    ) -> list[Any]:
        """
        Fetch all pages for list endpoints that support per_page & page params.
        Stops when a page returns fewer than per_page results or when max_pages is reached.
        """
        results: list[Any] = []
        page = start_page
        while True:
            if max_pages is not None and page > max_pages:
                break
            sep = '&' if ('?' in base_url) else '?'
            url = f"{base_url}{sep}per_page={per_page}&page={page}"
            data = self.get_with_cache(url, use_cache)
            if data is None:
                if page > start_page:
                    print(f"[WARN] Stopped paginating {base_url} at page {page}: "
                          f"returning the {len(results)} items fetched so far")
                break
            if isinstance(data, list):
                results.extend(data)
                if len(data) < per_page:
                    break
            else:
                # Non-list response; stop paging
                break
            page += 1
        return results

    def _log_rate_limit(self, response: requests.Response, prefix: str = "REST") -> None:
        """Log rate limit information from response headers."""
        remaining = response.headers.get('X-RateLimit-Remaining', 'Unknown')
        limit = response.headers.get('X-RateLimit-Limit', 'Unknown')
        reset_time = response.headers.get('X-RateLimit-Reset', 'Unknown')

        if reset_time != 'Unknown':
            reset_datetime = datetime.fromtimestamp(int(reset_time), tz=timezone.utc)
            print(f"[{prefix}] Rate limit: {remaining}/{limit}, resets at {reset_datetime}")
        else:
            print(f"[{prefix}] Rate limit: {remaining}/{limit}")

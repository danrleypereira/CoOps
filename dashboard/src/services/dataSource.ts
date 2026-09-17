/**
 * Data Source Service
 *
 * Handles fetching data from local or remote GitHub sources
 */

// Use local data in development if VITE_USE_LOCAL_DATA is true
const USE_LOCAL_DATA = import.meta.env.VITE_USE_LOCAL_DATA === 'true';

// GitHub organization and repository from environment variables
const GITHUB_ORG = import.meta.env.VITE_GITHUB_ORG || 'DW-Corp';
const GITHUB_REPO = import.meta.env.VITE_GITHUB_REPO || 'CoOps';

// GitHub raw content URL for the data files
// This fetches directly from the main branch of the repository
const GITHUB_RAW_BASE_URL = `https://raw.githubusercontent.com/${GITHUB_ORG}/${GITHUB_REPO}/main/data`;

/**
 * Get the base URL for data fetching
 * - Local mode: /data (expects data in public/data during development)
 * - Remote mode: Fetches from GitHub raw content URL
 */
export function getDataBasePath(): string {
  if (USE_LOCAL_DATA) {
    return '/data';
  }
  return GITHUB_RAW_BASE_URL;
}

/**
 * Thrown by {@link fetchData} when a data file does not exist (HTTP 404).
 *
 * A missing file means the pipeline hasn't generated it yet (e.g. a fresh fork
 * or a first pipeline run still in progress), not a failure, so pages render an
 * explanatory empty state for it instead of an error. Network errors, other
 * HTTP statuses and invalid JSON keep throwing regular errors.
 */
export class DataNotFoundError extends Error {
  /** Path relative to the data directory, e.g. 'silver/temporal_events.json'. */
  readonly path: string;
  readonly url: string;

  constructor(path: string, url: string) {
    super(`Data file not found: ${url} (status: 404)`);
    this.name = 'DataNotFoundError';
    this.path = path;
    this.url = url;
  }
}

export function isDataNotFoundError(error: unknown): error is DataNotFoundError {
  return error instanceof DataNotFoundError;
}

/**
 * Fetch JSON data from the configured source
 * @throws {DataNotFoundError} when the file does not exist (HTTP 404)
 * @param path - Relative path to the JSON file (e.g., 'silver/members_analytics.json')
 */
export async function fetchData<T = any>(path: string): Promise<T> {
  const basePath = getDataBasePath();
  const url = `${basePath}/${path}`;

  try {
    const response = await fetch(url);
    if (response.status === 404) {
      throw new DataNotFoundError(path, url);
    }
    if (!response.ok) {
      // statusText is empty over HTTP/2 (e.g. raw.githubusercontent.com), so
      // always include the numeric status code.
      const statusText = response.statusText ? ` ${response.statusText}` : '';
      throw new Error(`Failed to fetch ${url} (status: ${response.status}${statusText})`);
    }
    return await response.json();
  } catch (error) {
    if (isDataNotFoundError(error)) {
      console.warn(`Data file not generated yet: ${url}`);
    } else {
      console.error(`Error fetching data from ${url}:`, error);
    }
    throw error;
  }
}

/**
 * Fetch the repository names listed in `silver/available_repos.json`
 * (a JSON array of strings written by the pipeline).
 *
 * Metadata entries and non-string values are ignored. Errors (including a
 * missing file) propagate to the caller.
 */
export async function fetchAvailableRepoNames(): Promise<string[]> {
  const data = await fetchData<unknown>('silver/available_repos.json');
  if (!Array.isArray(data)) return [];
  return filterMetadata(data).filter((name): name is string => typeof name === 'string');
}

/**
 * Filter out metadata entries (and null/undefined entries) from data arrays
 */
export function filterMetadata<T>(data: T[]): T[] {
  return data.filter((item: any) => item != null && !item._metadata);
}

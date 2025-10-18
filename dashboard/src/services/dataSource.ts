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
 * Fetch JSON data from the configured source
 * @param path - Relative path to the JSON file (e.g., 'silver/members_analytics.json')
 */
export async function fetchData<T = any>(path: string): Promise<T> {
  const basePath = getDataBasePath();
  const url = `${basePath}/${path}`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`Error fetching data from ${url}:`, error);
    throw error;
  }
}

/**
 * Filter out metadata from data arrays
 */
export function filterMetadata<T>(data: T[]): T[] {
  return data.filter((item: any) => !item._metadata);
}

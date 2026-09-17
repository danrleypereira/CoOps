import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import type { LanguageAnalysis } from './VisualizationUtils';

type UtilsModule = typeof import('./VisualizationUtils');

const repoA: LanguageAnalysis = {
  repository: 'repo-a',
  owner: 'org',
  branch: 'main',
  total_files: 3,
  total_bytes: 300,
  languages: [{ language: 'Python', file_count: 3, total_bytes: 300, percentage: 100 }],
};

const repoB: LanguageAnalysis = {
  repository: 'repo-b',
  owner: 'org',
  branch: 'dev',
  total_files: 1,
  total_bytes: 10,
  languages: [],
};

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

const fetchMock = vi.fn<(input: string) => Promise<Response>>();

// The class keeps a static cache, so load a fresh module for every test
async function loadUtils(): Promise<UtilsModule['VisualizationUtils']> {
  vi.resetModules();
  const mod: UtilsModule = await import('./VisualizationUtils');
  return mod.VisualizationUtils;
}

describe('VisualizationUtils', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('fetchAvailableRepos', () => {
    test('returns repository names, skipping metadata/invalid entries', async () => {
      fetchMock.mockResolvedValue(
        jsonResponse([
          { _metadata: { generated_at: 'now' } },
          { repository: 'no-langs' },
          { languages: [] },
          repoA,
          repoB,
        ])
      );
      const Utils = await loadUtils();
      await expect(Utils.fetchAvailableRepos()).resolves.toEqual(['repo-a', 'repo-b']);
      expect(fetchMock).toHaveBeenCalledWith(
        `${import.meta.env.BASE_URL}data/silver/language_analysis_all.json`
      );
    });

    test('uses the cache after the first successful load', async () => {
      fetchMock.mockResolvedValue(jsonResponse([repoA]));
      const Utils = await loadUtils();
      await Utils.fetchAvailableRepos();
      await Utils.fetchAvailableRepos();
      await Utils.fetchLanguageData('repo-a');
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    test('returns empty list when payload is not an array', async () => {
      fetchMock.mockResolvedValue(jsonResponse({ repository: 'repo-a', languages: [] }));
      const Utils = await loadUtils();
      await expect(Utils.fetchAvailableRepos()).resolves.toEqual([]);
    });

    test('returns empty list and logs on HTTP error, and retries on next call', async () => {
      fetchMock.mockResolvedValueOnce(jsonResponse(null, false, 500));
      fetchMock.mockResolvedValueOnce(jsonResponse([repoB]));
      const Utils = await loadUtils();
      await expect(Utils.fetchAvailableRepos()).resolves.toEqual([]);
      expect(console.error).toHaveBeenCalledWith(
        'Error loading language analysis data:',
        expect.objectContaining({ message: 'HTTP error! status: 500' })
      );
      expect(console.error).toHaveBeenCalledWith('Error fetching repositories:', expect.any(Error));
      // Cache was not marked loaded, so a second call fetches again
      await expect(Utils.fetchAvailableRepos()).resolves.toEqual(['repo-b']);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  describe('fetchLanguageData', () => {
    test('returns the analysis for a known repository', async () => {
      fetchMock.mockResolvedValue(jsonResponse([repoA, repoB]));
      const Utils = await loadUtils();
      await expect(Utils.fetchLanguageData('repo-b')).resolves.toEqual(repoB);
    });

    test('returns null and warns for an unknown repository', async () => {
      fetchMock.mockResolvedValue(jsonResponse([repoA]));
      const Utils = await loadUtils();
      await expect(Utils.fetchLanguageData('missing')).resolves.toBeNull();
      expect(console.warn).toHaveBeenCalledWith('Repository "missing" not found in cache');
    });

    test('returns null and logs when the fetch rejects', async () => {
      fetchMock.mockRejectedValue(new Error('offline'));
      const Utils = await loadUtils();
      await expect(Utils.fetchLanguageData('repo-a')).resolves.toBeNull();
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching language data for repo-a:',
        expect.objectContaining({ message: 'offline' })
      );
    });
  });

  describe('fetchTreeData', () => {
    test('fetches and returns tree JSON for a repository', async () => {
      const tree = { name: 'root', children: [] };
      fetchMock.mockResolvedValue(jsonResponse(tree));
      const Utils = await loadUtils();
      await expect(Utils.fetchTreeData('repo-a')).resolves.toEqual(tree);
      expect(fetchMock).toHaveBeenCalledWith(
        `${import.meta.env.BASE_URL}data/silver/repo_tree_pack_repo-a.json`
      );
    });

    test('returns null on non-ok response', async () => {
      fetchMock.mockResolvedValue(jsonResponse(null, false, 404));
      const Utils = await loadUtils();
      await expect(Utils.fetchTreeData('repo-x')).resolves.toBeNull();
      expect(console.error).toHaveBeenCalledWith(
        'Error fetching tree data for repo-x:',
        expect.objectContaining({ message: 'Failed to load tree data for repo-x' })
      );
    });

    test('returns null when fetch rejects', async () => {
      fetchMock.mockRejectedValue(new Error('dns'));
      const Utils = await loadUtils();
      await expect(Utils.fetchTreeData('repo-y')).resolves.toBeNull();
    });
  });

  describe('getLanguageColor', () => {
    test.each([
      ['JavaScript', '#f1e05a'],
      ['TypeScript', '#2b7489'],
      ['Python', '#3572A5'],
      ['C++', '#f34b7d'],
      ['C#', '#178600'],
      ['Svelte', '#ff3e00'],
    ])('returns known color for %s', async (lang, color) => {
      const Utils = await loadUtils();
      expect(Utils.getLanguageColor(lang)).toBe(color);
    });

    test('falls back to grey for unknown languages', async () => {
      const Utils = await loadUtils();
      expect(Utils.getLanguageColor('COBOL')).toBe('#8e8e8e');
      expect(Utils.getLanguageColor('')).toBe('#8e8e8e');
    });
  });

  describe('formatBytes', () => {
    test.each([
      [0, '0 Bytes'],
      [1, '1 Bytes'],
      [512, '512 Bytes'],
      [1024, '1 KB'],
      [1536, '1.5 KB'],
      [1234567, '1.18 MB'],
      [1024 ** 3, '1 GB'],
      [5.25 * 1024 ** 3, '5.25 GB'],
    ])('formats %d as %s', async (bytes, expected) => {
      const Utils = await loadUtils();
      expect(Utils.formatBytes(bytes)).toBe(expected);
    });
  });
});

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { Utils, ActivityData, ProcessedActivityResponse, ProcessedActivity, RepoActivitySummary } from './Utils';

// Mock the dataSource module
vi.mock('../services/dataSource', () => ({
  fetchData: vi.fn(),
  filterMetadata: vi.fn((data: any[]) => data.filter((item: any) => !item._metadata)),
}));

import { fetchData, filterMetadata } from '../services/dataSource';

describe('Utils Class', () => {
  const mockRawActivities: ActivityData[] = [
    {
      date: '2024-01-01T10:00:00Z',
      type: 'commit',
      repo: 'repo1',
      user: 'user1',
      additions: 100,
      deletions: 50,
      totalLines: 1000,
    },
    {
      date: '2024-01-01T11:00:00Z',
      type: 'commit',
      repo: 'repo1',
      user: 'user2',
      additions: 200,
      deletions: 30,
      totalLines: 1170,
    },
    {
      date: '2024-01-01T12:00:00Z',
      type: 'issue_created',
      repo: 'repo2',
      user: 'user1',
    },
    {
      date: '2024-01-02T10:00:00Z',
      type: 'pr_created',
      repo: 'repo1',
      user: 'user3',
      additions: 50,
      deletions: 10,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ========== PROCESSACTIVITYDATA ==========
  describe('processActivityData', () => {
    test('processes activities without type filter', () => {
      const result = Utils.processActivityData(mockRawActivities);

      expect(result.totalActivities).toBe(4);
      expect(result.repoCount).toBe(2);
      expect(result.repositories).toHaveLength(2);
    });

    test('filters by commit type', () => {
      const result = Utils.processActivityData(mockRawActivities, 'commit');

      expect(result.totalActivities).toBe(2);
      expect(result.repositories).toHaveLength(1);
      expect(result.repositories[0].name).toBe('repo1');
    });

    test('filters by issue type', () => {
      const result = Utils.processActivityData(mockRawActivities, 'issue');

      expect(result.totalActivities).toBe(1);
      expect(result.repositories[0].activities[0].type).toBe('issue_created');
    });

    test('filters by pull_request type', () => {
      const result = Utils.processActivityData(mockRawActivities, 'pull_request');

      expect(result.totalActivities).toBe(1);
      expect(result.repositories[0].activities[0].type).toBe('pr_created');
    });

    test('groups activities by repository', () => {
      const result = Utils.processActivityData(mockRawActivities);

      const repo1 = result.repositories.find((r) => r.name === 'repo1');
      expect(repo1?.activities).toHaveLength(3);

      const repo2 = result.repositories.find((r) => r.name === 'repo2');
      expect(repo2?.activities).toHaveLength(1);
    });

    test('assigns incremental IDs to repositories', () => {
      const result = Utils.processActivityData(mockRawActivities);

      expect(result.repositories[0].id).toBe(1);
      expect(result.repositories[1].id).toBe(2);
    });

    test('maps user data correctly', () => {
      const result = Utils.processActivityData(mockRawActivities);

      const activity = result.repositories[0].activities[0];
      expect(activity.user.login).toBe('user1');
      expect(activity.user.displayName).toBe('user1');
    });

    test('maps additions, deletions, totalLines', () => {
      const result = Utils.processActivityData(mockRawActivities);

      const activity = result.repositories[0].activities[0];
      expect(activity.additions).toBe(100);
      expect(activity.deletions).toBe(50);
      expect(activity.totalLines).toBe(1000);
    });

    test('ignores entries with _metadata', () => {
      const dataWithMetadata = [
        { _metadata: { version: '1.0' } } as any,
        ...mockRawActivities,
      ];

      const result = Utils.processActivityData(dataWithMetadata);

      expect(result.totalActivities).toBe(4);
    });

    test('ignores activities without repo', () => {
      const dataWithoutRepo = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          repo: '',
          user: 'user1',
        },
      ];

      const result = Utils.processActivityData(dataWithoutRepo);

      expect(result.totalActivities).toBe(0);
      expect(result.repoCount).toBe(0);
    });

    test('uses displayName as Unknown when user is empty', () => {
      const dataWithEmptyUser = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          repo: 'repo1',
          user: '',
        },
      ];

      const result = Utils.processActivityData(dataWithEmptyUser);

      expect(result.repositories[0].activities[0].user.displayName).toBe('Unknown');
    });

    test('generatedAt is in ISO format', () => {
      const result = Utils.processActivityData(mockRawActivities);

      expect(() => new Date(result.generatedAt)).not.toThrow();
      expect(result.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    });

    test('processes empty array', () => {
      const result = Utils.processActivityData([]);

      expect(result.totalActivities).toBe(0);
      expect(result.repoCount).toBe(0);
      expect(result.repositories).toEqual([]);
    });

    test('filters by unmapped specific type', () => {
      const dataWithCustomType = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'custom_event',
          repo: 'repo1',
          user: 'user1',
        },
      ];

      const result = Utils.processActivityData(dataWithCustomType, 'custom_event');

      expect(result.totalActivities).toBe(1);
    });
  });

  // ========== FETCHANDPROCESSACTIVITYDATA ==========
  describe('fetchAndProcessActivityData', () => {
    test('fetches data via fetchData service', async () => {
      vi.mocked(fetchData).mockResolvedValue(mockRawActivities);

      await Utils.fetchAndProcessActivityData();

      expect(fetchData).toHaveBeenCalledWith('silver/temporal_events.json');
    });

    test('returns processed data', async () => {
      vi.mocked(fetchData).mockResolvedValue(mockRawActivities);

      const result = await Utils.fetchAndProcessActivityData();

      expect(result.totalActivities).toBe(4);
      expect(result.repoCount).toBe(2);
    });

    test('passes type filter to processActivityData', async () => {
      vi.mocked(fetchData).mockResolvedValue(mockRawActivities);

      const result = await Utils.fetchAndProcessActivityData('commit');

      expect(result.totalActivities).toBe(2);
    });

    test('throws error when fetchData fails', async () => {
      vi.mocked(fetchData).mockRejectedValue(new Error('Failed to fetch data: 404 Not Found'));

      await expect(Utils.fetchAndProcessActivityData()).rejects.toThrow(
        'Failed to fetch data: 404 Not Found'
      );
    });

    test('throws error with status 500', async () => {
      vi.mocked(fetchData).mockRejectedValue(new Error('Failed to fetch data: 500 Internal Server Error'));

      await expect(Utils.fetchAndProcessActivityData()).rejects.toThrow('500');
    });

    test('throws error when JSON parsing fails', async () => {
      vi.mocked(fetchData).mockRejectedValue(new Error('JSON parse error'));

      await expect(Utils.fetchAndProcessActivityData()).rejects.toThrow('JSON parse error');
    });

    test('throws error when fetchData is rejected', async () => {
      vi.mocked(fetchData).mockRejectedValue(new Error('Network error'));

      await expect(Utils.fetchAndProcessActivityData()).rejects.toThrow('Network error');
    });
  });

  // ========== AGGREGATEBASICDATA ==========
  describe('aggregateBasicData', () => {
    const mockProcessedActivities: ProcessedActivity[] = [
      {
        date: '2024-01-01T10:00:00Z',
        type: 'commit',
        user: { login: 'user1', displayName: 'User One' },
        additions: 100,
        deletions: 50,
      },
      {
        date: '2024-01-01T11:00:00Z',
        type: 'commit',
        user: { login: 'user2', displayName: 'User Two' },
        additions: 200,
        deletions: 30,
      },
      {
        date: '2024-01-02T10:00:00Z',
        type: 'commit',
        user: { login: 'user1', displayName: 'User One' },
        additions: 50,
        deletions: 10,
      },
    ];

    test('groups by day by default', () => {
      const result = Utils.aggregateBasicData(mockProcessedActivities);

      expect(result).toHaveLength(2);
      expect(result[0].date).toBe('2024-01-01');
      expect(result[1].date).toBe('2024-01-02');
    });

    test('groups by hour when groupByHour is true', () => {
      const result = Utils.aggregateBasicData(mockProcessedActivities, { groupByHour: true });

      expect(result).toHaveLength(3);
      expect(result[0].date).toMatch(/T10:00:00/);
      expect(result[1].date).toMatch(/T11:00:00/);
    });

    test('counts commits correctly', () => {
      const result = Utils.aggregateBasicData(mockProcessedActivities);

      expect(result[0].value).toBe(2); // 2 commits on day 01
      expect(result[1].value).toBe(1); // 1 commit on day 02
    });

    test('sums additions correctly', () => {
      const result = Utils.aggregateBasicData(mockProcessedActivities);

      expect(result[0].additions).toBe(300); // 100 + 200
      expect(result[1].additions).toBe(50);
    });

    test('sums deletions correctly', () => {
      const result = Utils.aggregateBasicData(mockProcessedActivities);

      expect(result[0].deletions).toBe(80); // 50 + 30
      expect(result[1].deletions).toBe(10);
    });

    test('calculates cumulative totalLines', () => {
      const result = Utils.aggregateBasicData(mockProcessedActivities);

      expect(result[0].totalLines).toBe(220); // 300 - 80
      expect(result[1].totalLines).toBe(260); // 220 + (50 - 10)
    });

    test('totalLines is never negative', () => {
      const activitiesWithMoreDeletions: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
          additions: 10,
          deletions: 100,
        },
      ];

      const result = Utils.aggregateBasicData(activitiesWithMoreDeletions);

      expect(result[0].totalLines).toBe(0);
    });

    test('applies cutoffDate filter', () => {
      const cutoff = new Date('2024-01-02T00:00:00Z');
      const result = Utils.aggregateBasicData(mockProcessedActivities, { cutoffDate: cutoff });

      expect(result).toHaveLength(1);
      expect(result[0].date).toBe('2024-01-02');
    });

    test('uses 0 for additions when undefined', () => {
      const activitiesWithoutAdditions: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
        },
      ];

      const result = Utils.aggregateBasicData(activitiesWithoutAdditions);

      expect(result[0].additions).toBe(0);
    });

    test('uses 0 for deletions when undefined', () => {
      const activitiesWithoutDeletions: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
        },
      ];

      const result = Utils.aggregateBasicData(activitiesWithoutDeletions);

      expect(result[0].deletions).toBe(0);
    });

    test('sorts results by date', () => {
      const unsortedActivities: ProcessedActivity[] = [
        {
          date: '2024-01-03T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
        },
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
        },
        {
          date: '2024-01-02T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
        },
      ];

      const result = Utils.aggregateBasicData(unsortedActivities);

      expect(result[0].date).toBe('2024-01-01');
      expect(result[1].date).toBe('2024-01-02');
      expect(result[2].date).toBe('2024-01-03');
    });

    test('processes empty array', () => {
      const result = Utils.aggregateBasicData([]);

      expect(result).toEqual([]);
    });

    test('groups multiple commits in the same hour', () => {
      const sameHourActivities: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:30:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
          additions: 50,
        },
        {
          date: '2024-01-01T10:45:00Z',
          type: 'commit',
          user: { login: 'user2', displayName: 'User Two' },
          additions: 30,
        },
      ];

      const result = Utils.aggregateBasicData(sameHourActivities, { groupByHour: true });

      expect(result).toHaveLength(1);
      expect(result[0].value).toBe(2);
      expect(result[0].additions).toBe(80);
    });
  });

  // ========== AGGREGATEPIEDATA ==========
  describe('aggregatePieData', () => {
    const mockPieActivities: ProcessedActivity[] = [
      {
        date: '2024-01-01T10:00:00Z',
        type: 'commit',
        user: { login: 'user1', displayName: 'Alice' },
      },
      {
        date: '2024-01-01T11:00:00Z',
        type: 'commit',
        user: { login: 'user1', displayName: 'Alice' },
      },
      {
        date: '2024-01-01T12:00:00Z',
        type: 'commit',
        user: { login: 'user2', displayName: 'Bob' },
      },
      {
        date: '2024-01-02T10:00:00Z',
        type: 'commit',
        user: { login: 'user3', displayName: 'Charlie' },
      },
    ];

    test('counts commits per contributor', () => {
      const result = Utils.aggregatePieData(mockPieActivities);

      const alice = result.find((d) => d.label === 'Alice');
      const bob = result.find((d) => d.label === 'Bob');

      expect(alice?.value).toBe(2);
      expect(bob?.value).toBe(1);
    });

    test('sorts contributors by count', () => {
      const result = Utils.aggregatePieData(mockPieActivities);

      expect(result[0].label).toBe('Alice'); // 2 commits
      expect(result[1].label).toBe('Bob'); // 1 commit or Charlie
    });

    test('limits to topN contributors', () => {
      const manyContributors: ProcessedActivity[] = Array.from({ length: 20 }, (_, i) => ({
        date: '2024-01-01T10:00:00Z',
        type: 'commit',
        user: { login: `user${i}`, displayName: `User ${i}` },
      }));

      const result = Utils.aggregatePieData(manyContributors, {}, 5);

      expect(result.length).toBeLessThanOrEqual(6); // 5 top + Others
    });

    test('groups remaining contributors into "Others"', () => {
      const manyContributors: ProcessedActivity[] = [
        ...Array.from({ length: 10 }, (_, i) => ({
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: `user${i}`, displayName: `User ${i}` },
        })),
      ];

      const result = Utils.aggregatePieData(manyContributors, {}, 5);

      const others = result.find((d) => d.label === 'Others');
      expect(others).toBeDefined();
      expect(others?.value).toBe(5); // 10 total - 5 top
    });

    test('does not include "Others" when all fit in topN', () => {
      const result = Utils.aggregatePieData(mockPieActivities, {}, 10);

      const others = result.find((d) => d.label === 'Others');
      expect(others).toBeUndefined();
    });

    test('assigns colors using d3-scale', () => {
      const result = Utils.aggregatePieData(mockPieActivities);

      result.forEach((datum) => {
        expect(datum.color).toBeDefined();
        expect(typeof datum.color).toBe('string');
        expect(datum.color).toMatch(/^#[0-9a-f]{6}$/i);
      });
    });

    test('applies cutoffDate for Last 24 hours', () => {
      const cutoff = new Date('2024-01-02T00:00:00Z');
      const result = Utils.aggregatePieData(mockPieActivities, {
        cutoffDate: cutoff,
        selectedTime: 'Last 24 hours',
      });

      expect(result).toHaveLength(1);
      expect(result[0].label).toBe('Charlie');
    });

    test('applies cutoffDate for other time periods', () => {
      const cutoff = new Date('2024-01-02T00:00:00Z');
      const result = Utils.aggregatePieData(mockPieActivities, {
        cutoffDate: cutoff,
        selectedTime: 'Last 7 days',
      });

      expect(result).toHaveLength(1);
      expect(result[0].label).toBe('Charlie');
    });

    test('uses displayName when available', () => {
      const result = Utils.aggregatePieData(mockPieActivities);

      expect(result[0].label).toBe('Alice');
    });

    test('uses login when displayName is empty', () => {
      const activitiesWithoutDisplay: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: '' },
        },
      ];

      const result = Utils.aggregatePieData(activitiesWithoutDisplay);

      expect(result[0].label).toBe('user1');
    });

    test('uses "Unknown" when both login and displayName are empty', () => {
      const activitiesWithoutUser: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: '', displayName: '' },
        },
      ];

      const result = Utils.aggregatePieData(activitiesWithoutUser);

      expect(result[0].label).toBe('Unknown');
    });

    test('processes empty array', () => {
      const result = Utils.aggregatePieData([]);

      expect(result).toEqual([]);
    });
  });

  // ========== APPLYFILTERS ==========
  describe('applyFilters', () => {
    const mockFilterActivities: ProcessedActivity[] = [
      {
        date: '2024-01-01T10:00:00Z',
        type: 'commit',
        user: { login: 'alice', displayName: 'Alice' },
      },
      {
        date: '2024-01-02T10:00:00Z',
        type: 'commit',
        user: { login: 'bob', displayName: 'Bob' },
      },
      {
        date: '2024-01-03T10:00:00Z',
        type: 'commit',
        user: { login: 'charlie', displayName: 'Charlie' },
      },
    ];

    test('filters by single member', () => {
      const result = Utils.applyFilters(mockFilterActivities, ['Alice'], 'All Time');

      expect(result).toHaveLength(1);
      expect(result[0].user.displayName).toBe('Alice');
    });

    test('filters by multiple members', () => {
      const result = Utils.applyFilters(mockFilterActivities, ['Alice', 'Bob'], 'All Time');

      expect(result).toHaveLength(2);
    });

    test('does not filter when selectedMembers is empty', () => {
      const result = Utils.applyFilters(mockFilterActivities, [], 'All Time');

      expect(result).toHaveLength(3);
    });

    test('filters by Last 24 hours', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-01-03T12:00:00Z'));

      const result = Utils.applyFilters(mockFilterActivities, [], 'Last 24 hours');

      expect(result).toHaveLength(1);
      expect(result[0].user.displayName).toBe('Charlie');

      vi.useRealTimers();
    });

    test('filters by Last 6 months', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-07-01T10:00:00Z'));

      const result = Utils.applyFilters(mockFilterActivities, [], 'Last 6 months');

      expect(result).toHaveLength(3);

      vi.useRealTimers();
    });

    test('filters by Last Year', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2025-01-01T10:00:00Z'));

      const result = Utils.applyFilters(mockFilterActivities, [], 'Last Year');

      expect(result).toHaveLength(3);

      vi.useRealTimers();
    });

    test('does not filter when selectedTime is All Time', () => {
      const result = Utils.applyFilters(mockFilterActivities, [], 'All Time');

      expect(result).toHaveLength(3);
    });

    test('applies member and time filters simultaneously', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-01-03T12:00:00Z'));

      const result = Utils.applyFilters(mockFilterActivities, ['Charlie'], 'Last 24 hours');

      expect(result).toHaveLength(1);
      expect(result[0].user.displayName).toBe('Charlie');

      vi.useRealTimers();
    });

    test('uses login when displayName is empty', () => {
      const activitiesWithLogin: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'alice', displayName: '' },
        },
      ];

      const result = Utils.applyFilters(activitiesWithLogin, ['alice'], 'All Time');

      expect(result).toHaveLength(1);
    });

    test('uses "Unknown" when both login and displayName are empty', () => {
      const activitiesWithoutUser: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: '', displayName: '' },
        },
      ];

      const result = Utils.applyFilters(activitiesWithoutUser, ['Unknown'], 'All Time');

      expect(result).toHaveLength(1);
    });
  });

  // ========== SELECTREPOANDFILTER ==========
  describe('selectRepoAndFilter', () => {
    const mockRepositories: RepoActivitySummary[] = [
      {
        id: 1,
        name: 'repo1',
        activities: [
          {
            date: '2024-01-01T10:00:00Z',
            type: 'commit',
            user: { login: 'alice', displayName: 'Alice' },
          },
          {
            date: '2024-01-01T11:00:00Z',
            type: 'commit',
            user: { login: 'bob', displayName: 'Bob' },
          },
        ],
      },
      {
        id: 2,
        name: 'repo2',
        activities: [
          {
            date: '2024-01-01T10:00:00Z',
            type: 'commit',
            user: { login: 'charlie', displayName: 'Charlie' },
          },
        ],
      },
    ];

    test('selects repository by ID', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, '1');

      expect(result.selectedRepo?.id).toBe(1);
      expect(result.selectedRepo?.name).toBe('repo1');
    });

    test('returns "All repositories" when repoParam is "all"', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, 'all');

      expect(result.selectedRepo?.name).toBe('All repositories');
      expect(result.selectedRepo?.id).toBe(-1);
    });

    test('returns "All repositories" when repoParam is null', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, null);

      expect(result.selectedRepo?.name).toBe('All repositories');
    });

    test('aggregates activities from all repos when "all"', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, 'all');

      expect(result.selectedRepo?.activities).toHaveLength(3);
    });

    test('extracts unique member list', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, '1');

      expect(result.members).toEqual(['Alice', 'Bob']);
    });

    test('sorts members alphabetically', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, 'all');

      expect(result.members).toEqual(['Alice', 'Bob', 'Charlie']);
    });

    test('returns null when repo is not found', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, '999');

      expect(result.selectedRepo).toBeNull();
      expect(result.members).toEqual([]);
    });

    test('treats non-numeric repoParam as "all"', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, 'invalid');

      expect(result.selectedRepo?.name).toBe('All repositories');
    });

    test('uses displayName when available', () => {
      const result = Utils.selectRepoAndFilter(mockRepositories, '1');

      expect(result.members).toContain('Alice');
    });

    test('uses login when displayName is empty', () => {
      const reposWithLogin: RepoActivitySummary[] = [
        {
          id: 1,
          name: 'repo1',
          activities: [
            {
              date: '2024-01-01T10:00:00Z',
              type: 'commit',
              user: { login: 'alice', displayName: '' },
            },
          ],
        },
      ];

      const result = Utils.selectRepoAndFilter(reposWithLogin, '1');

      expect(result.members).toContain('alice');
    });

    test('uses "Unknown" when both login and displayName are empty', () => {
      const reposWithoutUser: RepoActivitySummary[] = [
        {
          id: 1,
          name: 'repo1',
          activities: [
            {
              date: '2024-01-01T10:00:00Z',
              type: 'commit',
              user: { login: '', displayName: '' },
            },
          ],
        },
      ];

      const result = Utils.selectRepoAndFilter(reposWithoutUser, '1');

      expect(result.members).toContain('Unknown');
    });

    test('removes duplicate members', () => {
      const reposWithDuplicates: RepoActivitySummary[] = [
        {
          id: 1,
          name: 'repo1',
          activities: [
            {
              date: '2024-01-01T10:00:00Z',
              type: 'commit',
              user: { login: 'alice', displayName: 'Alice' },
            },
            {
              date: '2024-01-01T11:00:00Z',
              type: 'commit',
              user: { login: 'alice', displayName: 'Alice' },
            },
          ],
        },
      ];

      const result = Utils.selectRepoAndFilter(reposWithDuplicates, '1');

      expect(result.members).toEqual(['Alice']);
    });
  });

  // ========== CALCULATECUTOFFDATE ==========
  describe('calculateCutoffDate', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-01-10T12:00:00Z'));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    test('calculates Last 24 hours', () => {
      const result = Utils.calculateCutoffDate('Last 24 hours');

      expect(result).toBeInstanceOf(Date);
      expect(result?.toISOString()).toBe('2024-01-09T12:00:00.000Z');
    });

    test('calculates Last 7 days', () => {
      const result = Utils.calculateCutoffDate('Last 7 days');

      expect(result?.toISOString()).toBe('2024-01-03T12:00:00.000Z');
    });

    test('calculates Last 30 days', () => {
      const result = Utils.calculateCutoffDate('Last 30 days');

      expect(result?.toISOString()).toBe('2023-12-11T12:00:00.000Z');
    });

    test('calculates Last 6 months', () => {
      const result = Utils.calculateCutoffDate('Last 6 months');

      expect(result?.toISOString()).toBe('2023-07-10T12:00:00.000Z');
    });

    test('calculates Last Year', () => {
      const result = Utils.calculateCutoffDate('Last Year');

      expect(result?.toISOString()).toBe('2023-01-10T12:00:00.000Z');
    });

    test('returns null for All Time', () => {
      const result = Utils.calculateCutoffDate('All Time');

      expect(result).toBeNull();
    });

    test('returns null for unknown string', () => {
      const result = Utils.calculateCutoffDate('Unknown');

      expect(result).toBeNull();
    });

    test('returns null for empty string', () => {
      const result = Utils.calculateCutoffDate('');

      expect(result).toBeNull();
    });
  });

  // ========== EDGE CASES ==========
  describe('Edge Cases', () => {
    test('processActivityData with special characters in repo name', () => {
      const dataWithSpecialChars: ActivityData[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          repo: 'repo-with-dash_and_underscore',
          user: 'user1',
        },
      ];

      const result = Utils.processActivityData(dataWithSpecialChars);

      expect(result.repositories[0].name).toBe('repo-with-dash_and_underscore');
    });

    test('aggregateBasicData with very large values', () => {
      const largeActivities: ProcessedActivity[] = [
        {
          date: '2024-01-01T10:00:00Z',
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
          additions: 999999,
          deletions: 888888,
        },
      ];

      const result = Utils.aggregateBasicData(largeActivities);

      expect(result[0].additions).toBe(999999);
      expect(result[0].deletions).toBe(888888);
    });

    test('aggregatePieData with many different contributors', () => {
      const manyContributors: ProcessedActivity[] = Array.from({ length: 100 }, (_, i) => ({
        date: '2024-01-01T10:00:00Z',
        type: 'commit',
        user: { login: `user${i}`, displayName: `User ${i}` },
      }));

      const result = Utils.aggregatePieData(manyContributors, {}, 10);

      expect(result.length).toBeLessThanOrEqual(11); // 10 top + Others
      const others = result.find((d) => d.label === 'Others');
      expect(others?.value).toBe(90);
    });

    test('applyFilters with dates at the cutoff boundary', () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date('2024-01-10T12:00:00Z'));

      const borderlineActivities: ProcessedActivity[] = [
        {
          date: '2024-01-09T12:00:00Z', // Exactly 24h ago
          type: 'commit',
          user: { login: 'user1', displayName: 'User One' },
        },
        {
          date: '2024-01-09T11:59:59Z', // 1 second before 24h
          type: 'commit',
          user: { login: 'user2', displayName: 'User Two' },
        },
      ];

      const result = Utils.applyFilters(borderlineActivities, [], 'Last 24 hours');

      expect(result.length).toBeGreaterThanOrEqual(1);

      vi.useRealTimers();
    });
  });

  // ========== INTEGRATION ==========
  describe('Integration Tests', () => {
    test('full flow: fetch -> process -> aggregate', async () => {
      vi.mocked(fetchData).mockResolvedValue(mockRawActivities);

      const processed = await Utils.fetchAndProcessActivityData('commit');
      const repo = processed.repositories[0];
      const basicData = Utils.aggregateBasicData(repo.activities);

      expect(basicData.length).toBeGreaterThan(0);
      expect(basicData[0]).toHaveProperty('date');
      expect(basicData[0]).toHaveProperty('value');
    });

    test('full flow with filters', async () => {
      vi.mocked(fetchData).mockResolvedValue(mockRawActivities);

      const processed = await Utils.fetchAndProcessActivityData();
      const { selectedRepo, members } = Utils.selectRepoAndFilter(processed.repositories, 'all');

      if (selectedRepo) {
        const filtered = Utils.applyFilters(selectedRepo.activities, [members[0]], 'All Time');
        const pieData = Utils.aggregatePieData(filtered);

        expect(pieData.length).toBeGreaterThan(0);
      }
    });
  });
});

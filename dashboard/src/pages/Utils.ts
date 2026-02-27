/**
 * Utils Module
 *
 * Utility functions and types for processing GitHub activity data.
 * Handles data fetching, processing, and transformation for visualization.
 */

import { scaleOrdinal } from 'd3-scale';
import { schemeSpectral } from 'd3-scale-chromatic';
import { fetchData, filterMetadata } from '../services/dataSource';
import type { BasicDatum, PieDatum } from '../types';

export interface ActivityData {
  date: string;
  type: string;
  repo: string;
  user: string;
  additions?: number;
  deletions?: number;
  totalLines?: number;
  total_changes?: number;
}

export interface ProcessedActivityResponse {
  generatedAt: string;
  repoCount: number;
  totalActivities: number;
  repositories: RepoActivitySummary[];
}

export interface RepoActivitySummary {
  id: number;
  name: string;
  activities: ProcessedActivity[];
}

export interface ProcessedActivity {
  date: string;
  type: string;
  user: {
    login: string;
    displayName: string;
  };
  additions?: number;
  deletions?: number;
  totalLines?: number;
}

// Options for data aggregation
export interface AggregationOptions {
  groupByHour?: boolean;  // true = group by hour, false = group by day
  cutoffDate?: Date | null;  // filter out activities before this date
}

export class Utils {
  /**
   * Process raw activity data from GitHub into a structured format
   *
   * @param rawActivities - Raw activity data from GitHub API
   * @param filterType - Optional type filter (e.g., 'commit', 'issue', 'pull_request')
   * @returns Processed activity response with grouped repositories
   */
  static processActivityData(
    rawActivities: ActivityData[],
    filterType?: string
  ): ProcessedActivityResponse {
    // Define related types for each category
    const issueTypes = ['issue_created'];
    const commitTypes = ['commit'];
    const prTypes = ['pr_created'];

    // Filter by category if specified
    let filteredActivities = rawActivities;

    if (filterType === 'issue') {
      filteredActivities = rawActivities.filter(activity => issueTypes.includes(activity.type));
    } else if (filterType === 'commit') {
      filteredActivities = rawActivities.filter(activity => commitTypes.includes(activity.type));
    } else if (filterType === 'pull_request') {
      filteredActivities = rawActivities.filter(activity => prTypes.includes(activity.type));
    } else if (filterType) {
      filteredActivities = rawActivities.filter(activity => activity.type === filterType);
    }

    // Group activities by repository
    const activitiesByRepo = new Map<string, ActivityData[]>();

    for (const activity of filteredActivities) {
      if ('_metadata' in activity) continue;

      const repoName = activity.repo;
      if (!repoName) continue;

      if (!activitiesByRepo.has(repoName)) {
        activitiesByRepo.set(repoName, []);
      }
      activitiesByRepo.get(repoName)!.push(activity);
    }

    // Convert to expected format
    const repositories: RepoActivitySummary[] = [];
    let repoId = 1;

    for (const [repoName, repoActivities] of activitiesByRepo.entries()) {
      const processedActivities: ProcessedActivity[] = repoActivities.map((activity) => ({
        date: activity.date,
        type: activity.type,
        user: {
          login: activity.user,
          displayName: activity.user || 'Unknown',
        },
        additions: activity.additions,
        deletions: activity.deletions,
        totalLines: activity.totalLines,
      }));

      repositories.push({
        id: repoId++,
        name: repoName,
        activities: processedActivities,
      });
    }

    const totalActivities = repositories.reduce((sum, repo) => sum + repo.activities.length, 0);

    return {
      generatedAt: new Date().toISOString(),
      repoCount: repositories.length,
      totalActivities,
      repositories,
    };
  }

  /**
   * Fetch and process activity data from the remote JSON source
   *
   * @param type - Activity type to filter by (optional)
   * @returns Promise with processed activity data
   * @throws Error if fetch fails
   */
  static async fetchAndProcessActivityData(type?: string): Promise<ProcessedActivityResponse> {
    // Fetch from dynamic data source (GitHub or local)
    const rawActivities = await fetchData<ActivityData[]>('silver/temporal_events.json');

    // Filter metadata and process
    const cleanActivities = filterMetadata(rawActivities);
    const processedData = Utils.processActivityData(cleanActivities, type);

    return processedData;
  }

  /**
   * Aggregate activities into BasicDatum format with temporal grouping
   *
   * @param activities - Processed activities to aggregate
   * @param options - Aggregation options (grouping, filtering)
   * @returns Array of BasicDatum with aggregated metrics
   */
  static aggregateBasicData(
    activities: ProcessedActivity[],
    options: AggregationOptions = {}
  ): BasicDatum[] {
    const { groupByHour = false, cutoffDate = null } = options;

    const map = new Map<string, {
      value: number;
      additions: number;
      deletions: number;
    }>();

    for (const activity of activities) {
      const iso = activity.date;

      let key: string;
      if (groupByHour) {
        const d = new Date(iso);
        const hourKey = new Date(d);
        hourKey.setMinutes(0, 0, 0);
        key = hourKey.toISOString();
      } else {
        key = iso.slice(0, 10);
      }

      if (cutoffDate) {
        const activityDate = new Date(key.length > 10 ? key : key + 'T00:00:00Z');
        if (activityDate < cutoffDate) continue;
      }

      const additions = activity.additions ?? 0;
      const deletions = activity.deletions ?? 0;

      const entry = map.get(key) ?? { value: 0, additions: 0, deletions: 0 };
      entry.value += 1;
      entry.additions += additions;
      entry.deletions += deletions;
      map.set(key, entry);
    }

    const sortedKeys = [...map.keys()].sort();
    const results: BasicDatum[] = [];
    let cumulativeTotal = 0;

    for (const k of sortedKeys) {
      const e = map.get(k)!;
      cumulativeTotal += (e.additions - e.deletions);

      results.push({
        date: k,
        value: e.value,
        additions: e.additions,
        deletions: e.deletions,
        totalLines: Math.max(0, cumulativeTotal),
      });
    }

    return results;
  }

  /**
   * Aggregate activities into PieDatum format for contributor distribution
   *
   * @param activities - Processed activities to aggregate
   * @param options - Aggregation options (cutoff date, time selection)
   * @param topN - Number of top contributors to show (default: 8)
   * @returns Array of PieDatum with contributor distribution
   */
  static aggregatePieData(
    activities: ProcessedActivity[],
    options: { cutoffDate?: Date | null; selectedTime?: string } = {},
    topN: number = 8
  ): PieDatum[] {
    const { cutoffDate = null, selectedTime = '' } = options;

    const counts = new Map<string, number>();

    for (const activity of activities) {
      if (cutoffDate) {
        const activityDate = selectedTime === 'Last 24 hours'
          ? new Date(activity.date)
          : new Date(activity.date.slice(0, 10) + 'T00:00:00Z');
        if (activityDate < cutoffDate) continue;
      }

      const label = activity.user.displayName || activity.user.login || 'Unknown';
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }

    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const top = sorted.slice(0, topN);
    const restTotal = sorted.slice(topN).reduce((acc, [, value]) => acc + value, 0);

    const colorScale = scaleOrdinal<string, string>()
      .domain([...top.map(([label]) => label), 'Others'])
      .range([...schemeSpectral[3], ...schemeSpectral[11]]);

    const result = top.map(([label, value]) => ({
      label,
      value,
      color: colorScale(label),
    }));

    if (restTotal > 0) {
      result.push({
        label: 'Others',
        value: restTotal,
        color: colorScale('Others'),
      });
    }

    return result;
  }

  /**
   * Apply member and time filters to activities
   *
   * @param activities - Activities to filter
   * @param selectedMembers - Member names to filter by (empty array = all)
   * @param selectedTime - Time range to filter by (e.g., 'Last 24 hours', 'All Time')
   * @returns Filtered activities
   */
  static applyFilters(
    activities: ProcessedActivity[],
    selectedMembers: string[],
    selectedTime: string
  ): ProcessedActivity[] {
    let filteredActivities = activities;

    // Filter by members
    if (selectedMembers && selectedMembers.length > 0) {
      filteredActivities = filteredActivities.filter((activity) => {
        const name = activity.user.displayName || activity.user.login || 'Unknown';
        return selectedMembers.includes(name);
      });
    }

    // Filter by time
    if (selectedTime !== 'All Time') {
      const now = new Date();
      const cutoffDate = new Date();

      switch (selectedTime) {
        case 'Last 24 hours':
          cutoffDate.setHours(now.getHours() - 24);
          break;
        case 'Last 7 days':
          cutoffDate.setDate(now.getDate() - 7);
          break;
        case 'Last 30 days':
          cutoffDate.setDate(now.getDate() - 30);
          break;
        case 'Last 6 months':
          cutoffDate.setMonth(now.getMonth() - 6);
          break;
        case 'Last Year':
          cutoffDate.setFullYear(now.getFullYear() - 1);
          break;
      }

      filteredActivities = filteredActivities.filter((activity) => {
        const activityDate = new Date(activity.date);
        return activityDate >= cutoffDate;
      });
    }

    return filteredActivities;
  }

  /**
   * Select repository and extract list of members
   *
   * @param repositories - Array of repositories to select from
   * @param repoParam - Repository parameter from URL (repo ID or 'all')
   * @returns Object containing selected repo and list of members
   */
  static selectRepoAndFilter(
    repositories: RepoActivitySummary[],
    repoParam: string | null
  ): {
    selectedRepo: RepoActivitySummary | null;
    members: string[];
  } {
    const selectedRepoId: number | 'all' =
      !repoParam || repoParam === 'all'
        ? 'all'
        : Number.isNaN(Number(repoParam))
          ? 'all'
          : Number(repoParam);

    let selectedRepo: RepoActivitySummary | null;

    if (selectedRepoId === 'all') {
      selectedRepo = {
        id: -1,
        name: 'All repositories',
        activities: repositories.flatMap((r) => r.activities),
      } as RepoActivitySummary;
    } else {
      selectedRepo = repositories.find((r) => r.id === selectedRepoId) ?? null;
    }

    if (!selectedRepo) {
      return { selectedRepo: null, members: [] };
    }

    const memberSet = new Set<string>();
    for (const activity of selectedRepo.activities) {
      const name = activity.user?.displayName || activity.user?.login || 'Unknown';
      memberSet.add(name);
    }
    const membersFound = Array.from(memberSet).sort((a, b) => a.localeCompare(b));
    const members = membersFound;

    return { selectedRepo, members };
  }

  /**
   * Calculate cutoff date based on time range selection
   *
   * @param selectedTime - Time range string (e.g., 'Last 24 hours', 'Last 7 days')
   * @returns Date representing the cutoff, or null if no filter
   */
  static calculateCutoffDate(selectedTime: string): Date | null {
    const now = new Date();
    switch (selectedTime) {
      case 'Last 24 hours': {
        const d = new Date(now);
        d.setDate(d.getDate() - 1);
        return d;
      }
      case 'Last 7 days': {
        const d = new Date(now);
        d.setDate(d.getDate() - 7);
        return d;
      }
      case 'Last 30 days': {
        const d = new Date(now);
        d.setDate(d.getDate() - 30);
        return d;
      }
      case 'Last 6 months': {
        const d = new Date(now);
        d.setMonth(d.getMonth() - 6);
        return d;
      }
      case 'Last Year': {
        const d = new Date(now);
        d.setFullYear(d.getFullYear() - 1);
        return d;
      }
      default:
        return null;
    }
  }
}

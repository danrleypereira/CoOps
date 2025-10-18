import { useEffect, useState, useMemo } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import BaseFilters from '../components/BaseFilters';
import Loading from '../components/Loading';
import { StackedBarChart } from '../components/charts';
import { fetchData, filterMetadata } from '../services/dataSource';
import { Utils } from './Utils';

interface TemporalEvent {
  date: string;
  type: string;
  user: string;
  repo: string;
}

/**
 * Issues Page
 *
 * Displays issue-related analytics across repositories.
 * Shows distribution of issues, PRs, and commits by repository.
 */
export default function Issues() {
  const [temporalData, setTemporalData] = useState<TemporalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtering, setFiltering] = useState(false);
  const [selectedTime, setSelectedTime] = useState<string>('All Time');
  const [selectedMember, setSelectedMember] = useState<string>('All');
  const [activityData, setActivityData] = useState<any>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [temporal, activity] = await Promise.all([
          fetchData('silver/temporal_events.json'),
          Utils.fetchAndProcessActivityData(),
        ]);

        setTemporalData(filterMetadata(temporal));
        setActivityData(activity);
        setLoading(false);
      } catch (error) {
        console.error('Failed to load issues data:', error);
        setLoading(false);
      }
    }

    loadData();
  }, []);

  // Calculate cutoff date based on selected time filter
  const cutoffDate = useMemo<Date | null>(() => {
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
  }, [selectedTime]);

  // Show filtering state when filters change
  useEffect(() => {
    if (temporalData.length > 0) {
      setFiltering(true);
      const timer = setTimeout(() => setFiltering(false), 300);
      return () => clearTimeout(timer);
    }
  }, [selectedMember, selectedTime]);

  // Filter temporal events by member and time
  const filteredTemporalData = useMemo(() => {
    let filtered = temporalData;

    // Filter by member
    if (selectedMember && selectedMember !== 'All') {
      filtered = filtered.filter((event) => event.user === selectedMember);
    }

    // Filter by time
    if (cutoffDate) {
      filtered = filtered.filter((event) => {
        const eventDate = new Date(event.date);
        return eventDate >= cutoffDate;
      });
    }

    return filtered;
  }, [temporalData, selectedMember, cutoffDate]);

  // Calculate repository stacked data from filtered events
  const repoStackedData = useMemo(() => {
    const repoMetrics = new Map<string, { issues: number; prs: number; commits: number }>();

    filteredTemporalData.forEach((event) => {
      if (!repoMetrics.has(event.repo)) {
        repoMetrics.set(event.repo, { issues: 0, prs: 0, commits: 0 });
      }
      const metrics = repoMetrics.get(event.repo)!;

      if (event.type === 'issue') {
        metrics.issues++;
      } else if (event.type === 'pr') {
        metrics.prs++;
      } else if (event.type === 'commit') {
        metrics.commits++;
      }
    });

    return Array.from(repoMetrics.entries()).map(([repo, metrics]) => ({
      label: repo,
      issues: metrics.issues,
      prs: metrics.prs,
      commits: metrics.commits,
    }));
  }, [filteredTemporalData]);

  // Extract unique members for filter
  const members: string[] = activityData
    ? Array.from(
        new Set(
          activityData.repositories.flatMap((repo: any) =>
            repo.activities.map((activity: any) => activity.user.login)
          )
        )
      )
    : [];

  if (loading) {
    return (
      <DashboardLayout
        currentPage="repos"
        currentSubPage="issues"
        onRepo={true}
        currentRepo="All Repositories"
        data={activityData}
      >
        <Loading message="Loading issues analytics..." size="lg" />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      currentPage="repos"
      currentSubPage="issues"
      onRepo={true}
      currentRepo="All Repositories"
      data={activityData}
    >
      <div className="space-y-8 relative">
        {filtering && <Loading message="Filtering data..." size="md" overlay />}
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">Issues Analytics</h1>
          <p className="text-slate-400">
            Issue lifecycle, distributions, and patterns across repositories
          </p>
        </div>

        {/* Filters */}
        <BaseFilters
          members={members}
          selectedMember={selectedMember}
          onMemberChange={setSelectedMember}
          selectedTime={selectedTime}
          onTimeChange={setSelectedTime}
        />

        {/* Issues by Repository */}
        <div
          className="border rounded-lg p-6"
          style={{ backgroundColor: '#222222', borderColor: '#333333' }}
        >
          <h3 className="text-xl font-bold text-white mb-4">
            Issues by Repository
          </h3>
          <p className="text-slate-400 mb-4">
            Distribution of issues, PRs, and commits across all repositories
          </p>
          <StackedBarChart
            data={repoStackedData}
            keys={['issues', 'prs', 'commits']}
            width={900}
            height={400}
            xLabel="Repository"
            yLabel="Activity Count"
          />
        </div>
      </div>
    </DashboardLayout>
  );
}

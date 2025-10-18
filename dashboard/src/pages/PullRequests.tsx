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
 * Pull Requests Page
 *
 * Displays PR analytics and review patterns across repositories.
 * Shows PR activity breakdown with related commits.
 */
export default function PullRequests() {
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
        console.error('Failed to load PR data:', error);
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

  // Calculate repository stacked data for PRs from filtered events
  const repoStackedData = useMemo(() => {
    const repoMetrics = new Map<string, { prs: number; commits: number }>();

    filteredTemporalData.forEach((event) => {
      if (!repoMetrics.has(event.repo)) {
        repoMetrics.set(event.repo, { prs: 0, commits: 0 });
      }
      const metrics = repoMetrics.get(event.repo)!;

      if (event.type === 'pr') {
        metrics.prs++;
      } else if (event.type === 'commit') {
        metrics.commits++;
      }
    });

    return Array.from(repoMetrics.entries()).map(([repo, metrics]) => ({
      label: repo,
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
        currentSubPage="pullrequests"
        onRepo={true}
        currentRepo="All Repositories"
        data={activityData}
      >
        <Loading message="Loading PR analytics..." size="lg" />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      currentPage="repos"
      currentSubPage="pullrequests"
      onRepo={true}
      currentRepo="All Repositories"
      data={activityData}
    >
      <div className="space-y-8 relative">
        {filtering && <Loading message="Filtering data..." size="md" overlay />}
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">Pull Request Analytics</h1>
          <p className="text-slate-400">
            PR metrics, review patterns, and merge statistics across repositories
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

        {/* PR Activity */}
        <div
          className="border rounded-lg p-6"
          style={{ backgroundColor: '#222222', borderColor: '#333333' }}
        >
          <h3 className="text-xl font-bold text-white mb-4">
            Pull Request Activity
          </h3>
          <p className="text-slate-400 mb-4">
            Distribution of PRs and associated commits across repositories
          </p>
          <StackedBarChart
            data={repoStackedData}
            keys={['prs', 'commits']}
            width={900}
            height={400}
            xLabel="Repository"
            yLabel="Count"
            colors={['var(--color-amber-accent)', 'var(--color-blue-trust)']}
          />
        </div>
      </div>
    </DashboardLayout>
  );
}

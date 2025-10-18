import { useEffect, useState, useMemo } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import BaseFilters from '../components/BaseFilters';
import Loading from '../components/Loading';
import { BarChart } from '../components/charts';
import { fetchData, filterMetadata } from '../services/dataSource';
import { Utils } from './Utils';

interface TemporalEvent {
  date: string;
  type: string;
  user: string;
  repo: string;
}

/**
 * Structure Page
 *
 * Displays repository structure and organization metrics.
 * Shows how activity is distributed across repositories.
 */
export default function Structure() {
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
        console.error('Failed to load structure data:', error);
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

  // Calculate total activity per repository from filtered events
  const activityByRepo = useMemo(() => {
    const repoActivityCounts = new Map<string, number>();

    filteredTemporalData.forEach((event) => {
      const currentCount = repoActivityCounts.get(event.repo) || 0;
      repoActivityCounts.set(event.repo, currentCount + 1);
    });

    return Array.from(repoActivityCounts.entries())
      .map(([repo, count]) => ({ label: repo, value: count }))
      .sort((a, b) => b.value - a.value);
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
        currentSubPage="structure"
        onRepo={true}
        currentRepo="All Repositories"
        data={activityData}
      >
        <Loading message="Loading structure analytics..." size="lg" />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      currentPage="repos"
      currentSubPage="structure"
      onRepo={true}
      currentRepo="All Repositories"
      data={activityData}
    >
      <div className="space-y-8 relative">
        {filtering && <Loading message="Filtering data..." size="md" overlay />}
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">Repository Structure</h1>
          <p className="text-slate-400">
            Repository organization and activity distribution
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

        {/* Total Activity by Repository */}
        <div
          className="border rounded-lg p-6"
          style={{ backgroundColor: '#222222', borderColor: '#333333' }}
        >
          <h3 className="text-xl font-bold text-white mb-4">
            Total Activity by Repository
          </h3>
          <p className="text-slate-400 mb-4">
            Combined activity (issues + PRs + commits) across all repositories
          </p>
          <BarChart
            data={activityByRepo}
            width={900}
            height={400}
            xLabel="Repository"
            yLabel="Total Activity"
          />
        </div>
      </div>
    </DashboardLayout>
  );
}

import { useEffect, useState, useMemo } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import BaseFilters from '../components/BaseFilters';
import Loading from '../components/Loading';
import { NetworkGraph, Heatmap } from '../components/charts';
import { fetchData, filterMetadata } from '../services/dataSource';
import { Utils } from './Utils';

interface MemberAnalytics {
  login: string;
  maturity_score: number;
  status: string;
  public_repos: number;
  followers: number;
}

interface ContributionMetrics {
  user: string;
  total_contributions: number;
  commits: number;
  prs_authored: number;
  issues_created: number;
  has_contributed: boolean;
}

interface CollaborationEdge {
  source: string;
  target: string;
  weight: number;
}

interface TemporalEvent {
  date: string;
  type: string;
  user: string;
  repo: string;
}

/**
 * Collaboration Page
 *
 * Displays team collaboration networks and activity patterns.
 * Shows how team members interact and when they are most active.
 */
export default function Collaboration() {
  const [membersData, setMembersData] = useState<MemberAnalytics[]>([]);
  const [contributionsData, setContributionsData] = useState<ContributionMetrics[]>([]);
  const [collaborationData, setCollaborationData] = useState<CollaborationEdge[]>([]);
  const [temporalData, setTemporalData] = useState<TemporalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtering, setFiltering] = useState(false);
  const [selectedTime, setSelectedTime] = useState<string>('All Time');
  const [selectedMember, setSelectedMember] = useState<string>('All');
  const [activityData, setActivityData] = useState<any>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [members, contributions, collaboration, temporal, activity] = await Promise.all([
          fetchData('silver/members_analytics.json'),
          fetchData('silver/contribution_metrics.json'),
          fetchData('silver/collaboration_edges.json'),
          fetchData('silver/temporal_events.json'),
          Utils.fetchAndProcessActivityData(),
        ]);

        setMembersData(filterMetadata(members));
        setContributionsData(filterMetadata(contributions));
        setCollaborationData(filterMetadata(collaboration));
        setTemporalData(filterMetadata(temporal));
        setActivityData(activity);
        setLoading(false);
      } catch (error) {
        console.error('Failed to load collaboration data:', error);
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

  // Network graph data
  const networkNodes = Array.from(
    new Set([
      ...collaborationData.map((e) => e.source),
      ...collaborationData.map((e) => e.target),
    ])
  ).map((id) => {
    const member = membersData.find((m) => m.login === id);
    const contrib = contributionsData.find((c) => c.user === id);
    return {
      id,
      label: id,
      value: contrib?.total_contributions || 10,
      category: member?.status || 'unknown',
    };
  });

  const networkLinks = collaborationData
    .map((edge) => ({
      source: edge.source,
      target: edge.target,
      value: edge.weight,
    }))
    .filter((link) => link.value > 0);

  // Activity heatmap - use filtered data
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const heatmapData = useMemo(() => {
    const data: { row: string; col: string; value: number }[] = [];
    for (let day = 0; day < 7; day++) {
      for (let hour = 0; hour < 24; hour++) {
        const events = filteredTemporalData.filter((e) => {
          const date = new Date(e.date);
          return date.getDay() === day && date.getHours() === hour;
        });
        data.push({
          row: days[day],
          col: hour.toString(),
          value: events.length,
        });
      }
    }
    return data;
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
        currentSubPage="collaboration"
        onRepo={true}
        currentRepo="All Repositories"
        data={activityData}
      >
        <Loading message="Loading collaboration analytics..." size="lg" />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      currentPage="repos"
      currentSubPage="collaboration"
      onRepo={true}
      currentRepo="All Repositories"
      data={activityData}
    >
      <div className="space-y-8 relative">
        {filtering && <Loading message="Filtering data..." size="md" overlay />}
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">Collaboration Analytics</h1>
          <p className="text-slate-400">
            Team collaboration networks and activity patterns
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

        {/* Collaboration Network */}
        {networkLinks.length > 0 ? (
          <div
            className="border rounded-lg p-6"
            style={{ backgroundColor: '#222222', borderColor: '#333333' }}
          >
            <h3 className="text-xl font-bold text-white mb-4">
              Collaboration Network
            </h3>
            <p className="text-slate-400 mb-4">
              Interactive network showing collaboration patterns between team members
            </p>
            <div className="flex justify-center">
              <NetworkGraph
                nodes={networkNodes}
                links={networkLinks}
                width={900}
                height={600}
              />
            </div>
          </div>
        ) : (
          <div
            className="border rounded-lg p-6"
            style={{ backgroundColor: '#222222', borderColor: '#333333' }}
          >
            <h3 className="text-xl font-bold text-white mb-4">
              Collaboration Network
            </h3>
            <p className="text-slate-400">
              No collaboration data available. This graph shows when team members work on the same repositories.
            </p>
          </div>
        )}

        {/* Activity Heatmap */}
        <div
          className="border rounded-lg p-6"
          style={{ backgroundColor: '#222222', borderColor: '#333333' }}
        >
          <h3 className="text-xl font-bold text-white mb-4">
            Team Activity Patterns
          </h3>
          <p className="text-slate-400 mb-4">
            Heatmap showing when the team is most active (by day and hour)
          </p>
          <Heatmap
            data={heatmapData}
            width={900}
            height={400}
            rowLabels={days}
            colorScheme="blue"
          />
        </div>
      </div>
    </DashboardLayout>
  );
}

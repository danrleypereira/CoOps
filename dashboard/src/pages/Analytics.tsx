import { useEffect, useState } from 'react';
import DashboardLayout from '../components/DashboardLayout';
import {
  PieChart,
  BarChart,
  LineChart,
  ScatterPlot,
  Histogram,
  StackedBarChart,
  NetworkGraph,
  Heatmap,
} from '../components/charts';
import { fetchData, filterMetadata } from '../services/dataSource';

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

interface RepositoryMetrics {
  repo: string;
  issues: number;
  prs: number;
  commits: number;
  total_activity: number;
}

interface TemporalEvent {
  date: string;
  type: string;
  user: string;
  repo: string;
}

interface CollaborationEdge {
  source: string;
  target: string;
  weight: number;
}

/**
 * Analytics Page
 *
 * Comprehensive analytics dashboard with sections for different analysis areas:
 * - Commits: Commit-related metrics and trends
 * - Issues: Issue lifecycle and distributions
 * - Pull Requests: PR analytics and review patterns
 * - Collaboration: Team collaboration networks and patterns
 * - Structure: Repository structure and member distributions
 */
export default function Analytics() {
  const [membersData, setMembersData] = useState<MemberAnalytics[]>([]);
  const [contributionsData, setContributionsData] = useState<ContributionMetrics[]>([]);
  const [repoData, setRepoData] = useState<RepositoryMetrics[]>([]);
  const [temporalData, setTemporalData] = useState<TemporalEvent[]>([]);
  const [collaborationData, setCollaborationData] = useState<CollaborationEdge[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [members, contributions, repos, temporal, collaboration] = await Promise.all([
          fetchData('silver/members_analytics.json'),
          fetchData('silver/contribution_metrics.json'),
          fetchData('silver/repository_metrics.json'),
          fetchData('silver/temporal_events.json'),
          fetchData('silver/collaboration_edges.json'),
        ]);

        setMembersData(filterMetadata(members));
        setContributionsData(filterMetadata(contributions));
        setRepoData(filterMetadata(repos));
        setTemporalData(filterMetadata(temporal));
        setCollaborationData(filterMetadata(collaboration));

        setLoading(false);
      } catch (error) {
        console.error('Failed to load analytics data:', error);
        setLoading(false);
      }
    }

    loadData();
  }, []);

  // Transform data for charts
  const topContributorsBarData = contributionsData
    .filter((c) => c.has_contributed)
    .sort((a, b) => b.total_contributions - a.total_contributions)
    .slice(0, 10)
    .map((c) => ({ label: c.user, value: c.total_contributions }));

  // Commits over time
  const commitTimelineData = temporalData
    .filter((e) => e.type === 'commit')
    .reduce((acc, event) => {
      const date = event.date.split('T')[0];
      const existing = acc.find((d) => d.date === date);
      if (existing) {
        existing.value++;
      } else {
        acc.push({ date, value: 1 });
      }
      return acc;
    }, [] as { date: string; value: number }[])
    .sort((a, b) => a.date.localeCompare(b.date));

  // Commits per repository
  const commitsPerRepo = repoData
    .sort((a, b) => b.commits - a.commits)
    .map((r) => ({ label: r.repo, value: r.commits }));

  // Repository stacked data
  const repoStackedData = repoData.map((r) => ({
    label: r.repo,
    issues: r.issues,
    prs: r.prs,
    commits: r.commits,
  }));

  // Member status distribution
  const memberStatusPieData = membersData.reduce((acc, m) => {
    const status = m.status === 'new' ? 'New Members' : 'Established Members';
    const existing = acc.find((d) => d.label === status);
    if (existing) {
      existing.value++;
    } else {
      acc.push({ label: status, value: 1 });
    }
    return acc;
  }, [] as { label: string; value: number }[]);

  // Maturity vs Contributions scatter
  const maturityScatterData = membersData.map((m) => {
    const contrib = contributionsData.find((c) => c.user === m.login);
    return {
      x: m.maturity_score,
      y: contrib?.total_contributions || 0,
      label: m.login,
      category: m.status,
    };
  });

  // Followers histogram
  const followersHistogramData = membersData.map((m) => m.followers);

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

  // Activity heatmap
  const heatmapData: { row: string; col: string; value: number }[] = [];
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  for (let day = 0; day < 7; day++) {
    for (let hour = 0; hour < 24; hour++) {
      const events = temporalData.filter((e) => {
        const date = new Date(e.date);
        return date.getDay() === day && date.getHours() === hour;
      });
      heatmapData.push({
        row: days[day],
        col: hour.toString(),
        value: events.length,
      });
    }
  }

  if (loading) {
    return (
      <DashboardLayout currentPage="analytics" currentSubPage="" onRepo={false}>
        <div className="flex items-center justify-center h-96">
          <div className="text-slate-400 text-xl">Loading analytics...</div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout currentPage="analytics" currentSubPage="" onRepo={false}>
      <div className="space-y-12">
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">Analytics Dashboard</h1>
          <p className="text-slate-400">
            Comprehensive insights from GitHub metrics across the organization
          </p>
        </div>

        {/* Commits Section */}
        <section className="space-y-8">
          <h2 className="text-3xl font-bold text-white flex items-center gap-3">
            <span>💾</span> Commits
          </h2>
          <div className="space-y-8">
            {/* Top Contributors */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">Top Contributors by Commits</h3>
              <BarChart
                data={topContributorsBarData}
                width={900}
                height={400}
                orientation="horizontal"
                yLabel="Total Contributions"
              />
            </div>

            {/* Commits Timeline */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">Commit Activity Over Time</h3>
              <LineChart
                data={commitTimelineData}
                width={900}
                height={400}
                showArea={true}
                xLabel="Date"
                yLabel="Commits"
              />
            </div>

            {/* Commits per Repository */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">Commits per Repository</h3>
              <BarChart
                data={commitsPerRepo}
                width={900}
                height={400}
                xLabel="Repository"
                yLabel="Commits"
              />
            </div>
          </div>
        </section>

        {/* Issues Section */}
        <section className="space-y-8">
          <h2 className="text-3xl font-bold text-white flex items-center gap-3">
            <span>🐛</span> Issues
          </h2>
          <div className="space-y-8">
            {/* Repository Activity Breakdown */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">
                Issues by Repository
              </h3>
              <p className="text-slate-400 mb-4">
                Showing issues, PRs, and commits across all repositories
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
        </section>

        {/* Pull Requests Section */}
        <section className="space-y-8">
          <h2 className="text-3xl font-bold text-white flex items-center gap-3">
            <span>🔀</span> Pull Requests
          </h2>
          <div className="space-y-8">
            {/* PR Activity */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">
                Pull Request Activity
              </h3>
              <p className="text-slate-400 mb-4">
                Combined view of issues, PRs, and commits by repository
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
        </section>

        {/* Collaboration Section */}
        <section className="space-y-8">
          <h2 className="text-3xl font-bold text-white flex items-center gap-3">
            <span>🤝</span> Collaboration
          </h2>
          <div className="space-y-8">
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
        </section>

        {/* Structure Section */}
        <section className="space-y-8">
          <h2 className="text-3xl font-bold text-white flex items-center gap-3">
            <span>📊</span> Structure
          </h2>
          <div className="space-y-8">
            {/* Member Distribution */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">
                Member Status Distribution
              </h3>
              <div className="flex justify-center">
                <PieChart data={memberStatusPieData} width={500} height={500} />
              </div>
            </div>

            {/* Maturity vs Contributions */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">
                Member Maturity vs Contributions
              </h3>
              <ScatterPlot
                data={maturityScatterData}
                width={900}
                height={400}
                xLabel="Maturity Score"
                yLabel="Total Contributions"
              />
            </div>

            {/* Followers Distribution */}
            <div
              className="border rounded-lg p-6"
              style={{ backgroundColor: '#222222', borderColor: '#333333' }}
            >
              <h3 className="text-xl font-bold text-white mb-4">
                Followers Distribution
              </h3>
              <Histogram
                data={followersHistogramData}
                width={900}
                height={400}
                xLabel="Number of Followers"
                yLabel="Frequency"
              />
            </div>
          </div>
        </section>
      </div>
    </DashboardLayout>
  );
}

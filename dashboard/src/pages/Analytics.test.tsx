import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import Analytics from './Analytics';
import { fetchData } from '../services/dataSource';

vi.mock('../services/dataSource', async () => {
  const actual = await vi.importActual<typeof import('../services/dataSource')>(
    '../services/dataSource'
  );
  return { ...actual, fetchData: vi.fn() };
});

vi.mock('../components/DashboardLayout', () => ({
  default: ({ children, currentPage }: { children: ReactNode; currentPage: string }) => (
    <div data-testid="dashboard-layout" data-page={currentPage}>
      {children}
    </div>
  ),
}));

type ChartProps = Record<string, unknown>;

function makeChart(testId: string) {
  return (props: ChartProps) => (
    <div
      data-testid={testId}
      data-label={String(props.yLabel ?? '')}
      data-props={JSON.stringify(props)}
    />
  );
}

vi.mock('../components/charts', () => ({
  PieChart: makeChart('pie-chart'),
  BarChart: makeChart('bar-chart'),
  LineChart: makeChart('line-chart'),
  ScatterPlot: makeChart('scatter-plot'),
  Histogram: makeChart('histogram'),
  StackedBarChart: makeChart('stacked-bar-chart'),
  NetworkGraph: makeChart('network-graph'),
  Heatmap: makeChart('heatmap'),
}));

const mockedFetchData = vi.mocked(fetchData);

function propsOf(el: HTMLElement): ChartProps {
  return JSON.parse(el.getAttribute('data-props') ?? '{}') as ChartProps;
}

// Build ISO strings from local-time components so day/hour buckets are TZ-independent
const localIso = (y: number, m: number, d: number, h: number) =>
  new Date(y, m, d, h).toISOString();

// 2024-01-01 is a Monday; 2024-01-02 is a Tuesday
const MON_10 = localIso(2024, 0, 1, 10);
const MON_10_B = localIso(2024, 0, 1, 10);
const TUE_14 = localIso(2024, 0, 2, 14);

const members = [
  { _metadata: { generated: 'x' } },
  { login: 'alice', maturity_score: 50, status: 'established', public_repos: 20, followers: 30 },
  { login: 'bob', maturity_score: 10, status: 'new', public_repos: 1, followers: 2 },
  { login: 'carol', maturity_score: 5, status: 'new', public_repos: 0, followers: 0 },
];

const contributions = [
  { user: 'alice', total_contributions: 40, commits: 30, prs_authored: 5, issues_created: 5, has_contributed: true },
  { user: 'bob', total_contributions: 70, commits: 60, prs_authored: 5, issues_created: 5, has_contributed: true },
  { user: 'dave', total_contributions: 0, commits: 0, prs_authored: 0, issues_created: 0, has_contributed: false },
];

const repos = [
  { repo: 'small', issues: 1, prs: 2, commits: 3, total_activity: 6 },
  { repo: 'big', issues: 4, prs: 5, commits: 60, total_activity: 69 },
];

const temporal = [
  { _metadata: true },
  { date: TUE_14, type: 'commit', user: 'bob', repo: 'big' },
  { date: MON_10, type: 'commit', user: 'alice', repo: 'big' },
  { date: MON_10_B, type: 'commit', user: 'bob', repo: 'small' },
  { date: MON_10, type: 'issue', user: 'alice', repo: 'small' },
];

const collaboration = [
  { source: 'alice', target: 'bob', weight: 3 },
  { source: 'bob', target: 'zed', weight: 0 },
];

function setupFetch(overrides: Record<string, unknown[]> = {}) {
  const fixtures: Record<string, unknown[]> = {
    'silver/members_analytics.json': members,
    'silver/contribution_metrics.json': contributions,
    'silver/repository_metrics.json': repos,
    'silver/temporal_events.json': temporal,
    'silver/collaboration_edges.json': collaboration,
    ...overrides,
  };
  mockedFetchData.mockImplementation(async (path: string) => fixtures[path] as never);
}

const renderPage = () =>
  render(
    <BrowserRouter>
      <Analytics />
    </BrowserRouter>
  );

describe('Analytics page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test('shows loading state before data resolves', () => {
    mockedFetchData.mockImplementation(() => new Promise<never>(() => {}));
    renderPage();
    expect(screen.getByText('Loading analytics...')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-layout')).toHaveAttribute('data-page', 'analytics');
  });

  test('requests all five silver datasets', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    const paths = mockedFetchData.mock.calls.map((c) => c[0]);
    expect(paths).toEqual([
      'silver/members_analytics.json',
      'silver/contribution_metrics.json',
      'silver/repository_metrics.json',
      'silver/temporal_events.json',
      'silver/collaboration_edges.json',
    ]);
  });

  test('computes top contributors sorted desc and excluding non-contributors', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    const bars = screen.getAllByTestId('bar-chart');
    const top = bars.find((b) => b.getAttribute('data-label') === 'Total Contributions');
    expect(top).toBeDefined();
    expect(propsOf(top as HTMLElement).data).toEqual([
      { label: 'bob', value: 70 },
      { label: 'alice', value: 40 },
    ]);
  });

  test('builds commit timeline grouped by date and sorted ascending, ignoring non-commits', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    const data = propsOf(screen.getByTestId('line-chart')).data as { date: string; value: number }[];
    const d1 = MON_10.split('T')[0];
    const d2 = TUE_14.split('T')[0];
    const expected = new Map<string, number>();
    [d1, d1, d2].forEach((d) => expected.set(d, (expected.get(d) ?? 0) + 1));
    const expectedArr = Array.from(expected.entries())
      .map(([date, value]) => ({ date, value }))
      .sort((a, b) => a.date.localeCompare(b.date));
    expect(data).toEqual(expectedArr);
    expect(data.reduce((s, d) => s + d.value, 0)).toBe(3);
  });

  test('commits per repo sorted desc and stacked data built for both stacked charts', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    const commitsChart = screen
      .getAllByTestId('bar-chart')
      .find((b) => b.getAttribute('data-label') === 'Commits') as HTMLElement;
    expect(propsOf(commitsChart).data).toEqual([
      { label: 'big', value: 60 },
      { label: 'small', value: 3 },
    ]);

    const stacked = screen.getAllByTestId('stacked-bar-chart');
    expect(stacked).toHaveLength(2);
    expect(propsOf(stacked[0]).keys).toEqual(['issues', 'prs', 'commits']);
    expect(propsOf(stacked[1]).keys).toEqual(['prs', 'commits']);
    expect(propsOf(stacked[0]).data).toEqual([
      { label: 'big', issues: 4, prs: 5, commits: 60 },
      { label: 'small', issues: 1, prs: 2, commits: 3 },
    ]);
  });

  test('computes member status pie, scatter and followers histogram', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    expect(propsOf(screen.getByTestId('pie-chart')).data).toEqual([
      { label: 'Established Members', value: 1 },
      { label: 'New Members', value: 2 },
    ]);
    expect(propsOf(screen.getByTestId('scatter-plot')).data).toEqual([
      { x: 50, y: 40, label: 'alice', category: 'established' },
      { x: 10, y: 70, label: 'bob', category: 'new' },
      { x: 5, y: 0, label: 'carol', category: 'new' },
    ]);
    expect(propsOf(screen.getByTestId('histogram')).data).toEqual([30, 2, 0]);
  });

  test('builds network nodes with defaults and drops zero-weight links', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    const props = propsOf(screen.getByTestId('network-graph'));
    expect(props.nodes).toEqual([
      { id: 'alice', label: 'alice', value: 40, category: 'established' },
      { id: 'bob', label: 'bob', value: 70, category: 'new' },
      { id: 'zed', label: 'zed', value: 10, category: 'unknown' },
    ]);
    expect(props.links).toEqual([{ source: 'alice', target: 'bob', value: 3 }]);
    expect(screen.queryByText(/No collaboration data available/)).not.toBeInTheDocument();
  });

  test('builds a 7x24 activity heatmap bucketed by local day and hour', async () => {
    setupFetch();
    renderPage();
    await screen.findByText('Analytics Dashboard');
    const props = propsOf(screen.getByTestId('heatmap'));
    const data = props.data as { row: string; col: string; value: number }[];
    expect(data).toHaveLength(7 * 24);
    expect(props.rowLabels).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
    expect(data.find((d) => d.row === 'Mon' && d.col === '10')?.value).toBe(3);
    expect(data.find((d) => d.row === 'Tue' && d.col === '14')?.value).toBe(1);
    expect(data.filter((d) => d.row === 'Sun').every((d) => d.value === 0)).toBe(true);
    expect(data.reduce((s, d) => s + d.value, 0)).toBe(4);
  });

  test('shows empty collaboration message when no positive-weight links exist', async () => {
    setupFetch({ 'silver/collaboration_edges.json': [{ source: 'a', target: 'b', weight: 0 }] });
    renderPage();
    await screen.findByText('Analytics Dashboard');
    expect(screen.getByText(/No collaboration data available/)).toBeInTheDocument();
    expect(screen.queryByTestId('network-graph')).not.toBeInTheDocument();
  });

  test('logs error and renders empty dashboard when loading fails', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockedFetchData.mockRejectedValue(new Error('boom'));
    renderPage();
    await screen.findByText('Analytics Dashboard');
    expect(errorSpy).toHaveBeenCalledWith('Failed to load analytics data:', expect.any(Error));
    expect(propsOf(screen.getByTestId('pie-chart')).data).toEqual([]);
    expect(propsOf(screen.getByTestId('line-chart')).data).toEqual([]);
    expect(screen.getByText(/No collaboration data available/)).toBeInTheDocument();
  });
});

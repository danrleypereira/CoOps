import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import Structure from './Structure';
import { fetchData } from '../services/dataSource';
import { Utils, type ProcessedActivityResponse } from './Utils';

vi.mock('../services/dataSource', async () => {
  const actual = await vi.importActual<typeof import('../services/dataSource')>(
    '../services/dataSource'
  );
  return { ...actual, fetchData: vi.fn() };
});

vi.mock('./Utils', () => ({
  Utils: {
    fetchAndProcessActivityData: vi.fn(),
  },
}));

vi.mock('../components/DashboardLayout', () => ({
  default: ({
    children,
    currentPage,
    currentSubPage,
    currentRepo,
    data,
  }: {
    children: ReactNode;
    currentPage: string;
    currentSubPage: string;
    currentRepo?: string;
    data?: unknown;
  }) => (
    <div
      data-testid="dashboard-layout"
      data-page={currentPage}
      data-subpage={currentSubPage}
      data-repo={currentRepo}
      data-has-data={data ? 'yes' : 'no'}
    >
      {children}
    </div>
  ),
}));

vi.mock('../components/charts', () => ({
  BarChart: (props: { data: { label: string; value: number }[]; yLabel?: string }) => (
    <div data-testid="bar-chart" data-y-label={props.yLabel} data-chart={JSON.stringify(props.data)} />
  ),
}));

const mockedFetchData = vi.mocked(fetchData);
const mockedActivity = vi.mocked(Utils.fetchAndProcessActivityData);

const NOW = new Date('2024-06-15T12:00:00Z');
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();
const HOUR = 3600 * 1000;
const DAY = 24 * HOUR;

// Each event lives in a distinct age bucket so every time filter yields a different result
const temporal = [
  { _metadata: { generated: true } },
  { date: ago(2 * HOUR), type: 'commit', user: 'alice', repo: 'repo-a' }, // < 24h
  { date: ago(3 * DAY), type: 'issue', user: 'bob', repo: 'repo-b' }, // < 7d
  { date: ago(20 * DAY), type: 'pr', user: 'alice', repo: 'repo-b' }, // < 30d
  { date: ago(120 * DAY), type: 'commit', user: 'carol', repo: 'repo-c' }, // < 6m
  { date: ago(300 * DAY), type: 'commit', user: 'bob', repo: 'repo-c' }, // < 1y
  { date: ago(700 * DAY), type: 'commit', user: 'alice', repo: 'repo-c' }, // > 1y
  { date: ago(800 * DAY), type: 'commit', user: 'carol', repo: 'repo-d' }, // > 1y
];

const activity: ProcessedActivityResponse = {
  generatedAt: NOW.toISOString(),
  repoCount: 2,
  totalActivities: 3,
  repositories: [
    {
      id: 1,
      name: 'repo-a',
      activities: [
        { date: NOW.toISOString(), type: 'commit', user: { login: 'alice', displayName: 'Alice' } },
        { date: NOW.toISOString(), type: 'commit', user: { login: 'bob', displayName: 'Bob' } },
      ],
    },
    {
      id: 2,
      name: 'repo-b',
      activities: [
        { date: NOW.toISOString(), type: 'commit', user: { login: 'alice', displayName: 'Alice' } },
        { date: NOW.toISOString(), type: 'commit', user: { login: 'carol', displayName: 'Carol' } },
      ],
    },
  ],
} as ProcessedActivityResponse;

type Bar = { label: string; value: number };

const chartData = (): Bar[] =>
  JSON.parse(screen.getByTestId('bar-chart').getAttribute('data-chart') ?? '[]') as Bar[];

const renderPage = () =>
  render(
    <BrowserRouter>
      <Structure />
    </BrowserRouter>
  );

async function renderLoaded() {
  const utils = renderPage();
  await screen.findByText('Repository Structure');
  return utils;
}

const timeSelect = () => screen.getByRole('combobox') as HTMLSelectElement;

function toggleMember(name: string) {
  fireEvent.focus(screen.getByPlaceholderText('Search members...'));
  fireEvent.click(screen.getByLabelText(name));
}

describe('Structure page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(NOW);
    mockedFetchData.mockResolvedValue(temporal as never);
    mockedActivity.mockResolvedValue(activity);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test('shows loading state and layout props before data arrives', () => {
    mockedFetchData.mockImplementation(() => new Promise<never>(() => {}));
    renderPage();
    expect(screen.getByText('Loading structure analytics...')).toBeInTheDocument();
    const layout = screen.getByTestId('dashboard-layout');
    expect(layout).toHaveAttribute('data-page', 'repos');
    expect(layout).toHaveAttribute('data-subpage', 'structure');
    expect(layout).toHaveAttribute('data-repo', 'All Repositories');
    expect(layout).toHaveAttribute('data-has-data', 'no');
  });

  test('loads temporal events and aggregates all activity per repo sorted desc', async () => {
    await renderLoaded();
    expect(mockedFetchData).toHaveBeenCalledWith('silver/temporal_events.json');
    expect(mockedActivity).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Total Activity by Repository')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-layout')).toHaveAttribute('data-has-data', 'yes');
    expect(chartData()).toEqual([
      { label: 'repo-c', value: 3 },
      { label: 'repo-b', value: 2 },
      { label: 'repo-a', value: 1 },
      { label: 'repo-d', value: 1 },
    ]);
    expect(timeSelect().value).toBe('All Time');
    expect(screen.queryByText('Filtering data...')).not.toBeInTheDocument();
  });

  test('extracts unique members from activity data into the member filter', async () => {
    await renderLoaded();
    fireEvent.focus(screen.getByPlaceholderText('Search members...'));
    const labels = ['alice', 'bob', 'carol'];
    labels.forEach((l) => expect(screen.getByLabelText(l)).toBeInTheDocument());
    // Only three member checkboxes plus "Select All"
    expect(screen.getAllByRole('checkbox')).toHaveLength(labels.length + 1);
  });

  test.each([
    ['Last 24 hours', [{ label: 'repo-a', value: 1 }]],
    ['Last 7 days', [{ label: 'repo-a', value: 1 }, { label: 'repo-b', value: 1 }]],
    ['Last 30 days', [{ label: 'repo-b', value: 2 }, { label: 'repo-a', value: 1 }]],
    [
      'Last 6 months',
      [
        { label: 'repo-b', value: 2 },
        { label: 'repo-a', value: 1 },
        { label: 'repo-c', value: 1 },
      ],
    ],
    [
      'Last Year',
      [
        { label: 'repo-b', value: 2 },
        { label: 'repo-c', value: 2 },
        { label: 'repo-a', value: 1 },
      ],
    ],
  ])('time filter "%s" restricts chart data', async (option, expected) => {
    await renderLoaded();
    fireEvent.change(timeSelect(), { target: { value: option } });
    expect(timeSelect().value).toBe(option);
    expect(chartData()).toEqual(expected);
  });

  test('switching back to "All Time" restores every event', async () => {
    await renderLoaded();
    fireEvent.change(timeSelect(), { target: { value: 'Last 24 hours' } });
    expect(chartData()).toHaveLength(1);
    fireEvent.change(timeSelect(), { target: { value: 'All Time' } });
    expect(chartData().reduce((s, b) => s + b.value, 0)).toBe(7);
  });

  test('filtering by a single member only counts that member events', async () => {
    await renderLoaded();
    toggleMember('carol');
    expect(screen.getByText('1 Member Selected')).toBeInTheDocument();
    expect(chartData()).toEqual([
      { label: 'repo-c', value: 1 },
      { label: 'repo-d', value: 1 },
    ]);
  });

  test('filtering by multiple members unions their events; deselecting all restores everything', async () => {
    await renderLoaded();
    toggleMember('alice');
    toggleMember('bob');
    expect(screen.getByText('2 Members Selected')).toBeInTheDocument();
    expect(chartData()).toEqual([
      { label: 'repo-b', value: 2 },
      { label: 'repo-c', value: 2 },
      { label: 'repo-a', value: 1 },
    ]);

    fireEvent.click(screen.getByLabelText('alice'));
    fireEvent.click(screen.getByLabelText('bob'));
    expect(screen.queryByText(/Selected$/)).not.toBeInTheDocument();
    expect(chartData().reduce((s, b) => s + b.value, 0)).toBe(7);
  });

  test('combines member and time filters', async () => {
    await renderLoaded();
    toggleMember('alice');
    fireEvent.change(timeSelect(), { target: { value: 'Last 30 days' } });
    expect(chartData()).toEqual([
      { label: 'repo-a', value: 1 },
      { label: 'repo-b', value: 1 },
    ]);
    fireEvent.change(timeSelect(), { target: { value: 'Last 24 hours' } });
    expect(chartData()).toEqual([{ label: 'repo-a', value: 1 }]);
  });

  test('member filter with no matching events in range yields empty chart', async () => {
    await renderLoaded();
    toggleMember('carol');
    fireEvent.change(timeSelect(), { target: { value: 'Last 7 days' } });
    expect(chartData()).toEqual([]);
  });

  test('shows "Filtering data..." overlay for 300ms after a filter change', async () => {
    await renderLoaded();
    fireEvent.change(timeSelect(), { target: { value: 'Last 7 days' } });
    expect(screen.getByText('Filtering data...')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText('Filtering data...')).not.toBeInTheDocument(), {
      timeout: 2000,
    });
  });

  test('does not show filtering overlay when there are no temporal events', async () => {
    mockedFetchData.mockResolvedValue([] as never);
    await renderLoaded();
    fireEvent.change(timeSelect(), { target: { value: 'Last Year' } });
    expect(screen.queryByText('Filtering data...')).not.toBeInTheDocument();
    expect(chartData()).toEqual([]);
  });

  test('on load failure logs the error, renders page with no members and empty chart', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    mockedActivity.mockRejectedValue(new Error('fail'));
    await renderLoaded();
    expect(errorSpy).toHaveBeenCalledWith('Failed to load structure data:', expect.any(Error));
    expect(chartData()).toEqual([]);
    expect(screen.queryByPlaceholderText('Search members...')).not.toBeInTheDocument();
  });
});

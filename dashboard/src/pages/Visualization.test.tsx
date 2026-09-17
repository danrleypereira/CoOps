import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import VisualizationPage from './Visualization';
import { VisualizationUtils, type LanguageAnalysis } from './VisualizationUtils';

vi.mock('./VisualizationUtils', () => ({
  VisualizationUtils: {
    fetchLanguageData: vi.fn(),
  },
}));

vi.mock('../components/DashboardLayout', () => ({
  default: ({
    children,
    currentPage,
    currentSubPage,
    currentRepo,
  }: {
    children: ReactNode;
    currentPage: string;
    currentSubPage: string;
    currentRepo?: string;
  }) => (
    <div
      data-testid="dashboard-layout"
      data-page={currentPage}
      data-subpage={currentSubPage}
      data-repo={currentRepo}
    >
      {children}
    </div>
  ),
}));

vi.mock('../components/RepoTreemap', () => ({
  RepoTreemap: ({ data, width, height }: { data: LanguageAnalysis; width: number; height: number }) => (
    <div data-testid="treemap" data-repo={data.repository} data-width={width} data-height={height} />
  ),
}));

vi.mock('../components/RepoFingerprint', () => ({
  RepoFingerprint: ({ data }: { data: LanguageAnalysis }) => (
    <div data-testid="fingerprint" data-repo={data.repository} />
  ),
}));

vi.mock('../components/RepoStructureAnalysis', () => ({
  RepoStructureAnalysis: ({ data }: { data: LanguageAnalysis }) => (
    <div data-testid="structure-analysis" data-repo={data.repository} />
  ),
}));

vi.mock('../components/LanguageLegend', () => ({
  LanguageLegend: ({
    languages,
    colorMap,
  }: {
    languages: { language: string }[];
    colorMap: Record<string, string>;
  }) => (
    <div
      data-testid="language-legend"
      data-count={languages.length}
      data-python-color={colorMap.Python}
      data-color-count={Object.keys(colorMap).length}
    />
  ),
}));

const mockedFetch = vi.mocked(VisualizationUtils.fetchLanguageData);

const analysis: LanguageAnalysis = {
  repository: 'my-repo',
  owner: 'org',
  branch: 'main',
  total_files: 42,
  total_bytes: 2048,
  languages: [
    { language: 'Python', file_count: 30, total_bytes: 1500, percentage: 73.2 },
    { language: 'Markdown', file_count: 12, total_bytes: 548, percentage: 26.8 },
  ],
};

const renderAt = (url: string) => {
  window.history.pushState({}, '', url);
  return render(
    <BrowserRouter>
      <VisualizationPage />
    </BrowserRouter>
  );
};

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('VisualizationPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    window.history.pushState({}, '', '/');
  });

  test('prompts to select a repository when no repo param is present', () => {
    renderAt('/visualization');
    expect(screen.getByText('Please select a repository from the toolbar above')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-layout')).toHaveAttribute('data-repo', 'No repository selected');
    expect(screen.getByTestId('dashboard-layout')).toHaveAttribute('data-subpage', 'visualization');
    expect(mockedFetch).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /Treemap/ })).not.toBeInTheDocument();
  });

  test('treats repo=all as no selection', () => {
    renderAt('/visualization?repo=all');
    expect(screen.getByText('Please select a repository from the toolbar above')).toBeInTheDocument();
    expect(screen.getByTestId('dashboard-layout')).toHaveAttribute('data-repo', 'all');
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  test('shows loading state, then treemap, summary, analysis and legend', async () => {
    const d = deferred<LanguageAnalysis | null>();
    mockedFetch.mockReturnValue(d.promise);
    renderAt('/visualization?repo=my-repo');

    expect(screen.getByText('Loading data for my-repo...')).toBeInTheDocument();
    expect(screen.getByText('📊 Treemap View')).toBeInTheDocument();
    expect(screen.queryByTestId('treemap')).not.toBeInTheDocument();
    expect(mockedFetch).toHaveBeenCalledWith('my-repo');

    await act(async () => {
      d.resolve(analysis);
    });

    expect(screen.queryByText(/Loading data for/)).not.toBeInTheDocument();
    expect(screen.getByText('my-repo • 42 files • 2 languages')).toBeInTheDocument();
    const treemap = screen.getByTestId('treemap');
    expect(treemap).toHaveAttribute('data-repo', 'my-repo');
    expect(treemap).toHaveAttribute('data-height', '600');
    expect(Number(treemap.getAttribute('data-width'))).toBe(Math.min(900, window.innerWidth - 100));
    expect(screen.getByTestId('structure-analysis')).toHaveAttribute('data-repo', 'my-repo');
    const legend = screen.getByTestId('language-legend');
    expect(legend).toHaveAttribute('data-count', '2');
    expect(legend).toHaveAttribute('data-python-color', '#3572A5');
    expect(legend).toHaveAttribute('data-color-count', '19');
  });

  test('switches between treemap and circle pack modes via tabs', async () => {
    mockedFetch.mockResolvedValue(analysis);
    renderAt('/visualization?repo=my-repo');
    await screen.findByTestId('treemap');

    fireEvent.click(screen.getByRole('button', { name: /Circle Pack/ }));
    expect(screen.getByText('⭕ Circle Pack View')).toBeInTheDocument();
    expect(screen.getByTestId('fingerprint')).toHaveAttribute('data-repo', 'my-repo');
    expect(screen.queryByTestId('treemap')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Treemap/ }));
    expect(screen.getByText('📊 Treemap View')).toBeInTheDocument();
    expect(screen.getByTestId('treemap')).toBeInTheDocument();
    expect(screen.queryByTestId('fingerprint')).not.toBeInTheDocument();
  });

  test('shows "no data" error when the repository is not found', async () => {
    mockedFetch.mockResolvedValue(null);
    renderAt('/visualization?repo=ghost');
    expect(await screen.findByText('Error: No data available for this repository')).toBeInTheDocument();
    expect(screen.queryByTestId('treemap')).not.toBeInTheDocument();
    expect(screen.queryByTestId('language-legend')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Circle Pack/ })).not.toBeInTheDocument();
  });

  test('shows the thrown Error message', async () => {
    mockedFetch.mockRejectedValue(new Error('Network exploded'));
    renderAt('/visualization?repo=my-repo');
    expect(await screen.findByText('Error: Network exploded')).toBeInTheDocument();
  });

  test('shows "Unknown error" for non-Error rejections', async () => {
    mockedFetch.mockRejectedValue('weird');
    renderAt('/visualization?repo=my-repo');
    expect(await screen.findByText('Error: Unknown error')).toBeInTheDocument();
  });

  test('ignores results that arrive after unmount (cancelled)', async () => {
    const ok = deferred<LanguageAnalysis | null>();
    const bad = deferred<LanguageAnalysis | null>();
    mockedFetch.mockReturnValueOnce(ok.promise).mockReturnValueOnce(bad.promise);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const first = renderAt('/visualization?repo=my-repo');
    first.unmount();
    await act(async () => {
      ok.resolve(analysis);
    });

    const second = renderAt('/visualization?repo=other');
    second.unmount();
    await act(async () => {
      bad.reject(new Error('late'));
    });

    expect(mockedFetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Error:/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('treemap')).not.toBeInTheDocument();
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});

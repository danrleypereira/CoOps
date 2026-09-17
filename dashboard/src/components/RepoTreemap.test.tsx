import { describe, test, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { RepoTreemap } from './RepoTreemap';

type RepoData = ComponentProps<typeof RepoTreemap>['data'];
type Lang = RepoData['languages'][number];
type RepoFile = NonNullable<Lang['files']>[number];

const file = (name: string, size: number, dir = 'src'): RepoFile => ({
  path: `${dir}/${name}`,
  name,
  size,
  extension: name.includes('.') ? `.${name.split('.').pop()}` : '',
});

const pyFiles = Array.from({ length: 7 }, (_, i) => file(`mod${i}.py`, 1024 * (i + 1)));

const makeRepo = (languages: Lang[]): RepoData => ({
  repository: 'demo',
  owner: 'org',
  branch: 'main',
  total_files: languages.reduce((s, l) => s + l.file_count, 0),
  total_bytes: languages.reduce((s, l) => s + l.total_bytes, 0),
  languages,
});

const repo = makeRepo([
  { language: 'Python', file_count: 7, total_bytes: 60000, percentage: 60, files: pyFiles },
  {
    language: 'TypeScript',
    file_count: 2,
    total_bytes: 30000,
    percentage: 30,
    files: [file('<img src=x onerror=alert(1)>.ts', 2048), file('app.ts', 0)],
  },
  { language: 'Elixir', file_count: 1, total_bytes: 10000, percentage: 10 },
]);

const getTooltip = (): HTMLDivElement | null =>
  document.body.querySelector<HTMLDivElement>('.repo-tooltip');

const getRect = (container: HTMLElement, fill: string): SVGRectElement => {
  const rect = container.querySelector<SVGRectElement>(`rect[fill="${fill}"]`);
  if (!rect) throw new Error(`rect with fill ${fill} not found`);
  return rect;
};

describe('RepoTreemap', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.body.querySelectorAll('.repo-tooltip').forEach(el => el.remove());
  });

  test('mostra estado vazio quando não há linguagens', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(<RepoTreemap data={makeRepo([])} />);

    expect(screen.getByText('No language data available for visualization')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
    expect(getTooltip()).toBeNull();
    // svgRef é nulo no estado vazio -> effect retorna antes do aviso
    expect(warn).not.toHaveBeenCalled();
  });

  test('mostra estado vazio quando data é nulo', () => {
    render(<RepoTreemap data={null as unknown as RepoData} />);
    expect(screen.getByText('No language data available for visualization')).toBeInTheDocument();
  });

  test('renderiza uma célula por linguagem com dimensões e cores', () => {
    const { container } = render(<RepoTreemap data={repo} />);
    const svg = container.querySelector('svg');

    expect(svg).toHaveAttribute('width', '800');
    expect(svg).toHaveAttribute('height', '600');
    expect(svg).toHaveAttribute('viewBox', '0 0 800 600');
    expect(svg?.style.maxWidth).toBe('100%');

    const cells = container.querySelectorAll('svg > g');
    expect(cells).toHaveLength(3);
    cells.forEach(cell => expect(cell.getAttribute('transform')).toMatch(/^translate\(\d+,\d+\)$/));

    const python = getRect(container, '#3572A5');
    const ts = getRect(container, '#2b7489');
    const unknown = getRect(container, '#cccccc'); // Elixir -> Unknown
    expect(python).toHaveAttribute('opacity', '0.85');
    expect(python).toHaveAttribute('stroke-width', '2');

    // Células ordenadas por tamanho: Python ocupa maior área
    const area = (r: SVGRectElement) =>
      Number(r.getAttribute('width')) * Number(r.getAttribute('height'));
    expect(area(python)).toBeGreaterThan(area(ts));
    expect(area(ts)).toBeGreaterThan(area(unknown));

    // Labels com nome e percentual
    const tspans = Array.from(container.querySelectorAll('tspan')).map(t => t.textContent);
    expect(tspans).toEqual(expect.arrayContaining(['Python', '60.0%', 'TypeScript', '30.0%']));

    // Tooltip criado e não visível (o jsdom descarta o cssText multilinha,
    // então apenas garantimos que não está em "block")
    const tooltip = getTooltip();
    expect(tooltip).not.toBeNull();
    expect(tooltip?.className).toBe('repo-tooltip');
    expect(tooltip?.style.display).not.toBe('block');
  });

  test('tooltip exibe detalhes, limita arquivos de amostra e segue o mouse', () => {
    const { container } = render(<RepoTreemap data={repo} />);
    const python = getRect(container, '#3572A5');
    const tooltip = getTooltip() as HTMLDivElement;

    fireEvent.mouseOver(python, { clientX: 100, clientY: 50 });
    expect(tooltip.style.display).toBe('block');
    expect(tooltip.style.left).toBe('115px');
    expect(tooltip.style.top).toBe('65px');
    expect(tooltip).toHaveTextContent('Python');
    expect(tooltip).toHaveTextContent('Files: 7');
    expect(tooltip).toHaveTextContent('Size: 58.59 KB');
    expect(tooltip).toHaveTextContent('Percentage: 60.00%');
    expect(tooltip).toHaveTextContent('Sample files:');
    expect(tooltip).toHaveTextContent('mod0.py (1 KB)');
    expect(tooltip).toHaveTextContent('mod4.py (5 KB)');
    expect(tooltip).not.toHaveTextContent('mod5.py');
    expect(tooltip).toHaveTextContent('... and 2 more files');

    fireEvent.mouseMove(python, { clientX: 200, clientY: 120 });
    expect(tooltip.style.left).toBe('215px');
    expect(tooltip.style.top).toBe('135px');

    fireEvent.mouseOut(python);
    expect(tooltip.style.display).toBe('none');
  });

  test('tooltip escapa HTML dos nomes de arquivos', () => {
    const { container } = render(<RepoTreemap data={repo} />);
    const ts = getRect(container, '#2b7489');
    const tooltip = getTooltip() as HTMLDivElement;

    fireEvent.mouseOver(ts, { clientX: 0, clientY: 0 });
    expect(tooltip.querySelector('img')).toBeNull();
    expect(tooltip.innerHTML).toContain('&lt;img src=x onerror=alert(1)&gt;.ts');
    expect(tooltip).toHaveTextContent('<img src=x onerror=alert(1)>.ts (2 KB)');
    expect(tooltip).toHaveTextContent('app.ts (0 Bytes)');
    expect(tooltip).not.toHaveTextContent('more files');
  });

  test('tooltip escapa o nome da linguagem e omite amostra sem arquivos', () => {
    const data = makeRepo([
      { language: 'Py<b>thon</b>', file_count: 3, total_bytes: 0, percentage: 0 },
    ]);
    const { container } = render(<RepoTreemap data={data} />);
    const rect = container.querySelector('rect') as SVGRectElement;
    const tooltip = getTooltip() as HTMLDivElement;

    fireEvent.mouseOver(rect, { clientX: 0, clientY: 0 });
    expect(tooltip.querySelector('b')).toBeNull();
    expect(tooltip).toHaveTextContent('Py<b>thon</b>');
    expect(tooltip).toHaveTextContent('Size: 0 Bytes');
    expect(tooltip).toHaveTextContent('Percentage: 0.00%');
    expect(tooltip).not.toHaveTextContent('Sample files');
  });

  test('trunca o nome em células estreitas e omite percentual em células baixas', () => {
    const data = makeRepo([
      { language: 'JavaScript', file_count: 1, total_bytes: 100, percentage: 100 },
    ]);
    const { container } = render(<RepoTreemap data={data} width={90} height={40} />);

    // largura 82 (>50 e <=100), altura 32 (>30 e <=50)
    const tspans = container.querySelectorAll('tspan');
    expect(tspans).toHaveLength(1);
    expect(tspans[0]).toHaveTextContent('JavaScri');
    expect(tspans[0]).toHaveAttribute('font-size', String(82 / 8));
  });

  test('não renderiza labels em células pequenas', () => {
    const data = makeRepo([
      { language: 'Go', file_count: 1, total_bytes: 100, percentage: 100 },
    ]);
    const { container } = render(<RepoTreemap data={data} width={40} height={40} />);

    expect(container.querySelectorAll('rect')).toHaveLength(1);
    expect(container.querySelector('text')).not.toBeNull();
    expect(container.querySelectorAll('tspan')).toHaveLength(0);
  });

  test('recria o gráfico e o tooltip ao mudar props e remove o tooltip ao desmontar', () => {
    const { container, rerender, unmount } = render(<RepoTreemap data={repo} />);
    const firstTooltip = getTooltip();

    const smaller = makeRepo([repo.languages[0]]);
    rerender(<RepoTreemap data={smaller} width={400} height={300} />);

    expect(container.querySelectorAll('svg > g')).toHaveLength(1);
    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 400 300');
    const tooltips = document.body.querySelectorAll('.repo-tooltip');
    expect(tooltips).toHaveLength(1);
    expect(tooltips[0]).not.toBe(firstTooltip);
    expect(firstTooltip?.isConnected).toBe(false);

    unmount();
    expect(getTooltip()).toBeNull();
  });
});

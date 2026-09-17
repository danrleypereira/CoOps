import { describe, test, expect, vi, beforeAll, afterAll, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { RepoFingerprint } from './RepoFingerprint';

type RepoData = ComponentProps<typeof RepoFingerprint>['data'];
type Lang = RepoData['languages'][number];
type RepoFile = NonNullable<Lang['files']>[number];

const file = (path: string, size: number): RepoFile => {
  const name = path.split('/').pop() ?? path;
  return { path, name, size, extension: name.includes('.') ? `.${name.split('.').pop()}` : '' };
};

const lang = (language: string, files?: RepoFile[]): Lang => ({
  language,
  file_count: files?.length ?? 0,
  total_bytes: files?.reduce((s, f) => s + f.size, 0) ?? 0,
  percentage: 0,
  files,
});

const makeRepo = (languages: Lang[]): RepoData => ({
  repository: 'demo',
  owner: 'org',
  branch: 'main',
  total_files: languages.reduce((s, l) => s + l.file_count, 0),
  total_bytes: languages.reduce((s, l) => s + l.total_bytes, 0),
  languages,
});

const DEEP_DIR = 'src/components/charts/deep';

const buildRepo = (jsSize: number): RepoData => makeRepo([
  lang('TypeScript', Array.from({ length: 7 }, (_, i) => file(`${DEEP_DIR}/c${i}.ts`, 40000))),
  lang('Python', [file('lib/a.py', 30000), file('lib/b.py', 30000)]),
  lang('JavaScript', jsSize > 12000
    ? [file('lib/c.js', jsSize), file('lib/e.js', 2000)]
    : [file('lib/c.js', jsSize)]),
  lang('Elixir', [file('lib/d.ex', 5000)]),
  // Arquivos na raiz: sem "/" e com "/" inicial
  lang('Markdown', [file('README.md', 6000), file('LICENSE', 0)]),
  lang('Shell', [file('/setup.sh', 300)]),
  // Linguagem sem lista de arquivos é ignorada
  lang('Go'),
]);

// Layout do d3.pack (800x600, raio 280):
//   dirs: deep r≈153, lib r≈119, root r≈34
//   langs: TypeScript r≈149, Python r≈69, JavaScript r≈44, Markdown r≈22, Elixir r≈20, Shell r≈5
const repo = buildRepo(22000);

const COLORS = {
  dir: 'rgba(50, 50, 50, 0.3)',
  TypeScript: '#2b7489',
  Python: '#3572A5',
  JavaScript: '#f1e05a',
  Markdown: '#083fa1',
  Shell: '#89e051',
  Unknown: '#cccccc',
};

const getTooltip = (): HTMLDivElement | null =>
  document.body.querySelector<HTMLDivElement>('.repo-tooltip');

const circlesByFill = (container: HTMLElement, fill: string): SVGCircleElement[] =>
  Array.from(container.querySelectorAll<SVGCircleElement>('circle'))
    .filter(c => c.getAttribute('fill') === fill);

const circleByFill = (container: HTMLElement, fill: string): SVGCircleElement => {
  const [circle] = circlesByFill(container, fill);
  if (!circle) throw new Error(`circle with fill ${fill} not found`);
  return circle;
};

const radius = (c: SVGCircleElement): number => Number(c.getAttribute('r'));

const labelTexts = (container: HTMLElement): string[] =>
  Array.from(container.querySelectorAll('svg > g:not(.zoom-controls) text'))
    .map(t => Array.from(t.querySelectorAll('tspan')).map(s => s.textContent).join('|'))
    .filter(Boolean);

const getSvg = (container: HTMLElement): SVGSVGElement => {
  const svg = container.querySelector('svg');
  if (!svg) throw new Error('svg not found');
  return svg;
};

const zoomButtons = (container: HTMLElement): SVGGElement[] =>
  Array.from(container.querySelectorAll<SVGGElement>('.zoom-controls .zoom-btn'));

describe('RepoFingerprint', () => {
  // jsdom não implementa SVGSVGElement.width/height (usados pelo extent padrão do d3-zoom)
  beforeAll(() => {
    for (const dim of ['width', 'height'] as const) {
      Object.defineProperty(SVGSVGElement.prototype, dim, {
        configurable: true,
        get(this: SVGSVGElement) {
          return { baseVal: { value: Number(this.getAttribute(dim)) || 0 } };
        },
      });
    }
  });

  afterAll(() => {
    Reflect.deleteProperty(SVGSVGElement.prototype, 'width');
    Reflect.deleteProperty(SVGSVGElement.prototype, 'height');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.querySelectorAll('.repo-tooltip').forEach(el => el.remove());
  });

  test('mostra estado vazio sem linguagens ou sem dados', () => {
    const { container, rerender } = render(<RepoFingerprint data={makeRepo([])} />);
    expect(screen.getByText('No language data available for visualization')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
    expect(getTooltip()).toBeNull();

    rerender(<RepoFingerprint data={null as unknown as RepoData} />);
    expect(screen.getByText('No language data available for visualization')).toBeInTheDocument();
  });

  test('renderiza controles, indicador de zoom e dimensões padrão', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const svg = getSvg(container);

    expect(screen.getByText(/🔍 100%/)).toBeInTheDocument();
    expect(screen.getByText('💡 Controles:')).toBeInTheDocument();
    expect(svg).toHaveAttribute('width', '800');
    expect(svg).toHaveAttribute('height', '600');

    const controls = container.querySelector('.zoom-controls');
    expect(controls).toHaveAttribute('transform', 'translate(740, 20)');
    expect(zoomButtons(container).map(b => b.textContent)).toEqual(['+', '−', '⟲']);

    const inner = container.querySelector('svg > g > g');
    expect(inner).toHaveAttribute('transform', 'translate(400,300)');
  });

  test('agrupa arquivos por diretório e colore linguagens', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const circles = container.querySelectorAll('circle');

    // raiz + 3 diretórios (deep, lib, root) + 6 linguagens (Go ignorado)
    expect(circles).toHaveLength(10);

    const root = circles[0];
    expect(root).toHaveAttribute('fill', 'none');
    expect(root).toHaveAttribute('stroke', '#444');
    expect(root).toHaveAttribute('stroke-width', '2');
    expect(root).toHaveAttribute('r', '280');
    expect(root.style.cursor).toBe('default');

    const dirs = circlesByFill(container, COLORS.dir);
    expect(dirs).toHaveLength(3);
    dirs.forEach(d => {
      expect(d).toHaveAttribute('stroke', '#888');
      expect(d).toHaveAttribute('stroke-width', '2.5');
      expect(d).toHaveAttribute('opacity', '1');
      expect(d.style.cursor).toBe('pointer');
    });

    const ts = circleByFill(container, COLORS.TypeScript);
    expect(ts).toHaveAttribute('stroke', COLORS.TypeScript);
    expect(ts).toHaveAttribute('stroke-width', '1.5');
    expect(ts).toHaveAttribute('opacity', '0.85');

    // Linguagem sem cor mapeada usa Unknown no fill e no stroke
    const elixir = circleByFill(container, COLORS.Unknown);
    expect(elixir).toHaveAttribute('stroke', COLORS.Unknown);

    for (const color of [COLORS.Python, COLORS.JavaScript, COLORS.Markdown, COLORS.Shell]) {
      expect(circlesByFill(container, color)).toHaveLength(1);
    }
    expect(radius(ts)).toBeGreaterThan(radius(circleByFill(container, COLORS.Python)));
  });

  test('renderiza labels conforme o tamanho dos círculos', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const labels = labelTexts(container);

    // diretório com nome longo é encurtado para o último segmento
    expect(labels).toContain('📁 deep|7 files');
    expect(labels).toContain('📁 lib|5 files');
    expect(labels.some(l => l.includes(DEEP_DIR))).toBe(false);
    // diretório raiz pequeno (r<=50) não tem label
    expect(labels.some(l => l.includes('📁 root'))).toBe(false);
    // linguagem grande: nome completo; média (35<r<=50): nome truncado em 6
    expect(labels).toContain('TypeScript|7 files');
    expect(labels).toContain('Python|2 files');
    expect(labels).toContain('JavaSc|2 files');
    // círculos pequenos (r<=25) sem label
    expect(labels.some(l => l.startsWith('Markdown') || l.startsWith('Elix'))).toBe(false);
    expect(labels).toHaveLength(5);
  });

  test('usa abreviação de 3 letras para linguagens pequenas (25<r<=35)', () => {
    const { container } = render(<RepoFingerprint data={buildRepo(12000)} />);
    const js = circleByFill(container, COLORS.JavaScript);
    expect(radius(js)).toBeGreaterThan(25);
    expect(radius(js)).toBeLessThanOrEqual(35);
    expect(labelTexts(container)).toContain('Jav');
  });

  test('tooltip de diretório mostra totais e segue o mouse', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const tooltip = getTooltip() as HTMLDivElement;
    const lib = circlesByFill(container, COLORS.dir)
      .find(c => Math.round(radius(c)) === 119 || Math.round(radius(c)) === 120);
    if (!lib) throw new Error('lib directory circle not found');

    fireEvent.mouseOver(lib, { clientX: 10, clientY: 20 });
    expect(tooltip.style.display).toBe('block');
    expect(tooltip.style.left).toBe('25px');
    expect(tooltip.style.top).toBe('35px');
    expect(tooltip).toHaveTextContent('📁 lib');
    expect(tooltip).toHaveTextContent('Total Files: 5');
    expect(tooltip).toHaveTextContent('Total Size: 86.91 KB');
    expect(tooltip).toHaveTextContent('Languages: 3');
    expect(tooltip).toHaveTextContent('Python, JavaScript, Elixir');

    fireEvent.mouseMove(lib, { clientX: 50, clientY: 60 });
    expect(tooltip.style.left).toBe('65px');
    expect(tooltip.style.top).toBe('75px');

    fireEvent.mouseOut(lib);
    expect(tooltip.style.display).toBe('none');
  });

  test('tooltip de linguagem lista até 5 arquivos de amostra', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const tooltip = getTooltip() as HTMLDivElement;
    const ts = circleByFill(container, COLORS.TypeScript);

    fireEvent.mouseOver(ts, { clientX: 0, clientY: 0 });
    expect(tooltip.style.display).toBe('block');
    expect(tooltip).not.toHaveTextContent('📁');
    expect(tooltip).toHaveTextContent('Files: 7');
    expect(tooltip).toHaveTextContent('Size: 273.44 KB');
    expect(tooltip).toHaveTextContent('Sample files:');
    expect(tooltip).toHaveTextContent('c0.ts (39.06 KB)');
    expect(tooltip).toHaveTextContent('c4.ts');
    expect(tooltip).not.toHaveTextContent('c5.ts');
    expect(tooltip).toHaveTextContent('... and 2 more files');

    fireEvent.mouseOut(ts);
    expect(tooltip.style.display).toBe('none');

    const md = circleByFill(container, COLORS.Markdown);
    fireEvent.mouseOver(md, { clientX: 0, clientY: 0 });
    expect(tooltip).toHaveTextContent('Files: 2');
    expect(tooltip).toHaveTextContent('README.md (5.86 KB)');
    expect(tooltip).toHaveTextContent('LICENSE (0 Bytes)');
    expect(tooltip).not.toHaveTextContent('more files');
  });

  test('tooltip do diretório raiz agrupa arquivos sem diretório', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const tooltip = getTooltip() as HTMLDivElement;
    const rootDir = circlesByFill(container, COLORS.dir)
      .reduce((a, b) => (radius(a) < radius(b) ? a : b));

    fireEvent.mouseOver(rootDir, { clientX: 0, clientY: 0 });
    expect(tooltip).toHaveTextContent('📁 root');
    expect(tooltip).toHaveTextContent('Total Files: 3');
    expect(tooltip).toHaveTextContent('Languages: 2');
    expect(tooltip).toHaveTextContent('Markdown, Shell');
  });

  test('nó raiz ignora hover', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const tooltip = getTooltip() as HTMLDivElement;
    const [root] = Array.from(container.querySelectorAll('circle'));
    const ts = circleByFill(container, COLORS.TypeScript);

    fireEvent.mouseOver(root, { clientX: 0, clientY: 0 });
    expect(tooltip.style.display).not.toBe('block');
    expect(tooltip.innerHTML).toBe('');

    fireEvent.mouseOver(ts, { clientX: 0, clientY: 0 });
    expect(tooltip.style.display).toBe('block');
    // mouseout no nó raiz retorna antes de esconder o tooltip
    fireEvent.mouseOut(root);
    expect(tooltip.style.display).toBe('block');
  });

  test('tooltips escapam HTML em nomes de diretórios, linguagens e arquivos', () => {
    const data = makeRepo([
      lang('<em>Lang</em>', [file('docs<img src=x onerror=alert(1)>/a<b>.txt', 100)]),
    ]);
    const { container } = render(<RepoFingerprint data={data} />);
    const tooltip = getTooltip() as HTMLDivElement;

    const dir = circleByFill(container, COLORS.dir);
    fireEvent.mouseOver(dir, { clientX: 0, clientY: 0 });
    expect(tooltip.querySelector('img')).toBeNull();
    expect(tooltip.querySelector('em')).toBeNull();
    expect(tooltip.innerHTML).toContain('docs&lt;img src=x onerror=alert(1)&gt;');
    expect(tooltip).toHaveTextContent('📁 docs<img src=x onerror=alert(1)>');
    expect(tooltip).toHaveTextContent('<em>Lang</em>');

    const langCircle = circleByFill(container, COLORS.Unknown);
    fireEvent.mouseOver(langCircle, { clientX: 0, clientY: 0 });
    expect(tooltip.querySelector('em')).toBeNull();
    expect(tooltip.querySelector('b')).toBeNull();
    expect(tooltip.innerHTML).toContain('&lt;em&gt;Lang&lt;/em&gt;');
    expect(tooltip).toHaveTextContent('a<b>.txt (100 Bytes)');
  });

  test('zoom via roda do mouse atualiza indicador e transform', () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const svg = getSvg(container);

    fireEvent.wheel(svg, { deltaY: -100, clientX: 400, clientY: 300 });

    expect(screen.getByText(/🔍 115%/)).toBeInTheDocument();
    const zoomContainer = container.querySelector('svg > g');
    expect(zoomContainer?.getAttribute('transform')).toMatch(/scale\(1\.148/);
  });

  test('botões de zoom aproximam, afastam e resetam', async () => {
    const { container } = render(<RepoFingerprint data={repo} />);
    const [zoomIn, zoomOut, reset] = zoomButtons(container);

    fireEvent.click(zoomIn);
    await waitFor(() => expect(screen.getByText(/🔍 130%/)).toBeInTheDocument());

    fireEvent.click(zoomOut);
    await waitFor(() => expect(screen.getByText(/🔍 91%/)).toBeInTheDocument());

    fireEvent.click(reset);
    await waitFor(() => expect(container.querySelector('svg > g')?.getAttribute('transform'))
      .toBe('translate(0,0) scale(1)'));
    expect(screen.getByText(/🔍 100%/)).toBeInTheDocument();
  });

  test('redesenha ao mudar props e remove tooltip ao desmontar', () => {
    const { container, rerender, unmount } = render(<RepoFingerprint data={repo} />);
    const firstTooltip = getTooltip();

    const small = makeRepo([lang('Python', [file('app/main.py', 1000)])]);
    rerender(<RepoFingerprint data={small} width={400} height={300} />);

    const svg = getSvg(container);
    expect(svg).toHaveAttribute('width', '400');
    expect(svg).toHaveAttribute('height', '300');
    expect(container.querySelectorAll('circle')).toHaveLength(3);
    expect(container.querySelector('.zoom-controls')).toHaveAttribute('transform', 'translate(340, 20)');
    expect(container.querySelectorAll('.zoom-controls')).toHaveLength(1);

    const tooltips = document.body.querySelectorAll('.repo-tooltip');
    expect(tooltips).toHaveLength(1);
    expect(firstTooltip?.isConnected).toBe(false);

    unmount();
    expect(getTooltip()).toBeNull();
  });
});

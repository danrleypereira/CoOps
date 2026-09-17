import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import LineChart from './LineChart';
import { LineChart as LineChartFromIndex } from './index';

type Props = ComponentProps<typeof LineChart>;

const data: Props['data'] = [
  { date: '2024-01-01T00:00:00Z', value: 5 },
  { date: new Date('2024-01-11T00:00:00Z'), value: 10 },
  { date: '2024-01-21T00:00:00Z', value: 0 },
];

function mainGroup(container: HTMLElement): SVGGElement {
  const g = container.querySelector<SVGGElement>('svg > g');
  if (!g) throw new Error('grupo principal não encontrado');
  return g;
}

function paths(container: HTMLElement): SVGPathElement[] {
  return Array.from(container.querySelectorAll<SVGPathElement>('svg > g > path'));
}

function dots(container: HTMLElement): SVGCircleElement[] {
  return Array.from(container.querySelectorAll<SVGCircleElement>('svg > g > circle'));
}

function axisLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg > g > text')).map(
    (t) => t.textContent ?? ''
  );
}

describe('LineChart', () => {
  afterEach(() => {
    document.documentElement.style.removeProperty('--color-blue-trust');
  });

  test('é reexportado pelo index', () => {
    expect(LineChartFromIndex).toBe(LineChart);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<LineChart data={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando data é undefined', () => {
    const props = { data: undefined } as unknown as Props;
    const { container } = render(<LineChart {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define atributos padrão do svg', () => {
    const { container } = render(<LineChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '700');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 700 400');
    expect(svg).toHaveAttribute('aria-label', 'Line chart');
    expect(mainGroup(container)).toHaveAttribute('transform', 'translate(60,20)');
  });

  test('desenha a linha e pontos (padrão) posicionados pelas escalas', () => {
    const { container } = render(<LineChart data={data} />);
    const ps = paths(container);
    expect(ps).toHaveLength(1);
    expect(ps[0]).toHaveAttribute('fill', 'none');
    expect(ps[0]).toHaveAttribute('stroke-width', '2.5');
    expect(ps[0].getAttribute('d')).toMatch(/^M0,/);

    const cs = dots(container);
    expect(cs).toHaveLength(3);
    // innerWidth = 700 - 60 - 30 = 610 ; innerHeight = 400 - 20 - 60 = 320
    expect(cs.map((c) => Number(c.getAttribute('cx')))).toEqual([0, 305, 610]);
    expect(cs.map((c) => Number(c.getAttribute('cy')))).toEqual([160, 0, 320]);
    cs.forEach((c) => {
      expect(c).toHaveAttribute('r', '4');
      expect(c).toHaveAttribute('stroke', '#fff');
    });
  });

  test('showDots=false não desenha pontos', () => {
    const { container } = render(<LineChart data={data} showDots={false} />);
    expect(dots(container)).toHaveLength(0);
    expect(paths(container)).toHaveLength(1);
  });

  test('showArea desenha a área antes da linha', () => {
    const { container } = render(<LineChart data={data} showArea color="#ff00ff" />);
    const ps = paths(container);
    expect(ps).toHaveLength(2);
    const [areaPath, linePath] = ps;
    expect(areaPath).toHaveAttribute('fill', '#ff00ff');
    expect(areaPath).toHaveAttribute('opacity', '0.2');
    expect(areaPath.getAttribute('d')).toMatch(/Z$/);
    expect(linePath).toHaveAttribute('fill', 'none');
    expect(linePath).toHaveAttribute('stroke', '#ff00ff');
  });

  test('eixo X formata datas e rotaciona rótulos', () => {
    const { container } = render(<LineChart data={data} />);
    const xAxis = mainGroup(container).querySelector(':scope > g');
    const labels = Array.from(xAxis?.querySelectorAll('text') ?? []);
    expect(labels.length).toBeGreaterThan(0);
    labels.forEach((l) => {
      expect(l.textContent).toMatch(/^[A-Z][a-z]{2} \d{2}$/);
      expect(l).toHaveAttribute('transform', 'rotate(-45)');
    });
    expect(labels.map((l) => l.textContent)).toContain('Jan 11');
  });

  test('adiciona grade sem rótulos com opacidade reduzida', () => {
    const { container } = render(<LineChart data={data} />);
    const grid = container.querySelector('g.grid');
    expect(grid).toHaveAttribute('opacity', '0.1');
    const gridTexts = Array.from(grid?.querySelectorAll('text') ?? []);
    expect(gridTexts.length).toBeGreaterThan(0);
    gridTexts.forEach((t) => expect(t.textContent).toBe(''));
    // linhas da grade atravessam toda a largura
    grid?.querySelectorAll('.tick line').forEach((l) => {
      expect(l).toHaveAttribute('x2', '610');
    });
  });

  test('estiliza domínio dos eixos', () => {
    const { container } = render(<LineChart data={data} />);
    const axes = mainGroup(container).querySelectorAll(':scope > g:not(.grid)');
    axes.forEach((a) => {
      expect(a.querySelector('.domain')).toHaveAttribute('stroke', '#475569');
    });
  });

  test.each([
    [{ xLabel: 'Data', yLabel: 'Commits' }, ['Data', 'Commits']],
    [{ xLabel: 'Data' }, ['Data']],
    [{ yLabel: 'Commits' }, ['Commits']],
    [{}, []],
  ])('rótulos de eixo %o', (labels, expected) => {
    const { container } = render(<LineChart data={data} {...labels} />);
    expect(axisLabels(container)).toEqual(expected);
  });

  describe('cor', () => {
    test('usa cor personalizada', () => {
      document.documentElement.style.setProperty('--color-blue-trust', '#111111');
      const { container } = render(<LineChart data={data} color="#222222" />);
      expect(paths(container)[0]).toHaveAttribute('stroke', '#222222');
      dots(container).forEach((c) => expect(c).toHaveAttribute('fill', '#222222'));
    });

    test('usa a variável CSS do tema', () => {
      document.documentElement.style.setProperty('--color-blue-trust', '#111111');
      const { container } = render(<LineChart data={data} />);
      expect(paths(container)[0]).toHaveAttribute('stroke', '#111111');
    });

    test('usa fallback sem variável CSS', () => {
      const { container } = render(<LineChart data={data} />);
      expect(paths(container)[0]).toHaveAttribute('stroke', '#1E88E5');
    });
  });

  test('mouseover/mouseout alteram o raio do ponto', () => {
    const { container } = render(<LineChart data={data} />);
    const dot = dots(container)[1];
    fireEvent.mouseOver(dot);
    expect(dot).toHaveAttribute('r', '6');
    fireEvent.mouseOut(dot);
    expect(dot).toHaveAttribute('r', '4');
  });

  test('todos os valores zero não quebram o gráfico', () => {
    const { container } = render(
      <LineChart
        data={[
          { date: '2024-01-01', value: 0 },
          { date: '2024-01-02', value: 0 },
        ]}
      />
    );
    expect(dots(container)).toHaveLength(2);
    dots(container).forEach((c) => expect(Number.isFinite(Number(c.getAttribute('cy')))).toBe(true));
  });

  test('redesenha sem duplicar ao mudar props', () => {
    const { container, rerender } = render(<LineChart data={data} />);
    rerender(<LineChart data={data.slice(0, 2)} showArea width={500} />);
    expect(container.querySelectorAll('svg > g')).toHaveLength(1);
    expect(dots(container)).toHaveLength(2);
    expect(paths(container)).toHaveLength(2);
    expect(container.querySelector('svg')).toHaveAttribute('width', '500');
  });
});

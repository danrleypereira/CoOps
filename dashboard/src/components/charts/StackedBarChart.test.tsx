import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import StackedBarChart from './StackedBarChart';
import { StackedBarChart as StackedBarChartFromIndex } from './index';

type Props = ComponentProps<typeof StackedBarChart>;

const data: Props['data'] = [
  { label: 'repo-a', commits: 10, issues: 5, prs: 5 },
  { label: 'repo-b', commits: 20, issues: 10, prs: 10 },
];
const keys = ['commits', 'issues', 'prs'];

function layers(container: HTMLElement): SVGGElement[] {
  return Array.from(container.querySelectorAll<SVGGElement>('g.layer'));
}

function rects(container: HTMLElement): SVGRectElement[] {
  return Array.from(container.querySelectorAll<SVGRectElement>('g.layer > rect'));
}

function legendRows(container: HTMLElement): Element[] {
  return Array.from(container.querySelectorAll('svg > g:nth-of-type(2) > g'));
}

function axisLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg > g:first-of-type > text')).map(
    (t) => t.textContent ?? ''
  );
}

const CSS_VARS = ['--color-blue-trust', '--color-green-growth', '--color-amber-accent'];

describe('StackedBarChart', () => {
  afterEach(() => {
    CSS_VARS.forEach((v) => document.documentElement.style.removeProperty(v));
  });

  test('é reexportado pelo index', () => {
    expect(StackedBarChartFromIndex).toBe(StackedBarChart);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<StackedBarChart data={[]} keys={keys} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando keys está vazio', () => {
    const { container } = render(<StackedBarChart data={data} keys={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando data ou keys são undefined', () => {
    const noData = { data: undefined, keys } as unknown as Props;
    const noKeys = { data, keys: undefined } as unknown as Props;
    const { container: c1 } = render(<StackedBarChart {...noData} />);
    const { container: c2 } = render(<StackedBarChart {...noKeys} />);
    expect(c1.querySelector('svg')?.childNodes.length).toBe(0);
    expect(c2.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define atributos padrão do svg', () => {
    const { container } = render(<StackedBarChart data={data} keys={keys} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '700');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 700 400');
    expect(container.querySelector('svg > g')).toHaveAttribute('transform', 'translate(60,20)');
  });

  test('empilha uma camada por chave e um retângulo por item', () => {
    const { container } = render(<StackedBarChart data={data} keys={keys} />);
    expect(layers(container)).toHaveLength(3);
    const rs = rects(container);
    expect(rs).toHaveLength(6);

    // innerHeight = 400 - 20 - 80 = 300 ; domínio y [0, 40]
    const byLayer = layers(container).map((l) =>
      Array.from(l.querySelectorAll('rect')).map((r) => ({
        y: Number(r.getAttribute('y')),
        h: Number(r.getAttribute('height')),
      }))
    );
    // repo-b: commits 0→20, issues 20→30, prs 30→40
    expect(byLayer.map((l) => l[1])).toEqual([
      { y: 150, h: 150 },
      { y: 75, h: 75 },
      { y: 0, h: 75 },
    ]);
    // repo-a: commits 0→10, issues 10→15, prs 15→20
    expect(byLayer.map((l) => l[0])).toEqual([
      { y: 225, h: 75 },
      { y: 187.5, h: 37.5 },
      { y: 150, h: 37.5 },
    ]);

    // barras da mesma categoria compartilham x e largura
    const xs = layers(container).map((l) => l.querySelector('rect')?.getAttribute('x'));
    expect(new Set(xs).size).toBe(1);
    expect(new Set(rs.map((r) => r.getAttribute('width'))).size).toBe(1);
    rs.forEach((r) => expect(r).toHaveAttribute('opacity', '0.9'));
  });

  test('cores padrão (fallback) por camada e na legenda', () => {
    const { container } = render(<StackedBarChart data={data} keys={keys} />);
    const expected = ['#1E88E5', '#43A047', '#FFB300'];
    expect(layers(container).map((l) => l.getAttribute('fill'))).toEqual(expected);
    expect(
      legendRows(container).map((r) => r.querySelector('rect')?.getAttribute('fill'))
    ).toEqual(expected);
  });

  test('cores padrão vêm das variáveis CSS e incluem cores fixas extras', () => {
    document.documentElement.style.setProperty('--color-blue-trust', '#000001');
    document.documentElement.style.setProperty('--color-green-growth', '#000002');
    document.documentElement.style.setProperty('--color-amber-accent', '#000003');
    const fiveKeys = ['a', 'b', 'c', 'd', 'e'];
    const { container } = render(
      <StackedBarChart data={[{ label: 'x', a: 1, b: 1, c: 1, d: 1, e: 1 }]} keys={fiveKeys} />
    );
    expect(layers(container).map((l) => l.getAttribute('fill'))).toEqual([
      '#000001',
      '#000002',
      '#000003',
      '#9C27B0',
      '#F44336',
    ]);
  });

  test('cores personalizadas', () => {
    const colors = ['#111111', '#222222', '#333333'];
    const { container } = render(<StackedBarChart data={data} keys={keys} colors={colors} />);
    expect(layers(container).map((l) => l.getAttribute('fill'))).toEqual(colors);
  });

  test('legenda mostra uma linha por chave', () => {
    const { container } = render(<StackedBarChart data={data} keys={keys} width={700} />);
    expect(container.querySelector('svg > g:nth-of-type(2)')).toHaveAttribute(
      'transform',
      'translate(600, 20)'
    );
    const rows = legendRows(container);
    expect(rows.map((r) => r.querySelector('text')?.textContent)).toEqual(keys);
    expect(rows.map((r) => r.getAttribute('transform'))).toEqual([
      'translate(0, 0)',
      'translate(0, 25)',
      'translate(0, 50)',
    ]);
  });

  test('eixo X mostra rótulos rotacionados', () => {
    const { container } = render(<StackedBarChart data={data} keys={keys} />);
    const xAxis = container.querySelector('svg > g:first-of-type > g:not(.layer)');
    const labels = Array.from(xAxis?.querySelectorAll('text') ?? []);
    expect(labels.map((l) => l.textContent)).toEqual(['repo-a', 'repo-b']);
    labels.forEach((l) => expect(l).toHaveAttribute('transform', 'rotate(-45)'));
    container
      .querySelectorAll('.domain')
      .forEach((d) => expect(d).toHaveAttribute('stroke', '#475569'));
  });

  test.each([
    [{ xLabel: 'Repositório', yLabel: 'Total' }, ['Repositório', 'Total']],
    [{ xLabel: 'Repositório' }, ['Repositório']],
    [{ yLabel: 'Total' }, ['Total']],
    [{}, []],
  ])('rótulos de eixo %o', (labels, expected) => {
    const { container } = render(<StackedBarChart data={data} keys={keys} {...labels} />);
    expect(axisLabels(container)).toEqual(expected);
  });

  test('mouseover/mouseout alteram a opacidade do segmento', () => {
    const { container } = render(<StackedBarChart data={data} keys={keys} />);
    const rect = rects(container)[3];
    fireEvent.mouseOver(rect);
    expect(rect).toHaveAttribute('opacity', '1');
    fireEvent.mouseOut(rect);
    expect(rect).toHaveAttribute('opacity', '0.9');
  });

  test('chave presente é desenhada mesmo com outra chave ausente', () => {
    const { container } = render(
      <StackedBarChart data={[{ label: 'r', commits: 4 }]} keys={['commits', 'issues']} />
    );
    const rs = rects(container);
    expect(rs).toHaveLength(2);
    expect(Number(rs[0].getAttribute('height'))).toBe(300);
  });

  test('todos os valores zero geram segmentos de altura 0', () => {
    const { container } = render(
      <StackedBarChart data={[{ label: 'r', commits: 0, issues: 0 }]} keys={['commits', 'issues']} />
    );
    rects(container).forEach((r) => expect(r).toHaveAttribute('height', '0'));
  });

  // Regressão #81: d3.stack convertia chaves ausentes em NaN, gerando atributos
  // SVG inválidos (y/height = NaN) em vez de segmentos de altura 0.
  test('chaves ausentes geram segmentos com altura 0', () => {
    const { container } = render(
      <StackedBarChart data={[{ label: 'r', commits: 4 }]} keys={['commits', 'issues']} />
    );
    const rs = rects(container);
    expect(rs).toHaveLength(2);
    expect(Number(rs[0].getAttribute('height'))).toBeGreaterThan(0);
    const missing = rs[1];
    expect(missing).toHaveAttribute('height', '0');
    rs.forEach((r) => {
      expect(r.getAttribute('y')).not.toBe('NaN');
      expect(r.getAttribute('height')).not.toBe('NaN');
    });
  });

  test('redesenha sem duplicar ao mudar props', () => {
    const { container, rerender } = render(<StackedBarChart data={data} keys={keys} />);
    rerender(<StackedBarChart data={data} keys={['commits']} yLabel="Y" />);
    expect(layers(container)).toHaveLength(1);
    expect(rects(container)).toHaveLength(2);
    expect(legendRows(container)).toHaveLength(1);
    expect(axisLabels(container)).toEqual(['Y']);
  });
});

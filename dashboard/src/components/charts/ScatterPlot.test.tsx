import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import ScatterPlot from './ScatterPlot';
import { ScatterPlot as ScatterPlotFromIndex } from './index';

type Props = ComponentProps<typeof ScatterPlot>;

const data: Props['data'] = [
  { x: 0, y: 0, label: 'origem' },
  { x: 5, y: 10, category: 'new' },
  { x: 10, y: 5, category: 'established' },
  { x: 2, y: 4, category: 'veteran' },
  { x: 3, y: 3, category: 'new' },
];

function dots(container: HTMLElement): SVGCircleElement[] {
  return Array.from(container.querySelectorAll<SVGCircleElement>('svg > g:first-of-type > circle'));
}

function legendRows(container: HTMLElement): Element[] {
  return Array.from(container.querySelectorAll('svg > g:nth-of-type(2) > g'));
}

function axisLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg > g:first-of-type > text')).map(
    (t) => t.textContent ?? ''
  );
}

const CSS_VARS = ['--color-blue-trust', '--color-amber-accent'];

describe('ScatterPlot', () => {
  afterEach(() => {
    CSS_VARS.forEach((v) => document.documentElement.style.removeProperty(v));
  });

  test('é reexportado pelo index', () => {
    expect(ScatterPlotFromIndex).toBe(ScatterPlot);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<ScatterPlot data={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando data é undefined', () => {
    const props = { data: undefined } as unknown as Props;
    const { container } = render(<ScatterPlot {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define atributos padrão do svg', () => {
    const { container } = render(<ScatterPlot data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '600');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 600 400');
    expect(container.querySelector('svg > g')).toHaveAttribute('transform', 'translate(60,20)');
  });

  test('posiciona um ponto por item conforme as escalas', () => {
    const { container } = render(<ScatterPlot data={data} />);
    const cs = dots(container);
    expect(cs).toHaveLength(5);
    // innerWidth = 600 - 60 - 100 = 440 ; innerHeight = 400 - 20 - 60 = 320
    expect(cs.map((c) => Number(c.getAttribute('cx')))).toEqual([0, 220, 440, 88, 132]);
    expect(cs.map((c) => Number(c.getAttribute('cy')))).toEqual([320, 0, 160, 192, 224]);
    cs.forEach((c) => {
      expect(c).toHaveAttribute('r', '6');
      expect(c).toHaveAttribute('opacity', '0.7');
      expect(c).toHaveAttribute('stroke', '#fff');
    });
  });

  test('cores por categoria: padrão, fallback e sem categoria', () => {
    const { container } = render(<ScatterPlot data={data} />);
    expect(dots(container).map((c) => c.getAttribute('fill'))).toEqual([
      '#64B5F6', // sem categoria
      '#1E88E5', // new
      '#FFB300', // established
      '#64B5F6', // categoria desconhecida
      '#1E88E5',
    ]);
  });

  test('cores padrão vêm das variáveis CSS do tema', () => {
    document.documentElement.style.setProperty('--color-blue-trust', '#0000ff');
    document.documentElement.style.setProperty('--color-amber-accent', '#ffaa00');
    const { container } = render(<ScatterPlot data={data} />);
    const fills = dots(container).map((c) => c.getAttribute('fill'));
    expect(fills[1]).toBe('#0000ff');
    expect(fills[2]).toBe('#ffaa00');
  });

  test('cores personalizadas têm prioridade e caem no padrão quando ausentes', () => {
    const colors = { veteran: '#123123', new: '#abcabc' };
    const { container } = render(<ScatterPlot data={data} colors={colors} />);
    expect(dots(container).map((c) => c.getAttribute('fill'))).toEqual([
      '#64B5F6',
      '#abcabc',
      '#FFB300',
      '#123123',
      '#abcabc',
    ]);
    const legendFills = legendRows(container).map((r) =>
      r.querySelector('circle')?.getAttribute('fill')
    );
    expect(legendFills).toEqual(['#abcabc', '#FFB300', '#123123']);
  });

  test('legenda lista categorias únicas na ordem de aparição', () => {
    const { container } = render(<ScatterPlot data={data} width={600} />);
    const legend = container.querySelector('svg > g:nth-of-type(2)');
    expect(legend).toHaveAttribute('transform', 'translate(510, 20)');
    const rows = legendRows(container);
    expect(rows.map((r) => r.querySelector('text')?.textContent)).toEqual([
      'new',
      'established',
      'veteran',
    ]);
    expect(rows.map((r) => r.getAttribute('transform'))).toEqual([
      'translate(0, 0)',
      'translate(0, 25)',
      'translate(0, 50)',
    ]);
    expect(rows[2].querySelector('circle')).toHaveAttribute('fill', '#64B5F6');
  });

  test('sem categorias não há legenda', () => {
    const { container } = render(
      <ScatterPlot
        data={[
          { x: 1, y: 1 },
          { x: 2, y: 2 },
        ]}
      />
    );
    expect(container.querySelectorAll('svg > g')).toHaveLength(1);
    dots(container).forEach((c) => expect(c).toHaveAttribute('fill', '#64B5F6'));
  });

  test.each([
    [{ xLabel: 'Score', yLabel: 'Contribuições' }, ['Score', 'Contribuições']],
    [{ xLabel: 'Score' }, ['Score']],
    [{ yLabel: 'Contribuições' }, ['Contribuições']],
    [{}, []],
  ])('rótulos de eixo %o', (labels, expected) => {
    const { container } = render(<ScatterPlot data={data} {...labels} />);
    expect(axisLabels(container)).toEqual(expected);
  });

  test('yLabel é rotacionado e eixos estilizados', () => {
    const { container } = render(<ScatterPlot data={data} yLabel="Y" />);
    expect(container.querySelector('svg > g > text')).toHaveAttribute('transform', 'rotate(-90)');
    const domains = container.querySelectorAll('.domain');
    expect(domains).toHaveLength(2);
    domains.forEach((d) => expect(d).toHaveAttribute('stroke', '#475569'));
  });

  test('mouseover/mouseout destacam o ponto', () => {
    const { container } = render(<ScatterPlot data={data} />);
    const dot = dots(container)[2];
    fireEvent.mouseOver(dot);
    expect(dot).toHaveAttribute('r', '8');
    expect(dot).toHaveAttribute('opacity', '1');
    fireEvent.mouseOut(dot);
    expect(dot).toHaveAttribute('r', '6');
    expect(dot).toHaveAttribute('opacity', '0.7');
  });

  test('todos os valores zero não geram coordenadas inválidas', () => {
    const { container } = render(<ScatterPlot data={[{ x: 0, y: 0 }]} />);
    const dot = dots(container)[0];
    expect(Number.isFinite(Number(dot.getAttribute('cx')))).toBe(true);
    expect(Number.isFinite(Number(dot.getAttribute('cy')))).toBe(true);
  });

  test('redesenha sem duplicar ao mudar props', () => {
    const { container, rerender } = render(<ScatterPlot data={data} />);
    rerender(<ScatterPlot data={data.slice(0, 2)} xLabel="X" />);
    expect(dots(container)).toHaveLength(2);
    expect(legendRows(container)).toHaveLength(1);
    expect(container.querySelectorAll('svg > g')).toHaveLength(2);
  });
});

import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import PieChart from './PieChart';
import { PieChart as PieChartFromIndex } from './index';

type Props = ComponentProps<typeof PieChart>;

const data: Props['data'] = [
  { label: 'Alice', value: 50 },
  { label: 'Bob', value: 30 },
  { label: 'Carol', value: 20 },
];

function slices(container: HTMLElement): SVGPathElement[] {
  return Array.from(container.querySelectorAll<SVGPathElement>('svg > g:first-of-type > path'));
}

function sliceLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg > g:first-of-type > text')).map(
    (t) => t.textContent ?? ''
  );
}

function legendRows(container: HTMLElement): Element[] {
  return Array.from(container.querySelectorAll('svg > g:nth-of-type(2) > g'));
}

const CSS_VARS = ['--color-blue-trust', '--color-green-growth', '--color-amber-accent'];

describe('PieChart', () => {
  afterEach(() => {
    CSS_VARS.forEach((v) => document.documentElement.style.removeProperty(v));
  });

  test('é reexportado pelo index', () => {
    expect(PieChartFromIndex).toBe(PieChart);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<PieChart data={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando data é undefined', () => {
    const props = { data: undefined } as unknown as Props;
    const { container } = render(<PieChart {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define atributos padrão do svg e centraliza o gráfico', () => {
    const { container } = render(<PieChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '400');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 400 400');
    expect(svg).toHaveAttribute('aria-label', 'Gráfico de pizza');
    expect(container.querySelector('svg > g')).toHaveAttribute(
      'transform',
      'translate(200, 200)'
    );
  });

  test('desenha uma fatia por item com cores padrão (fallback)', () => {
    const { container } = render(<PieChart data={data} />);
    const ps = slices(container);
    expect(ps).toHaveLength(3);
    expect(ps.map((p) => p.getAttribute('fill'))).toEqual(['#1E88E5', '#43A047', '#FFB300']);
    ps.forEach((p) => {
      expect(p.getAttribute('d')).toMatch(/^M/);
      expect(p).toHaveAttribute('stroke', '#1e293b');
      expect(p.style.opacity).toBe('0.9');
    });
  });

  test('donut padrão (innerRadius=60) vs pizza (innerRadius=0)', () => {
    const { container: donut } = render(<PieChart data={data} />);
    const { container: pie } = render(<PieChart data={data} innerRadius={0} />);
    const donutD = slices(donut)[0].getAttribute('d') ?? '';
    const pieD = slices(pie)[0].getAttribute('d') ?? '';
    // Donut possui dois arcos (externo + interno); pizza fecha no centro
    expect((donutD.match(/A/g) ?? []).length).toBe(2);
    expect((pieD.match(/A/g) ?? []).length).toBe(1);
    expect(pieD).toContain('L0,0');
    // raio externo = min(w,h)/2 - 10 = 190
    expect(pieD).toContain('A190,190');
    expect(donutD).toContain('A60,60');
  });

  test('usa as variáveis CSS do tema nas cores padrão', () => {
    document.documentElement.style.setProperty('--color-blue-trust', '#000001');
    document.documentElement.style.setProperty('--color-green-growth', '#000002');
    document.documentElement.style.setProperty('--color-amber-accent', '#000003');
    const { container } = render(<PieChart data={data} />);
    expect(slices(container).map((p) => p.getAttribute('fill'))).toEqual([
      '#000001',
      '#000002',
      '#000003',
    ]);
  });

  test('cores padrão cobrem mais de três categorias', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i'].map((label) => ({
      label,
      value: 1,
    }));
    const { container } = render(<PieChart data={many} />);
    const fills = slices(container).map((p) => p.getAttribute('fill'));
    expect(fills.slice(3, 8)).toEqual(['#9C27B0', '#F44336', '#00BCD4', '#FF9800', '#4CAF50']);
    // a escala ordinal recicla as cores
    expect(fills[8]).toBe(fills[0]);
  });

  test('usa cores personalizadas nas fatias e na legenda', () => {
    const colors = ['#aa0000', '#00aa00', '#0000aa'];
    const { container } = render(<PieChart data={data} colors={colors} />);
    expect(slices(container).map((p) => p.getAttribute('fill'))).toEqual(colors);
    const legendFills = legendRows(container).map((r) =>
      r.querySelector('rect')?.getAttribute('fill')
    );
    expect(legendFills).toEqual(colors);
  });

  test('mostra rótulos de porcentagem por padrão', () => {
    const { container } = render(<PieChart data={data} />);
    expect(sliceLabels(container)).toEqual(['50.0%', '30.0%', '20.0%']);
    const label = container.querySelector('svg > g:first-of-type > text');
    expect(label?.getAttribute('transform')).toMatch(/^translate\(/);
    expect(label).toHaveAttribute('font-weight', 'bold');
  });

  test('omite o rótulo de fatias com 0.0%', () => {
    const { container } = render(
      <PieChart
        data={[
          { label: 'Grande', value: 10000 },
          { label: 'Minúsculo', value: 1 },
          { label: 'Zero', value: 0 },
        ]}
      />
    );
    expect(sliceLabels(container)).toEqual(['100.0%', '', '']);
  });

  test('showLabels=false não desenha rótulos nas fatias', () => {
    const { container } = render(<PieChart data={data} showLabels={false} />);
    expect(sliceLabels(container)).toEqual([]);
    expect(slices(container)).toHaveLength(3);
  });

  test('desenha a legenda com um item por categoria', () => {
    const { container } = render(<PieChart data={data} width={500} />);
    const legend = container.querySelector('svg > g:nth-of-type(2)');
    expect(legend).toHaveAttribute('transform', 'translate(380, 20)');
    const rows = legendRows(container);
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.getAttribute('transform'))).toEqual([
      'translate(0, 0)',
      'translate(0, 25)',
      'translate(0, 50)',
    ]);
    expect(rows.map((r) => r.querySelector('text')?.textContent)).toEqual([
      'Alice',
      'Bob',
      'Carol',
    ]);
    rows.forEach((r) => {
      expect(r.querySelector('rect')).toHaveAttribute('width', '15');
      expect(r.querySelector('rect')).toHaveAttribute('rx', '2');
    });
  });

  test('raio usa a menor dimensão', () => {
    const { container } = render(<PieChart data={data} width={600} height={200} innerRadius={0} />);
    // raio = 100 → externo = 90
    expect(slices(container)[0].getAttribute('d')).toContain('A90,90');
  });

  test('mouseover/mouseout destacam a fatia', () => {
    const { container } = render(<PieChart data={data} />);
    const slice = slices(container)[1];
    fireEvent.mouseOver(slice);
    expect(slice.style.opacity).toBe('1');
    expect(slice.style.filter).toBe('brightness(1.1)');
    fireEvent.mouseOut(slice);
    expect(slice.style.opacity).toBe('0.9');
    expect(slice.style.filter).toBe('none');
  });

  test('redesenha sem duplicar ao mudar props', () => {
    const { container, rerender } = render(<PieChart data={data} />);
    rerender(<PieChart data={data.slice(0, 2)} showLabels={false} />);
    expect(slices(container)).toHaveLength(2);
    expect(legendRows(container)).toHaveLength(2);
    expect(container.querySelectorAll('svg > g')).toHaveLength(2);
  });

  // BUG conhecido: se todos os valores forem 0, total = 0 e o rótulo vira "NaN%".
  test.fails('não exibe "NaN%" quando todos os valores são zero (bug)', () => {
    const { container } = render(
      <PieChart
        data={[
          { label: 'A', value: 0 },
          { label: 'B', value: 0 },
        ]}
      />
    );
    sliceLabels(container).forEach((l) => expect(l).not.toContain('NaN'));
  });
});

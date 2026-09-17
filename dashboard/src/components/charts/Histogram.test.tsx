import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import Histogram, { gaussianKDE, silvermanBandwidth } from './Histogram';
import { Histogram as HistogramFromIndex } from './index';

type Props = ComponentProps<typeof Histogram>;

const data = [1, 2, 2, 3, 3, 3, 7, 9, 10];

function bars(container: HTMLElement): SVGRectElement[] {
  return Array.from(container.querySelectorAll<SVGRectElement>('svg > g > rect'));
}

function axisLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg > g > text')).map(
    (t) => t.textContent ?? ''
  );
}

function totalCount(container: HTMLElement, innerHeight: number, yMax: number): number {
  return bars(container).reduce(
    (acc, r) => acc + (Number(r.getAttribute('height')) / innerHeight) * yMax,
    0
  );
}

describe('Histogram', () => {
  afterEach(() => {
    document.documentElement.style.removeProperty('--color-green-growth');
  });

  test('é reexportado pelo index', () => {
    expect(HistogramFromIndex).toBe(Histogram);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<Histogram data={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando data é undefined', () => {
    const props = { data: undefined } as unknown as Props;
    const { container } = render(<Histogram {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define dimensões padrão do svg', () => {
    const { container } = render(<Histogram data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '600');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 600 400');
  });

  test('bins automáticos usam os ticks da escala (passo 0.5 em [0,10])', () => {
    const { container } = render(<Histogram data={data} />);
    const rects = bars(container);
    // x.ticks(20) em [0, 10] → 21 limiares → 20 bins + bin degenerado [10, 10]
    expect(rects.length).toBe(21);
    // bin degenerado tem largura negativa, limitada a 0 por Math.max
    expect(rects[20]).toHaveAttribute('width', '0');
    expect(rects[0]).toHaveAttribute('width', '23.5');
    // innerHeight = 400 - 20 - 60 = 320; maior bin tem 3 elementos → y domínio [0, 3]
    const heights = rects.map((r) => Number(r.getAttribute('height')));
    expect(Math.max(...heights)).toBe(320);
    expect(totalCount(container, 320, 3)).toBeCloseTo(data.length);
    rects.forEach((r) => {
      expect(Number(r.getAttribute('width'))).toBeGreaterThanOrEqual(0);
      expect(r).toHaveAttribute('opacity', '0.8');
    });
  });

  test('bins explícitos alteram a quantidade de barras', () => {
    const { container } = render(<Histogram data={data} bins={2} />);
    const rects = bars(container);
    // thresholds(2) em [0, 10] → limiares "nice" [0, 5, 10] → 2 bins
    expect(rects).toHaveLength(2);
    // [0,5): 1,2,2,3,3,3 = 6 ; [5,10]: 7,9,10 = 3 → y domínio [0, 6]
    const heights = rects.map((r) => Number(r.getAttribute('height')));
    expect(heights).toEqual([320, 160]);
    // largura = x(x1) - x(x0) - 2; innerWidth = 510 → 255 - 2
    expect(rects[0]).toHaveAttribute('width', '253');
    expect(rects[0]).toHaveAttribute('x', '1');
  });

  test('bins = 0 ainda é respeitado (não usa o padrão)', () => {
    const { container: auto } = render(<Histogram data={data} />);
    const autoCount = bars(auto).length;
    const { container } = render(<Histogram data={data} bins={0} />);
    expect(bars(container).length).not.toBe(autoCount);
  });

  test('eixos mostram ticks e são estilizados', () => {
    const { container } = render(<Histogram data={data} />);
    const domains = container.querySelectorAll('.domain');
    expect(domains).toHaveLength(2);
    domains.forEach((d) => expect(d).toHaveAttribute('stroke', '#475569'));
    const xTicks = Array.from(container.querySelectorAll('svg > g > g')[0].querySelectorAll('text'));
    expect(xTicks[0]).toHaveTextContent('0');
    xTicks.forEach((t) => expect(t).toHaveAttribute('fill', '#e2e8f0'));
  });

  test.each([
    [{ xLabel: 'Repos', yLabel: 'Frequência' }, ['Repos', 'Frequência']],
    [{ xLabel: 'Repos' }, ['Repos']],
    [{ yLabel: 'Frequência' }, ['Frequência']],
    [{}, []],
  ])('rótulos de eixo %o', (labels, expected) => {
    const { container } = render(<Histogram data={data} {...labels} />);
    expect(axisLabels(container)).toEqual(expected);
  });

  test('yLabel é rotacionado', () => {
    const { container } = render(<Histogram data={data} yLabel="Y" />);
    expect(container.querySelector('svg > g > text')).toHaveAttribute('transform', 'rotate(-90)');
  });

  describe('cor', () => {
    test('usa cor personalizada', () => {
      document.documentElement.style.setProperty('--color-green-growth', '#00ff00');
      const { container } = render(<Histogram data={data} color="#abcdef" />);
      bars(container).forEach((r) => expect(r).toHaveAttribute('fill', '#abcdef'));
    });

    test('usa a variável CSS do tema', () => {
      document.documentElement.style.setProperty('--color-green-growth', '#00ff00');
      const { container } = render(<Histogram data={data} />);
      bars(container).forEach((r) => expect(r).toHaveAttribute('fill', '#00ff00'));
    });

    test('usa fallback quando não há variável CSS', () => {
      const { container } = render(<Histogram data={data} />);
      bars(container).forEach((r) => expect(r).toHaveAttribute('fill', '#43A047'));
    });
  });

  test('mouseover/mouseout alteram a opacidade', () => {
    const { container } = render(<Histogram data={data} />);
    const rect = bars(container)[2];
    fireEvent.mouseOver(rect);
    expect(rect).toHaveAttribute('opacity', '1');
    fireEvent.mouseOut(rect);
    expect(rect).toHaveAttribute('opacity', '0.8');
  });

  test('dados todos zero produzem um único bin', () => {
    const { container } = render(<Histogram data={[0, 0, 0]} />);
    const rects = bars(container);
    expect(rects).toHaveLength(1);
    expect(rects[0]).toHaveAttribute('fill');
  });

  // Regressão #79: showKDE estava na interface/documentação, mas nunca era desenhado.
  describe('showKDE', () => {
    function kdePath(container: HTMLElement) {
      return container.querySelector<SVGPathElement>('svg > g > path.kde-curve');
    }

    test('desenha a curva de densidade', () => {
      const { container } = render(<Histogram data={data} showKDE />);
      const path = kdePath(container);
      expect(path).not.toBeNull();
      expect(path).toHaveAttribute('fill', 'none');
      const d = path?.getAttribute('d') ?? '';
      expect(d).toMatch(/^M/);
      expect(d).not.toContain('NaN');
    });

    test('não desenha a curva sem showKDE', () => {
      const { container } = render(<Histogram data={data} />);
      expect(container.querySelector('svg > g > path')).toBeNull();
    });

    test('não desenha a curva quando os dados não têm dispersão', () => {
      const { container } = render(<Histogram data={[4, 4, 4]} showKDE />);
      expect(kdePath(container)).toBeNull();
      expect(bars(container).length).toBeGreaterThan(0);
    });

    test('a curva fica dentro da área do gráfico', () => {
      const { container } = render(<Histogram data={data} showKDE />);
      const d = kdePath(container)?.getAttribute('d') ?? '';
      const nums = (d.match(/-?\d+(\.\d+)?(e-?\d+)?/g) ?? []).map(Number);
      const xs = nums.filter((_, i) => i % 2 === 0);
      const ys = nums.filter((_, i) => i % 2 === 1);
      // innerWidth = 510, innerHeight = 320
      xs.forEach((v) => expect(v).toBeGreaterThanOrEqual(-1e-6));
      xs.forEach((v) => expect(v).toBeLessThanOrEqual(510 + 1e-6));
      ys.forEach((v) => expect(v).toBeGreaterThanOrEqual(-1e-6));
      ys.forEach((v) => expect(v).toBeLessThanOrEqual(320 + 1e-6));
    });

    test('silvermanBandwidth segue a regra de Silverman', () => {
      expect(silvermanBandwidth([])).toBe(0);
      expect(silvermanBandwidth([1])).toBe(0);
      expect(silvermanBandwidth([2, 2, 2])).toBe(0);
      const values = [1, 2, 3, 4, 5];
      // sd = sqrt(2.5) ≈ 1.5811; IQR = 4 - 2 = 2 → 2 / 1.34 ≈ 1.4925
      expect(silvermanBandwidth(values)).toBeCloseTo(0.9 * (2 / 1.34) * Math.pow(5, -0.2), 10);
    });

    test('gaussianKDE integra aproximadamente 1 e tem pico na moda', () => {
      const values = [0, 0, 0, 5];
      const h = 1;
      const xs = Array.from({ length: 2001 }, (_, i) => -10 + i * 0.01);
      const dens = gaussianKDE(values, h, xs);
      const area = dens.reduce((a, v) => a + v * 0.01, 0);
      expect(area).toBeCloseTo(1, 3);
      const peak = xs[dens.indexOf(Math.max(...dens))];
      expect(peak).toBeCloseTo(0, 1);
      // valor em x = 0: (3 * φ(0) + φ(5)) / 4
      const phi = (u: number) => Math.exp(-0.5 * u * u) / Math.sqrt(2 * Math.PI);
      expect(gaussianKDE(values, h, [0])[0]).toBeCloseTo((3 * phi(0) + phi(5)) / 4, 10);
    });

    test('barras continuam dentro do gráfico com KDE ativo', () => {
      const { container } = render(<Histogram data={data} showKDE />);
      bars(container).forEach((r) => {
        expect(Number(r.getAttribute('height'))).toBeLessThanOrEqual(320);
        expect(Number(r.getAttribute('y'))).toBeGreaterThanOrEqual(0);
      });
    });
  });

  // Regressão #79: o domínio de X começava em 0, então valores negativos eram descartados.
  test('valores negativos são contabilizados', () => {
    const values = [-5, -3, 1, 2];
    const { container } = render(<Histogram data={values} bins={2} />);
    const heights = bars(container).map((r) => Number(r.getAttribute('height')));
    const yMax = 2;
    const total = heights.reduce((a, h) => a + (h / 320) * yMax, 0);
    expect(total).toBeCloseTo(values.length);
  });

  test('redesenha sem duplicar ao mudar props', () => {
    const { container, rerender } = render(<Histogram data={data} bins={2} />);
    expect(bars(container)).toHaveLength(2);
    rerender(<Histogram data={data} bins={2} xLabel="X" width={300} />);
    expect(bars(container)).toHaveLength(2);
    expect(container.querySelectorAll('svg > g')).toHaveLength(1);
    expect(axisLabels(container)).toEqual(['X']);
  });
});

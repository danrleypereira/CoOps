import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import BarChart from './BarChart';
import { BarChart as BarChartFromIndex } from './index';

type Props = ComponentProps<typeof BarChart>;

const data: Props['data'] = [
  { label: 'Alice', value: 10 },
  { label: 'Bob', value: 20 },
  { label: 'Carol', value: 5 },
];

function bars(container: HTMLElement): SVGRectElement[] {
  return Array.from(container.querySelectorAll<SVGRectElement>('svg > g > rect'));
}

/** Textos adicionados diretamente no grupo principal (rótulos de eixo). */
function axisLabels(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('svg > g > text')).map(
    (t) => t.textContent ?? ''
  );
}

describe('BarChart', () => {
  afterEach(() => {
    document.documentElement.style.removeProperty('--color-blue-trust');
  });

  test('é reexportado pelo index', () => {
    expect(BarChartFromIndex).toBe(BarChart);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<BarChart data={[]} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(svg?.childNodes.length).toBe(0);
    expect(svg?.getAttribute('width')).toBeNull();
  });

  test('não desenha nada quando data é undefined', () => {
    const props = { data: undefined } as unknown as Props;
    const { container } = render(<BarChart {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('usa dimensões padrão e define atributos do svg', () => {
    const { container } = render(<BarChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '600');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 600 400');
    // Obs.: o rótulo atual é "Histograma", embora o componente seja um gráfico de barras.
    expect(svg?.getAttribute('aria-label')).toBeTruthy();
    expect(container.querySelector('svg > g')).toHaveAttribute(
      'transform',
      'translate(60,20)'
    );
  });

  describe('orientação vertical (padrão)', () => {
    test('desenha uma barra por item com alturas proporcionais', () => {
      const { container } = render(<BarChart data={data} width={600} height={400} />);
      const rects = bars(container);
      expect(rects).toHaveLength(3);

      // innerHeight = 400 - 20 - 80 = 300; domínio [0, 20]
      const heights = rects.map((r) => Number(r.getAttribute('height')));
      expect(heights).toEqual([150, 300, 75]);
      const ys = rects.map((r) => Number(r.getAttribute('y')));
      expect(ys).toEqual([150, 0, 225]);

      // Todas as barras têm a mesma largura (bandwidth) e x crescente
      const widths = new Set(rects.map((r) => r.getAttribute('width')));
      expect(widths.size).toBe(1);
      const xs = rects.map((r) => Number(r.getAttribute('x')));
      expect(xs[0]).toBeLessThan(xs[1]);
      expect(xs[1]).toBeLessThan(xs[2]);
    });

    test('rotaciona os rótulos do eixo X e mostra os nomes', () => {
      const { container } = render(<BarChart data={data} />);
      const xAxis = container.querySelector('svg > g > g');
      const labels = Array.from(xAxis?.querySelectorAll('text') ?? []);
      expect(labels.map((l) => l.textContent)).toEqual(['Alice', 'Bob', 'Carol']);
      labels.forEach((l) => {
        expect(l).toHaveAttribute('transform', 'rotate(-45)');
        expect(l).toHaveAttribute('fill', '#e2e8f0');
      });
    });

    test('estiliza linhas de eixo e domínio', () => {
      const { container } = render(<BarChart data={data} />);
      const domains = container.querySelectorAll('.domain');
      expect(domains.length).toBe(2);
      domains.forEach((d) => expect(d).toHaveAttribute('stroke', '#475569'));
      container
        .querySelectorAll('.tick line')
        .forEach((l) => expect(l).toHaveAttribute('stroke', '#475569'));
    });

    test('renderiza xLabel e yLabel quando fornecidos', () => {
      const { container } = render(
        <BarChart data={data} xLabel="Membros" yLabel="Commits" />
      );
      expect(axisLabels(container)).toEqual(['Membros', 'Commits']);
      const yText = Array.from(container.querySelectorAll('svg > g > text')).find(
        (t) => t.textContent === 'Commits'
      );
      expect(yText).toHaveAttribute('transform', 'rotate(-90)');
    });

    test('renderiza apenas xLabel', () => {
      const { container } = render(<BarChart data={data} xLabel="Membros" />);
      expect(axisLabels(container)).toEqual(['Membros']);
    });

    test('renderiza apenas yLabel', () => {
      const { container } = render(<BarChart data={data} yLabel="Commits" />);
      expect(axisLabels(container)).toEqual(['Commits']);
    });

    test('sem rótulos quando xLabel/yLabel ausentes', () => {
      const { container } = render(<BarChart data={data} />);
      expect(axisLabels(container)).toEqual([]);
    });

    test('mouseover/mouseout alteram a opacidade da barra', () => {
      const { container } = render(<BarChart data={data} />);
      const rect = bars(container)[1];
      expect(rect.style.opacity).toBe('0.9');
      expect(rect.style.cursor).toBe('pointer');
      fireEvent.mouseOver(rect);
      expect(rect.style.opacity).toBe('1');
      fireEvent.mouseOut(rect);
      expect(rect.style.opacity).toBe('0.9');
    });

    // BUG conhecido: com todos os valores 0 o domínio fica [0, 0] e o d3
    // mapeia 0 para o meio do range, desenhando barras com metade da altura.
    test.fails('todos os valores zero geram barras com altura 0 (bug: domínio [0,0])', () => {
      const { container } = render(
        <BarChart
          data={[
            { label: 'A', value: 0 },
            { label: 'B', value: 0 },
          ]}
        />
      );
      const rects = bars(container);
      expect(rects).toHaveLength(2);
      rects.forEach((r) => expect(Number(r.getAttribute('height'))).toBe(0));
    });
  });

  describe('orientação horizontal', () => {
    test('desenha barras com largura proporcional e x = 0', () => {
      const { container } = render(
        <BarChart data={data} orientation="horizontal" width={600} height={400} />
      );
      const rects = bars(container);
      expect(rects).toHaveLength(3);
      // innerWidth = 600 - 60 - 30 = 510; domínio [0, 20]
      expect(rects.map((r) => Number(r.getAttribute('width')))).toEqual([255, 510, 127.5]);
      rects.forEach((r) => expect(r).toHaveAttribute('x', '0'));
      const heights = new Set(rects.map((r) => r.getAttribute('height')));
      expect(heights.size).toBe(1);
      const ys = rects.map((r) => Number(r.getAttribute('y')));
      expect(ys[0]).toBeLessThan(ys[1]);
    });

    test('rótulos do eixo X não são rotacionados e categorias ficam no eixo Y', () => {
      const { container } = render(<BarChart data={data} orientation="horizontal" />);
      const axes = container.querySelectorAll('svg > g > g');
      expect(axes).toHaveLength(2);
      axes[0].querySelectorAll('text').forEach((t) => {
        expect(t).not.toHaveAttribute('transform');
      });
      const yLabels = Array.from(axes[1].querySelectorAll('text')).map((t) => t.textContent);
      expect(yLabels).toEqual(['Alice', 'Bob', 'Carol']);
    });

    // BUG conhecido: o ramo horizontal nunca desenha xLabel/yLabel.
    test.fails('renderiza xLabel/yLabel na orientação horizontal (bug: ignorados)', () => {
      const { container } = render(
        <BarChart data={data} orientation="horizontal" xLabel="X" yLabel="Y" />
      );
      expect(axisLabels(container)).toEqual(['X', 'Y']);
    });

    test('mouseover/mouseout alteram a opacidade da barra', () => {
      const { container } = render(<BarChart data={data} orientation="horizontal" />);
      const rect = bars(container)[0];
      fireEvent.mouseOver(rect);
      expect(rect.style.opacity).toBe('1');
      fireEvent.mouseOut(rect);
      expect(rect.style.opacity).toBe('0.9');
    });

    // BUG conhecido: mesmo problema do domínio [0, 0] na orientação horizontal.
    test.fails('todos os valores zero geram barras com largura 0 (bug: domínio [0,0])', () => {
      const { container } = render(
        <BarChart data={[{ label: 'A', value: 0 }]} orientation="horizontal" />
      );
      expect(bars(container)[0]).toHaveAttribute('width', '0');
    });
  });

  describe('cor das barras', () => {
    test('usa a cor personalizada quando fornecida', () => {
      document.documentElement.style.setProperty('--color-blue-trust', '#123456');
      const { container } = render(<BarChart data={data} color="#ff0000" />);
      bars(container).forEach((r) => expect(r).toHaveAttribute('fill', '#ff0000'));
    });

    test('usa a variável CSS do tema quando não há cor', () => {
      document.documentElement.style.setProperty('--color-blue-trust', '#123456');
      const { container } = render(<BarChart data={data} />);
      bars(container).forEach((r) => expect(r).toHaveAttribute('fill', '#123456'));
    });

    test('usa a cor de fallback quando a variável CSS não existe', () => {
      const { container } = render(<BarChart data={data} />);
      bars(container).forEach((r) => expect(r).toHaveAttribute('fill', '#1E88E5'));
    });
  });

  test('redesenha ao mudar as props, sem duplicar elementos', () => {
    const { container, rerender } = render(<BarChart data={data} />);
    expect(bars(container)).toHaveLength(3);
    rerender(<BarChart data={data.slice(0, 2)} width={300} />);
    expect(bars(container)).toHaveLength(2);
    expect(container.querySelector('svg')).toHaveAttribute('width', '300');
    expect(container.querySelectorAll('svg > g')).toHaveLength(1);
  });
});

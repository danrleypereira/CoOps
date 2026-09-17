import { describe, test, expect } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent } from '@testing-library/react';
import Heatmap from './Heatmap';
import { Heatmap as HeatmapFromIndex } from './index';

type Props = ComponentProps<typeof Heatmap>;

const data: Props['data'] = [
  { row: 'Seg', col: 0, value: 0 },
  { row: 'Seg', col: 1, value: 4 },
  { row: 'Ter', col: 0, value: 8 },
  { row: 'Ter', col: 1, value: 2 },
];

function cells(container: HTMLElement): SVGRectElement[] {
  // Células ficam no grupo principal; o retângulo da legenda fica em outro grupo.
  return Array.from(container.querySelectorAll<SVGRectElement>('svg > g:first-of-type > rect'));
}

function valueTexts(container: HTMLElement): SVGTextElement[] {
  return Array.from(container.querySelectorAll<SVGTextElement>('text.value'));
}

describe('Heatmap', () => {
  test('é reexportado pelo index', () => {
    expect(HeatmapFromIndex).toBe(Heatmap);
  });

  test('não desenha nada quando data está vazio', () => {
    const { container } = render(<Heatmap data={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando data é undefined', () => {
    const props = { data: undefined } as unknown as Props;
    const { container } = render(<Heatmap {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define dimensões padrão, título e posição do grupo principal', () => {
    const { container } = render(<Heatmap data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '800');
    expect(svg).toHaveAttribute('height', '400');
    expect(svg).toHaveAttribute('viewBox', '0 0 800 400');
    expect(container.querySelector('svg > g')).toHaveAttribute(
      'transform',
      'translate(80,60)'
    );
    const title = container.querySelector('svg > text');
    expect(title).toHaveTextContent('Activity Heatmap');
    expect(title).toHaveAttribute('x', '400');
  });

  test('desenha uma célula por item com linhas/colunas derivadas dos dados', () => {
    const { container } = render(<Heatmap data={data} width={800} height={400} />);
    const rects = cells(container);
    expect(rects).toHaveLength(4);

    // Eixos: colunas no eixo X, linhas no eixo Y
    const axes = container.querySelectorAll('svg > g:first-of-type > g');
    const colTicks = Array.from(axes[0].querySelectorAll('text')).map((t) => t.textContent);
    const rowTicks = Array.from(axes[1].querySelectorAll('text')).map((t) => t.textContent);
    expect(colTicks).toEqual(['0', '1']);
    expect(rowTicks).toEqual(['Seg', 'Ter']);

    // Mesma largura/altura para todas as células
    expect(new Set(rects.map((r) => r.getAttribute('width'))).size).toBe(1);
    expect(new Set(rects.map((r) => r.getAttribute('height'))).size).toBe(1);

    // Primeira célula está na origem; a da coluna 1 está à direita
    expect(Number(rects[0].getAttribute('x'))).toBeLessThan(Number(rects[1].getAttribute('x')));
    expect(Number(rects[0].getAttribute('y'))).toBeLessThan(Number(rects[2].getAttribute('y')));
  });

  test('células com valor 0 usam a cor de fundo e as demais usam a escala', () => {
    const { container } = render(<Heatmap data={data} />);
    const rects = cells(container);
    expect(rects[0]).toHaveAttribute('fill', '#1e293b');
    // valor máximo (8) → última cor do esquema azul
    expect(rects[2]).toHaveAttribute('fill', 'rgb(3, 105, 161)');
    // valor 4 (= max/2) → cor intermediária
    expect(rects[1]).toHaveAttribute('fill', 'rgb(14, 165, 233)');
    expect(rects[3].getAttribute('fill')).not.toBe('#1e293b');
  });

  test.each([
    ['blue', ['#f0f9ff', '#0ea5e9', '#0369a1'], 'rgb(3, 105, 161)'],
    ['green', ['#f0fdf4', '#22c55e', '#15803d'], 'rgb(21, 128, 61)'],
    ['red', ['#fef2f2', '#ef4444', '#b91c1c'], 'rgb(185, 28, 28)'],
    ['amber', ['#fffbeb', '#f59e0b', '#b45309'], 'rgb(180, 83, 9)'],
  ] as const)('esquema de cores %s aplica o gradiente e as células', (scheme, stops, maxFill) => {
    const { container } = render(<Heatmap data={data} colorScheme={scheme} />);
    const gradient = container.querySelector('linearGradient[id^="heatmap-gradient"]');
    expect(gradient).not.toBeNull();
    const stopColors = Array.from(gradient?.querySelectorAll('stop') ?? []).map((s) =>
      s.getAttribute('stop-color')
    );
    expect(stopColors).toEqual([...stops]);
    expect(cells(container)[2]).toHaveAttribute('fill', maxFill);
  });

  test('legenda usa o gradiente e possui eixo', () => {
    const { container } = render(<Heatmap data={data} width={800} />);
    const legend = container.querySelector('svg > g:nth-of-type(2)');
    // legendX = 800 - 200 - 30
    expect(legend).toHaveAttribute('transform', 'translate(570,20)');
    const legendRect = legend?.querySelector('rect');
    expect(legendRect).toHaveAttribute('width', '200');
    expect(legendRect).toHaveAttribute('height', '10');
    expect(legendRect?.style.fill).toContain('heatmap-gradient');
    expect(legend?.querySelector('.domain')).toHaveAttribute('stroke', '#475569');
    const ticks = Array.from(legend?.querySelectorAll('.tick text') ?? []);
    expect(ticks.length).toBeGreaterThan(1);
    ticks.forEach((t) => expect(t).toHaveAttribute('font-size', '10px'));
  });

  test('não mostra valores por padrão', () => {
    const { container } = render(<Heatmap data={data} />);
    expect(valueTexts(container)).toHaveLength(0);
  });

  test('showValues exibe valores (vazio para zero) com cor por intensidade', () => {
    const { container } = render(<Heatmap data={data} showValues />);
    const texts = valueTexts(container);
    expect(texts).toHaveLength(4);
    expect(texts.map((t) => t.textContent)).toEqual(['', '4', '8', '2']);
    // valores acima de max/2 (=4) ficam em branco
    expect(texts[2]).toHaveAttribute('fill', '#fff');
    expect(texts[1]).toHaveAttribute('fill', '#e2e8f0');
    expect(texts[3]).toHaveAttribute('fill', '#e2e8f0');

    // centralizado na célula
    const rect = cells(container)[1];
    const expectedX =
      Number(rect.getAttribute('x')) + Number(rect.getAttribute('width')) / 2;
    expect(Number(texts[1].getAttribute('x'))).toBeCloseTo(expectedX);
  });

  test('usa rowLabels e colLabels fornecidos (inclusive ordem e rótulos extras)', () => {
    const { container } = render(
      <Heatmap
        data={[
          { row: 'Dom', col: 'b', value: 3 },
          { row: 'Sab', col: 'a', value: 1 },
          { row: 'Fora', col: 'z', value: 5 },
        ]}
        rowLabels={['Sab', 'Dom', 'Seg']}
        colLabels={['a', 'b', 'c']}
      />
    );
    const axes = container.querySelectorAll('svg > g:first-of-type > g');
    expect(Array.from(axes[0].querySelectorAll('text')).map((t) => t.textContent)).toEqual([
      'a',
      'b',
      'c',
    ]);
    expect(Array.from(axes[1].querySelectorAll('text')).map((t) => t.textContent)).toEqual([
      'Sab',
      'Dom',
      'Seg',
    ]);

    const rects = cells(container);
    expect(rects).toHaveLength(3);
    // 'Dom' é a segunda linha → y > 0; 'Sab' é a primeira
    expect(Number(rects[0].getAttribute('y'))).toBeGreaterThan(0);
    expect(Number(rects[1].getAttribute('y'))).toBe(Number(rects[1].getAttribute('y')));
    expect(Number(rects[1].getAttribute('x'))).toBeLessThan(Number(rects[0].getAttribute('x')));
    // Linha/coluna fora dos rótulos cai na posição 0,0 (fallback)
    expect(rects[2]).toHaveAttribute('x', '0');
    expect(rects[2]).toHaveAttribute('y', '0');
  });

  test('showValues posiciona valores fora dos rótulos no fallback', () => {
    const { container } = render(
      <Heatmap
        data={[{ row: 'X', col: 'Y', value: 1 }]}
        rowLabels={['A']}
        colLabels={['B']}
        showValues
      />
    );
    const text = valueTexts(container)[0];
    const rect = cells(container)[0];
    expect(Number(text.getAttribute('x'))).toBeCloseTo(Number(rect.getAttribute('width')) / 2);
    expect(Number(text.getAttribute('y'))).toBeCloseTo(Number(rect.getAttribute('height')) / 2);
  });

  test('todos os valores zero usam max=1 e cor de fundo', () => {
    const { container } = render(
      <Heatmap
        data={[
          { row: 1, col: 1, value: 0 },
          { row: 2, col: 1, value: 0 },
        ]}
      />
    );
    cells(container).forEach((r) => expect(r).toHaveAttribute('fill', '#1e293b'));
    const legendTicks = Array.from(
      container.querySelectorAll('svg > g:nth-of-type(2) .tick text')
    ).map((t) => t.textContent);
    expect(legendTicks[legendTicks.length - 1]).toBe('1.0');
  });

  test('mouseover/mouseout destacam a borda da célula', () => {
    const { container } = render(<Heatmap data={data} />);
    const rect = cells(container)[1];
    expect(rect).toHaveAttribute('stroke', '#0f172a');
    expect(rect).toHaveAttribute('stroke-width', '1');
    fireEvent.mouseOver(rect);
    expect(rect).toHaveAttribute('stroke', '#64B5F6');
    expect(rect).toHaveAttribute('stroke-width', '2');
    fireEvent.mouseOut(rect);
    expect(rect).toHaveAttribute('stroke', '#0f172a');
    expect(rect).toHaveAttribute('stroke-width', '1');
  });

  test('redesenha sem duplicar elementos ao mudar props', () => {
    const { container, rerender } = render(<Heatmap data={data} />);
    rerender(<Heatmap data={data.slice(0, 1)} showValues />);
    expect(cells(container)).toHaveLength(1);
    expect(container.querySelectorAll('svg > text')).toHaveLength(1);
    expect(container.querySelectorAll('linearGradient')).toHaveLength(1);
  });

  // Regressão #80: o id do gradiente era fixo, então dois heatmaps na mesma página
  // geravam ids duplicados e ambos referenciavam o primeiro gradiente.
  test('ids de gradiente são únicos entre instâncias', () => {
    const { container } = render(
      <div>
        <Heatmap data={data} colorScheme="blue" />
        <Heatmap data={data} colorScheme="red" />
      </div>
    );
    const ids = Array.from(container.querySelectorAll('linearGradient')).map((g) => g.id);
    expect(new Set(ids).size).toBe(2);
    // cada legenda referencia o seu próprio gradiente
    const fills = Array.from(container.querySelectorAll<SVGRectElement>('svg > g:nth-of-type(2) > rect')).map(
      (r) => r.style.fill
    );
    expect(fills).toHaveLength(2);
    ids.forEach((id, i) => {
      expect(id).toMatch(/^[A-Za-z0-9_-]+$/);
      expect(fills[i]).toContain(`#${id}`);
    });
  });
});

import { describe, test, expect, afterEach } from 'vitest';
import type { ComponentProps } from 'react';
import { render, fireEvent, createEvent, waitFor } from '@testing-library/react';
import NetworkGraph from './NetworkGraph';
import { NetworkGraph as NetworkGraphFromIndex } from './index';

type Props = ComponentProps<typeof NetworkGraph>;
type Node = Props['nodes'][number];
type Link = Props['links'][number];

/** Nó após passar pela simulação (d3 adiciona posição e fixação). */
type SimNode = Node & { x?: number; y?: number; fx?: number | null; fy?: number | null };
type SimLink = { source: SimNode | string; target: SimNode | string; value?: number };

// Os dados são mutados pela simulação, então cada teste recebe cópias novas.
function makeNodes(): Node[] {
  return [
    { id: 'alice', label: 'Alice', value: 20, category: 'new' },
    { id: 'bob', category: 'established' },
    { id: 'carol', label: 'Carol', category: 'mentor' },
    { id: 'dave', label: 'Dave', value: 5 },
  ];
}

function makeLinks(): Link[] {
  return [
    { source: 'alice', target: 'bob', value: 4 },
    { source: 'bob', target: 'carol' },
    { source: 'carol', target: 'dave', value: 9 },
  ];
}

function groups(container: HTMLElement) {
  const gs = container.querySelectorAll('svg > g');
  return { links: gs[0], nodes: gs[1], labels: gs[2] };
}

function circles(container: HTMLElement): SVGCircleElement[] {
  return Array.from(groups(container).nodes.querySelectorAll<SVGCircleElement>('circle'));
}

function lines(container: HTMLElement): SVGLineElement[] {
  return Array.from(groups(container).links.querySelectorAll<SVGLineElement>('line'));
}

function labels(container: HTMLElement): SVGTextElement[] {
  return Array.from(groups(container).labels.querySelectorAll<SVGTextElement>('text'));
}

type PointerEventName = 'mouseDown' | 'mouseMove' | 'mouseUp' | 'touchStart' | 'touchEnd';

interface FakeTouch {
  identifier: number;
  clientX: number;
  clientY: number;
  pageX: number;
  pageY: number;
}

/**
 * Dispara um evento de ponteiro com `view` (e toques) definidos.
 * O construtor do jsdom rejeita o `window` do ambiente de teste como `view`
 * e exige objetos `Touch` reais, então as propriedades são definidas na instância.
 */
function firePointer(
  target: Element | Window,
  name: PointerEventName,
  init: { clientX?: number; clientY?: number; button?: number } = {},
  touches?: { changedTouches: FakeTouch[]; touches: FakeTouch[] }
): void {
  const event = createEvent[name](target, { bubbles: true, cancelable: true, ...init });
  Object.defineProperty(event, 'view', { value: window });
  if (touches) {
    Object.defineProperty(event, 'changedTouches', { value: touches.changedTouches });
    Object.defineProperty(event, 'touches', { value: touches.touches });
  }
  fireEvent(target, event);
}

function touch(identifier: number, x: number, y: number): FakeTouch {
  return { identifier, clientX: x, clientY: y, pageX: x, pageY: y };
}

const CSS_VARS = ['--color-blue-trust-light', '--color-amber-accent', '--color-green-growth'];

describe('NetworkGraph', () => {
  afterEach(() => {
    CSS_VARS.forEach((v) => document.documentElement.style.removeProperty(v));
  });

  test('é reexportado pelo index', () => {
    expect(NetworkGraphFromIndex).toBe(NetworkGraph);
  });

  test('não desenha nada quando nodes está vazio', () => {
    const { container } = render(<NetworkGraph nodes={[]} links={[]} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('não desenha nada quando nodes é undefined', () => {
    const props = { nodes: undefined, links: [] } as unknown as Props;
    const { container } = render(<NetworkGraph {...props} />);
    expect(container.querySelector('svg')?.childNodes.length).toBe(0);
  });

  test('define atributos padrão do svg e cria três grupos', () => {
    const { container } = render(<NetworkGraph nodes={makeNodes()} links={makeLinks()} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '700');
    expect(svg).toHaveAttribute('height', '600');
    expect(svg).toHaveAttribute('viewBox', '0 0 700 600');
    expect(container.querySelectorAll('svg > g')).toHaveLength(3);
  });

  test('desenha uma linha por aresta com espessura baseada no valor', () => {
    const { container } = render(<NetworkGraph nodes={makeNodes()} links={makeLinks()} />);
    const ls = lines(container);
    expect(ls).toHaveLength(3);
    expect(ls.map((l) => l.getAttribute('stroke-width'))).toEqual(['2', '1', '3']);
    ls.forEach((l) => {
      expect(l).toHaveAttribute('stroke', '#475569');
      expect(l).toHaveAttribute('stroke-opacity', '0.6');
    });
  });

  test('desenha um círculo por nó com raio baseado no valor (padrão 50)', () => {
    const { container } = render(<NetworkGraph nodes={makeNodes()} links={makeLinks()} />);
    const cs = circles(container);
    expect(cs).toHaveLength(4);
    expect(cs.map((c) => Number(c.getAttribute('r')))).toEqual([
      10,
      Math.sqrt(250),
      Math.sqrt(250),
      5,
    ]);
    cs.forEach((c) => {
      expect(c).toHaveAttribute('stroke', '#1e293b');
      expect(c.style.cursor).toBe('pointer');
    });
  });

  test('rótulos usam label ou, na falta, o id', () => {
    const { container } = render(<NetworkGraph nodes={makeNodes()} links={makeLinks()} />);
    const ts = labels(container);
    expect(ts.map((t) => t.textContent)).toEqual(['Alice', 'bob', 'Carol', 'Dave']);
    ts.forEach((t) => {
      expect(t).toHaveAttribute('dy', '-15');
      expect(t.style.pointerEvents).toBe('none');
    });
  });

  test('cores padrão (fallback) por categoria', () => {
    const { container } = render(<NetworkGraph nodes={makeNodes()} links={makeLinks()} />);
    expect(circles(container).map((c) => c.getAttribute('fill'))).toEqual([
      '#64B5F6', // new
      '#FFB300', // established
      '#43A047', // categoria desconhecida → default
      '#43A047', // sem categoria → default
    ]);
  });

  test('cores padrão vêm das variáveis CSS do tema', () => {
    document.documentElement.style.setProperty('--color-blue-trust-light', '#000001');
    document.documentElement.style.setProperty('--color-amber-accent', '#000002');
    document.documentElement.style.setProperty('--color-green-growth', '#000003');
    const { container } = render(<NetworkGraph nodes={makeNodes()} links={makeLinks()} />);
    expect(circles(container).map((c) => c.getAttribute('fill'))).toEqual([
      '#000001',
      '#000002',
      '#000003',
      '#000003',
    ]);
  });

  test('cores personalizadas têm prioridade sobre as padrão', () => {
    const colors = { mentor: '#ff00ff', new: '#00ffff' };
    const { container } = render(
      <NetworkGraph nodes={makeNodes()} links={makeLinks()} colors={colors} />
    );
    expect(circles(container).map((c) => c.getAttribute('fill'))).toEqual([
      '#00ffff',
      '#FFB300',
      '#ff00ff',
      '#43A047',
    ]);
  });

  test('a simulação atualiza posições de nós, arestas e rótulos a cada tick', async () => {
    const nodes = makeNodes();
    const { container } = render(
      <NetworkGraph nodes={nodes} links={makeLinks()} width={400} height={300} />
    );

    await waitFor(() => {
      expect(circles(container)[0].getAttribute('cx')).not.toBeNull();
    });

    const cs = circles(container);
    const ts = labels(container);
    cs.forEach((c, i) => {
      const n = nodes[i] as SimNode;
      expect(Number(c.getAttribute('cx'))).toBeCloseTo(n.x ?? NaN, 5);
      expect(Number(c.getAttribute('cy'))).toBeCloseTo(n.y ?? NaN, 5);
      expect(ts[i].getAttribute('x')).toBe(c.getAttribute('cx'));
      expect(ts[i].getAttribute('y')).toBe(c.getAttribute('cy'));
    });

    // Arestas ligam os nós corretos
    const ls = lines(container);
    expect(ls[0].getAttribute('x1')).toBe(cs[0].getAttribute('cx'));
    expect(ls[0].getAttribute('y2')).toBe(cs[1].getAttribute('cy'));
    expect(ls[2].getAttribute('x1')).toBe(cs[2].getAttribute('cx'));
    expect(ls[2].getAttribute('x2')).toBe(cs[3].getAttribute('cx'));
    ls.forEach((l) => {
      ['x1', 'y1', 'x2', 'y2'].forEach((attr) => {
        expect(Number.isFinite(Number(l.getAttribute(attr)))).toBe(true);
      });
    });
  });

  test('a simulação resolve as arestas por id', () => {
    const links = makeLinks();
    render(<NetworkGraph nodes={makeNodes()} links={links} />);
    const first = links[0] as unknown as SimLink;
    expect(typeof first.source).toBe('object');
    expect((first.source as SimNode).id).toBe('alice');
    expect((first.target as SimNode).id).toBe('bob');
  });

  test('arrastar um nó fixa sua posição e solta ao final', () => {
    const nodes = makeNodes();
    const { container } = render(<NetworkGraph nodes={nodes} links={makeLinks()} />);
    const circle = circles(container)[0];
    const node = nodes[0] as SimNode;
    const startX = node.x;
    const startY = node.y;
    expect(startX).toEqual(expect.any(Number));

    firePointer(circle, 'mouseDown', { clientX: 100, clientY: 100, button: 0 });
    // dragstarted fixa o nó na posição atual
    expect(node.fx).toBe(startX);
    expect(node.fy).toBe(startY);

    firePointer(window, 'mouseMove', { clientX: 150, clientY: 130 });
    // dragged move a posição fixa pelo deslocamento do ponteiro
    expect(node.fx).toBeCloseTo((startX ?? 0) + 50, 5);
    expect(node.fy).toBeCloseTo((startY ?? 0) + 30, 5);

    firePointer(window, 'mouseUp', { clientX: 150, clientY: 130 });
    // dragended libera o nó
    expect(node.fx).toBeNull();
    expect(node.fy).toBeNull();
  });

  test('dois gestos simultâneos (toque) só reiniciam a simulação no primeiro', () => {
    const nodes = makeNodes();
    const { container } = render(<NetworkGraph nodes={nodes} links={makeLinks()} />);
    const [c0, c1] = circles(container);
    const n0 = nodes[0] as SimNode;
    const n1 = nodes[1] as SimNode;

    // Primeiro toque (event.active = 0)
    firePointer(c0, 'touchStart', {}, {
      changedTouches: [touch(1, 10, 10)],
      touches: [touch(1, 10, 10)],
    });
    expect(n0.fx).toBe(n0.x);
    expect(n0.fx).not.toBeUndefined();

    // Segundo toque simultâneo (event.active = 1)
    firePointer(c1, 'touchStart', {}, {
      changedTouches: [touch(2, 20, 20)],
      touches: [touch(1, 10, 10), touch(2, 20, 20)],
    });
    expect(n1.fx).toBe(n1.x);
    expect(n1.fx).not.toBeUndefined();

    // Termina o primeiro enquanto o segundo ainda está ativo
    firePointer(c0, 'touchEnd', {}, {
      changedTouches: [touch(1, 10, 10)],
      touches: [touch(2, 20, 20)],
    });
    expect(n0.fx).toBeNull();
    expect(n1.fx).toBe(n1.x);

    firePointer(c1, 'touchEnd', {}, {
      changedTouches: [touch(2, 20, 20)],
      touches: [],
    });
    expect(n1.fx).toBeNull();
  });

  test('sem arestas ainda desenha os nós', () => {
    const { container } = render(<NetworkGraph nodes={[{ id: 'solo' }]} links={[]} />);
    expect(circles(container)).toHaveLength(1);
    expect(lines(container)).toHaveLength(0);
    expect(labels(container)[0]).toHaveTextContent('solo');
  });

  test('redesenha sem duplicar e para a simulação ao desmontar', async () => {
    const { container, rerender, unmount } = render(
      <NetworkGraph nodes={makeNodes()} links={makeLinks()} />
    );
    const newNodes: Node[] = [{ id: 'x' }, { id: 'y' }];
    rerender(
      <NetworkGraph nodes={newNodes} links={[{ source: 'x', target: 'y' }]} width={300} />
    );
    expect(container.querySelectorAll('svg > g')).toHaveLength(3);
    expect(circles(container)).toHaveLength(2);
    expect(container.querySelector('svg')).toHaveAttribute('width', '300');

    const svg = container.querySelector('svg');
    await waitFor(() => {
      expect(circles(container)[0].getAttribute('cx')).not.toBeNull();
    });
    unmount();
    // Após desmontar, a simulação parada não altera mais as posições
    const n = newNodes[0] as SimNode;
    const x = n.x;
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(n.x).toBe(x);
    expect(svg?.isConnected).toBe(false);
  });
});

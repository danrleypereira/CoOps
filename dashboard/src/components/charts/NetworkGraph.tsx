import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface NetworkNode {
  id: string;
  label?: string;
  value?: number;
  category?: string;
}

interface NetworkLink {
  source: string;
  target: string;
  value?: number;
}

interface NetworkGraphProps {
  nodes: NetworkNode[];
  links: NetworkLink[];
  width?: number;
  height?: number;
  colors?: Record<string, string>;
}

/**
 * NetworkGraph Component (Force-Directed Graph)
 *
 * Creates a force-directed network graph using d3.js
 * Use case: Collaboration networks, team relationships
 *
 * @param nodes - Array of nodes with id and optional properties
 * @param links - Array of edges connecting nodes
 * @param width - Chart width (default: 700)
 * @param height - Chart height (default: 600)
 * @param colors - Custom colors by category
 */
export default function NetworkGraph({
  nodes,
  links,
  width = 700,
  height = 600,
  colors,
}: NetworkGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !nodes || nodes.length === 0) return;

    d3.select(svgRef.current).selectAll('*').remove();

    const defaultColors: Record<string, string> = {
      new:
        getComputedStyle(document.documentElement)
          .getPropertyValue('--color-blue-trust-light')
          .trim() || '#64B5F6',
      established:
        getComputedStyle(document.documentElement)
          .getPropertyValue('--color-amber-accent')
          .trim() || '#FFB300',
      default:
        getComputedStyle(document.documentElement)
          .getPropertyValue('--color-green-growth')
          .trim() || '#43A047',
    };

    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    // Create simulation
    const simulation = d3
      .forceSimulation(nodes as any)
      .force(
        'link',
        d3
          .forceLink(links)
          .id((d: any) => d.id)
          .distance(80)
      )
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30));

    // Draw links
    const link = svg
      .append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', '#475569')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', (d) => Math.sqrt(d.value || 1));

    // Draw nodes
    const node = svg
      .append('g')
      .selectAll('circle')
      .data(nodes)
      .enter()
      .append('circle')
      .attr('r', (d) => Math.sqrt((d.value || 50) * 5))
      .attr('fill', (d) =>
        d.category
          ? colors?.[d.category] || defaultColors[d.category] || defaultColors.default
          : defaultColors.default
      )
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .call(drag(simulation) as any);

    // Add labels
    const label = svg
      .append('g')
      .selectAll('text')
      .data(nodes)
      .enter()
      .append('text')
      .text((d) => d.label || d.id)
      .attr('font-size', 10)
      .attr('fill', '#e2e8f0')
      .attr('text-anchor', 'middle')
      .attr('dy', -15)
      .style('pointer-events', 'none');

    // Update positions
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node.attr('cx', (d: any) => d.x).attr('cy', (d: any) => d.y);

      label.attr('x', (d: any) => d.x).attr('y', (d: any) => d.y);
    });

    // Drag behavior
    function drag(simulation: d3.Simulation<any, undefined>) {
      function dragstarted(event: any) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
      }

      function dragged(event: any) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
      }

      function dragended(event: any) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
      }

      return d3
        .drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended);
    }

    return () => {
      simulation.stop();
    };
  }, [nodes, links, width, height, colors]);

  return <svg ref={svgRef} />;
}

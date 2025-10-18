import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface ScatterPlotData {
  x: number;
  y: number;
  label?: string;
  category?: string;
}

interface ScatterPlotProps {
  data: ScatterPlotData[];
  width?: number;
  height?: number;
  xLabel?: string;
  yLabel?: string;
  colors?: Record<string, string>;
}

/**
 * ScatterPlot Component
 *
 * Creates a scatter plot using d3.js with optional categorical coloring
 * Use case: Maturity score vs contributions, followers vs repos
 *
 * @param data - Array of {x, y, label, category} objects
 * @param width - Chart width (default: 600)
 * @param height - Chart height (default: 400)
 * @param xLabel - X-axis label
 * @param yLabel - Y-axis label
 * @param colors - Custom colors by category
 */
export default function ScatterPlot({
  data,
  width = 600,
  height = 400,
  xLabel,
  yLabel,
  colors,
}: ScatterPlotProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0) return;

    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 20, right: 100, bottom: 60, left: 60 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const defaultColors: Record<string, string> = {
      new:
        getComputedStyle(document.documentElement)
          .getPropertyValue('--color-blue-trust')
          .trim() || '#1E88E5',
      established:
        getComputedStyle(document.documentElement)
          .getPropertyValue('--color-amber-accent')
          .trim() || '#FFB300',
    };

    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Scales
    const x = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.x) || 0])
      .nice()
      .range([0, innerWidth]);

    const y = d3
      .scaleLinear()
      .domain([0, d3.max(data, (d) => d.y) || 0])
      .nice()
      .range([innerHeight, 0]);

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(d3.axisBottom(x))
      .selectAll('text')
      .attr('fill', '#e2e8f0');

    g.append('g').call(d3.axisLeft(y)).selectAll('text').attr('fill', '#e2e8f0');

    // Dots
    g.selectAll('circle')
      .data(data)
      .enter()
      .append('circle')
      .attr('cx', (d) => x(d.x))
      .attr('cy', (d) => y(d.y))
      .attr('r', 6)
      .attr('fill', (d) =>
        d.category
          ? colors?.[d.category] || defaultColors[d.category] || '#64B5F6'
          : '#64B5F6'
      )
      .attr('opacity', 0.7)
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
      .style('cursor', 'pointer')
      .on('mouseover', function () {
        d3.select(this).attr('r', 8).attr('opacity', 1);
      })
      .on('mouseout', function () {
        d3.select(this).attr('r', 6).attr('opacity', 0.7);
      });

    // Labels
    if (xLabel) {
      g.append('text')
        .attr('x', innerWidth / 2)
        .attr('y', innerHeight + 45)
        .attr('text-anchor', 'middle')
        .attr('fill', '#e2e8f0')
        .text(xLabel);
    }

    if (yLabel) {
      g.append('text')
        .attr('transform', 'rotate(-90)')
        .attr('x', -innerHeight / 2)
        .attr('y', -40)
        .attr('text-anchor', 'middle')
        .attr('fill', '#e2e8f0')
        .text(yLabel);
    }

    // Legend
    const categories = Array.from(new Set(data.map((d) => d.category).filter(Boolean)));
    if (categories.length > 0) {
      const legend = svg
        .append('g')
        .attr('transform', `translate(${width - 90}, ${margin.top})`);

      categories.forEach((cat, i) => {
        const row = legend.append('g').attr('transform', `translate(0, ${i * 25})`);

        row
          .append('circle')
          .attr('cx', 7)
          .attr('cy', 7)
          .attr('r', 6)
          .attr('fill', colors?.[cat!] || defaultColors[cat!] || '#64B5F6');

        row
          .append('text')
          .attr('x', 20)
          .attr('y', 11)
          .attr('fill', '#e2e8f0')
          .attr('font-size', '12px')
          .text(cat!);
      });
    }

    g.selectAll('.domain, .tick line').attr('stroke', '#475569');
  }, [data, width, height, xLabel, yLabel, colors]);

  return <svg ref={svgRef} />;
}

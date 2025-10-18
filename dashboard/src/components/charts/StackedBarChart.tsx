import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface StackedBarData {
  label: string;
  [key: string]: string | number;
}

interface StackedBarChartProps {
  data: StackedBarData[];
  keys: string[];
  width?: number;
  height?: number;
  colors?: string[];
  xLabel?: string;
  yLabel?: string;
}

/**
 * StackedBarChart Component
 *
 * Creates a stacked bar chart using d3.js
 * Use case: Issues/PRs/Commits per repository, multi-metric comparison
 *
 * @param data - Array of objects with label and values
 * @param keys - Array of keys to stack
 * @param width - Chart width (default: 700)
 * @param height - Chart height (default: 400)
 * @param colors - Custom colors for each stack
 * @param xLabel - X-axis label
 * @param yLabel - Y-axis label
 */
export default function StackedBarChart({
  data,
  keys,
  width = 700,
  height = 400,
  colors,
  xLabel,
  yLabel,
}: StackedBarChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0 || !keys || keys.length === 0)
      return;

    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 20, right: 120, bottom: 80, left: 60 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const defaultColors = [
      getComputedStyle(document.documentElement)
        .getPropertyValue('--color-blue-trust')
        .trim() || '#1E88E5',
      getComputedStyle(document.documentElement)
        .getPropertyValue('--color-green-growth')
        .trim() || '#43A047',
      getComputedStyle(document.documentElement)
        .getPropertyValue('--color-amber-accent')
        .trim() || '#FFB300',
      '#9C27B0',
      '#F44336',
    ];

    const colorScale = d3
      .scaleOrdinal<string>()
      .domain(keys)
      .range(colors || defaultColors);

    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Stack the data
    const stack = d3.stack<StackedBarData>().keys(keys);
    const series = stack(data);

    // Scales
    const x = d3
      .scaleBand()
      .domain(data.map((d) => d.label))
      .range([0, innerWidth])
      .padding(0.2);

    const y = d3
      .scaleLinear()
      .domain([
        0,
        d3.max(series, (layer) => d3.max(layer, (d) => d[1])) || 0,
      ])
      .nice()
      .range([innerHeight, 0]);

    // Draw stacked bars
    g.selectAll('g.layer')
      .data(series)
      .enter()
      .append('g')
      .attr('class', 'layer')
      .attr('fill', (d) => colorScale(d.key))
      .selectAll('rect')
      .data((d) => d)
      .enter()
      .append('rect')
      .attr('x', (d) => x((d.data as StackedBarData).label) || 0)
      .attr('y', (d) => y(d[1]))
      .attr('height', (d) => y(d[0]) - y(d[1]))
      .attr('width', x.bandwidth())
      .attr('opacity', 0.9)
      .style('cursor', 'pointer')
      .on('mouseover', function () {
        d3.select(this).attr('opacity', 1);
      })
      .on('mouseout', function () {
        d3.select(this).attr('opacity', 0.9);
      });

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(d3.axisBottom(x))
      .selectAll('text')
      .attr('transform', 'rotate(-45)')
      .style('text-anchor', 'end')
      .attr('fill', '#e2e8f0');

    g.append('g').call(d3.axisLeft(y)).selectAll('text').attr('fill', '#e2e8f0');

    // Legend
    const legend = svg
      .append('g')
      .attr('transform', `translate(${width - 100}, ${margin.top})`);

    keys.forEach((key, i) => {
      const row = legend.append('g').attr('transform', `translate(0, ${i * 25})`);

      row
        .append('rect')
        .attr('width', 15)
        .attr('height', 15)
        .attr('fill', colorScale(key))
        .attr('rx', 2);

      row
        .append('text')
        .attr('x', 20)
        .attr('y', 12)
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px')
        .text(key);
    });

    // Labels
    if (xLabel) {
      g.append('text')
        .attr('x', innerWidth / 2)
        .attr('y', innerHeight + margin.bottom - 10)
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

    g.selectAll('.domain, .tick line').attr('stroke', '#475569');
  }, [data, keys, width, height, colors, xLabel, yLabel]);

  return <svg ref={svgRef} />;
}

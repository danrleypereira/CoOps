import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface HeatmapData {
  row: string | number;
  col: string | number;
  value: number;
}

interface HeatmapProps {
  data: HeatmapData[];
  width?: number;
  height?: number;
  rowLabels?: string[];
  colLabels?: string[];
  colorScheme?: 'blue' | 'green' | 'red' | 'amber';
  showValues?: boolean;
}

/**
 * Heatmap Component
 *
 * Creates a heatmap visualization using d3.js
 * Use case: Activity by day/hour, contribution patterns over time
 *
 * @param data - Array of {row, col, value} objects
 * @param width - Chart width (default: 800)
 * @param height - Chart height (default: 400)
 * @param rowLabels - Labels for rows (e.g., days of week)
 * @param colLabels - Labels for columns (e.g., hours)
 * @param colorScheme - Color gradient scheme (default: 'blue')
 * @param showValues - Display values in cells (default: false)
 */
export default function Heatmap({
  data,
  width = 800,
  height = 400,
  rowLabels,
  colLabels,
  colorScheme = 'blue',
  showValues = false,
}: HeatmapProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0) return;

    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 60, right: 30, bottom: 60, left: 80 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    // Get unique rows and columns
    const rows = rowLabels || Array.from(new Set(data.map((d) => String(d.row))));
    const cols = colLabels || Array.from(new Set(data.map((d) => String(d.col))));

    // Color schemes
    const colorSchemes = {
      blue: ['#f0f9ff', '#0ea5e9', '#0369a1'],
      green: ['#f0fdf4', '#22c55e', '#15803d'],
      red: ['#fef2f2', '#ef4444', '#b91c1c'],
      amber: ['#fffbeb', '#f59e0b', '#b45309'],
    };

    const colors = colorSchemes[colorScheme];
    const maxValue = d3.max(data, (d) => d.value) || 1;

    const colorScale = d3
      .scaleLinear<string>()
      .domain([0, maxValue / 2, maxValue])
      .range(colors);

    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Scales
    const x = d3.scaleBand().domain(cols).range([0, innerWidth]).padding(0.05);

    const y = d3.scaleBand().domain(rows).range([0, innerHeight]).padding(0.05);

    // Draw cells
    g.selectAll('rect')
      .data(data)
      .enter()
      .append('rect')
      .attr('x', (d) => x(String(d.col)) || 0)
      .attr('y', (d) => y(String(d.row)) || 0)
      .attr('width', x.bandwidth())
      .attr('height', y.bandwidth())
      .attr('fill', (d) => (d.value > 0 ? colorScale(d.value) : '#1e293b'))
      .attr('stroke', '#0f172a')
      .attr('stroke-width', 1)
      .style('cursor', 'pointer')
      .on('mouseover', function () {
        d3.select(this).attr('stroke', '#64B5F6').attr('stroke-width', 2);
      })
      .on('mouseout', function () {
        d3.select(this).attr('stroke', '#0f172a').attr('stroke-width', 1);
      });

    // Add values to cells (if enabled)
    if (showValues) {
      g.selectAll('text.value')
        .data(data)
        .enter()
        .append('text')
        .attr('class', 'value')
        .attr('x', (d) => (x(String(d.col)) || 0) + x.bandwidth() / 2)
        .attr('y', (d) => (y(String(d.row)) || 0) + y.bandwidth() / 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', (d) => (d.value > maxValue / 2 ? '#fff' : '#e2e8f0'))
        .attr('font-size', '10px')
        .text((d) => (d.value > 0 ? d.value : ''));
    }

    // X axis (column labels)
    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(d3.axisBottom(x))
      .selectAll('text')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '12px');

    // Y axis (row labels)
    g.append('g')
      .call(d3.axisLeft(y))
      .selectAll('text')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '12px');

    // Title
    svg
      .append('text')
      .attr('x', width / 2)
      .attr('y', margin.top / 2)
      .attr('text-anchor', 'middle')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '16px')
      .attr('font-weight', 'bold')
      .text('Activity Heatmap');

    // Color legend
    const legendWidth = 200;
    const legendHeight = 10;
    const legendX = width - legendWidth - margin.right;
    const legendY = 20;

    const legend = svg.append('g').attr('transform', `translate(${legendX},${legendY})`);

    const legendScale = d3
      .scaleLinear()
      .domain([0, maxValue])
      .range([0, legendWidth]);

    const legendAxis = d3.axisBottom(legendScale).ticks(4);

    // Gradient for legend
    const defs = svg.append('defs');
    const gradient = defs
      .append('linearGradient')
      .attr('id', 'heatmap-gradient')
      .attr('x1', '0%')
      .attr('x2', '100%');

    gradient.append('stop').attr('offset', '0%').attr('stop-color', colors[0]);
    gradient.append('stop').attr('offset', '50%').attr('stop-color', colors[1]);
    gradient.append('stop').attr('offset', '100%').attr('stop-color', colors[2]);

    legend
      .append('rect')
      .attr('width', legendWidth)
      .attr('height', legendHeight)
      .style('fill', 'url(#heatmap-gradient)');

    legend
      .append('g')
      .attr('transform', `translate(0,${legendHeight})`)
      .call(legendAxis)
      .selectAll('text')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '10px');

    legend.selectAll('.domain, .tick line').attr('stroke', '#475569');

    g.selectAll('.domain, .tick line').attr('stroke', '#475569');
  }, [data, width, height, rowLabels, colLabels, colorScheme, showValues]);

  return <svg ref={svgRef} />;
}

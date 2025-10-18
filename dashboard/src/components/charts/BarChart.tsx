import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface BarChartData {
  label: string;
  value: number;
}

interface BarChartProps {
  data: BarChartData[];
  width?: number;
  height?: number;
  orientation?: 'vertical' | 'horizontal';
  color?: string;
  xLabel?: string;
  yLabel?: string;
}

/**
 * BarChart Component
 *
 * Creates vertical or horizontal bar charts using d3.js
 * Use case: Contributions per member, commits per repository
 *
 * @param data - Array of {label, value} objects
 * @param width - Chart width (default: 600)
 * @param height - Chart height (default: 400)
 * @param orientation - 'vertical' or 'horizontal' (default: 'vertical')
 * @param color - Bar color (defaults to theme blue)
 * @param xLabel - X-axis label
 * @param yLabel - Y-axis label
 */
export default function BarChart({
  data,
  width = 600,
  height = 400,
  orientation = 'vertical',
  color,
  xLabel,
  yLabel,
}: BarChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0) return;

    // Clear previous chart
    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 20, right: 30, bottom: 80, left: 60 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    // Get theme color
    const barColor =
      color ||
      getComputedStyle(document.documentElement)
        .getPropertyValue('--color-blue-trust')
        .trim() ||
      '#1E88E5';

    // Create SVG
    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('aria-label', 'Histograma');

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    if (orientation === 'vertical') {
      // Vertical bar chart
      const x = d3
        .scaleBand()
        .domain(data.map((d) => d.label))
        .range([0, innerWidth])
        .padding(0.2);

      const y = d3
        .scaleLinear()
        .domain([0, d3.max(data, (d) => d.value) || 0])
        .nice()
        .range([innerHeight, 0]);

      // X axis
      g.append('g')
        .attr('transform', `translate(0,${innerHeight})`)
        .call(d3.axisBottom(x))
        .selectAll('text')
        .attr('transform', 'rotate(-45)')
        .style('text-anchor', 'end')
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px');

      // Y axis
      g.append('g')
        .call(d3.axisLeft(y))
        .selectAll('text')
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px');

      // Bars
      g.selectAll('rect')
        .data(data)
        .enter()
        .append('rect')
        .attr('x', (d) => x(d.label) || 0)
        .attr('y', (d) => y(d.value))
        .attr('width', x.bandwidth())
        .attr('height', (d) => innerHeight - y(d.value))
        .attr('fill', barColor)
        .style('opacity', 0.9)
        .style('cursor', 'pointer')
        .on('mouseover', function () {
          d3.select(this).style('opacity', 1);
        })
        .on('mouseout', function () {
          d3.select(this).style('opacity', 0.9);
        });

      // Add axis labels
      if (xLabel) {
        g.append('text')
          .attr('x', innerWidth / 2)
          .attr('y', innerHeight + margin.bottom - 10)
          .attr('text-anchor', 'middle')
          .attr('fill', '#e2e8f0')
          .attr('font-size', '14px')
          .text(xLabel);
      }

      if (yLabel) {
        g.append('text')
          .attr('transform', 'rotate(-90)')
          .attr('x', -innerHeight / 2)
          .attr('y', -margin.left + 15)
          .attr('text-anchor', 'middle')
          .attr('fill', '#e2e8f0')
          .attr('font-size', '14px')
          .text(yLabel);
      }
    } else {
      // Horizontal bar chart
      const x = d3
        .scaleLinear()
        .domain([0, d3.max(data, (d) => d.value) || 0])
        .nice()
        .range([0, innerWidth]);

      const y = d3
        .scaleBand()
        .domain(data.map((d) => d.label))
        .range([0, innerHeight])
        .padding(0.2);

      // X axis
      g.append('g')
        .attr('transform', `translate(0,${innerHeight})`)
        .call(d3.axisBottom(x))
        .selectAll('text')
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px');

      // Y axis
      g.append('g')
        .call(d3.axisLeft(y))
        .selectAll('text')
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px');

      // Bars
      g.selectAll('rect')
        .data(data)
        .enter()
        .append('rect')
        .attr('x', 0)
        .attr('y', (d) => y(d.label) || 0)
        .attr('width', (d) => x(d.value))
        .attr('height', y.bandwidth())
        .attr('fill', barColor)
        .style('opacity', 0.9)
        .style('cursor', 'pointer')
        .on('mouseover', function () {
          d3.select(this).style('opacity', 1);
        })
        .on('mouseout', function () {
          d3.select(this).style('opacity', 0.9);
        });
    }

    // Style axes
    g.selectAll('.domain, .tick line').attr('stroke', '#475569');
  }, [data, width, height, orientation, color, xLabel, yLabel]);

  return <svg ref={svgRef} />;
}

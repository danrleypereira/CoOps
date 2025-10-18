import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface LineChartData {
  date: Date | string;
  value: number;
}

interface LineChartProps {
  data: LineChartData[];
  width?: number;
  height?: number;
  color?: string;
  showDots?: boolean;
  xLabel?: string;
  yLabel?: string;
  showArea?: boolean;
}

/**
 * LineChart Component (Time-Series)
 *
 * Creates a line chart for time-series data using d3.js
 * Use case: Commits over time, activity trends, burndown charts
 *
 * @param data - Array of {date, value} objects
 * @param width - Chart width (default: 700)
 * @param height - Chart height (default: 400)
 * @param color - Line color (defaults to theme blue)
 * @param showDots - Show data points as dots (default: true)
 * @param xLabel - X-axis label
 * @param yLabel - Y-axis label
 * @param showArea - Fill area under the line (default: false)
 */
export default function LineChart({
  data,
  width = 700,
  height = 400,
  color,
  showDots = true,
  xLabel,
  yLabel,
  showArea = false,
}: LineChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0) return;

    // Clear previous chart
    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 20, right: 30, bottom: 60, left: 60 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    // Parse dates
    const parsedData = data.map((d) => ({
      date: typeof d.date === 'string' ? new Date(d.date) : d.date,
      value: d.value,
    }));

    // Get theme color
    const lineColor =
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
      .attr('aria-label', 'Line chart');

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Create scales
    const x = d3
      .scaleTime()
      .domain(d3.extent(parsedData, (d) => d.date) as [Date, Date])
      .range([0, innerWidth]);

    const y = d3
      .scaleLinear()
      .domain([0, d3.max(parsedData, (d) => d.value) || 0])
      .nice()
      .range([innerHeight, 0]);

    // Create line generator
    const line = d3
      .line<{ date: Date; value: number }>()
      .x((d) => x(d.date))
      .y((d) => y(d.value))
      .curve(d3.curveMonotoneX);

    // Create area generator (if showArea is true)
    const area = d3
      .area<{ date: Date; value: number }>()
      .x((d) => x(d.date))
      .y0(innerHeight)
      .y1((d) => y(d.value))
      .curve(d3.curveMonotoneX);

    // Add area fill (if enabled)
    if (showArea) {
      g.append('path')
        .datum(parsedData)
        .attr('fill', lineColor)
        .attr('opacity', 0.2)
        .attr('d', area);
    }

    // Add line
    g.append('path')
      .datum(parsedData)
      .attr('fill', 'none')
      .attr('stroke', lineColor)
      .attr('stroke-width', 2.5)
      .attr('d', line);

    // Add dots (if enabled)
    if (showDots) {
      g.selectAll('circle')
        .data(parsedData)
        .enter()
        .append('circle')
        .attr('cx', (d) => x(d.date))
        .attr('cy', (d) => y(d.value))
        .attr('r', 4)
        .attr('fill', lineColor)
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('mouseover', function () {
          d3.select(this).attr('r', 6);
        })
        .on('mouseout', function () {
          d3.select(this).attr('r', 4);
        });
    }

    // Add X axis
    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(
        d3
          .axisBottom(x)
          .ticks(6)
          .tickFormat((d) => d3.timeFormat('%b %d')(d as Date))
      )
      .selectAll('text')
      .attr('transform', 'rotate(-45)')
      .style('text-anchor', 'end')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '12px');

    // Add Y axis
    g.append('g')
      .call(d3.axisLeft(y))
      .selectAll('text')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '12px');

    // Add grid lines
    g.append('g')
      .attr('class', 'grid')
      .attr('opacity', 0.1)
      .call(d3.axisLeft(y).tickSize(-innerWidth).tickFormat(() => ''));

    // Add axis labels
    if (xLabel) {
      g.append('text')
        .attr('x', innerWidth / 2)
        .attr('y', innerHeight + margin.bottom - 5)
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

    // Style axes
    g.selectAll('.domain, .tick line:not(.grid line)').attr('stroke', '#475569');
  }, [data, width, height, color, showDots, xLabel, yLabel, showArea]);

  return <svg ref={svgRef} />;
}

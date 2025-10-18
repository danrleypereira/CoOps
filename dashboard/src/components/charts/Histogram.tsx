import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface HistogramProps {
  data: number[];
  width?: number;
  height?: number;
  bins?: number;
  color?: string;
  xLabel?: string;
  yLabel?: string;
  showKDE?: boolean;
}

/**
 * Histogram Component
 *
 * Creates a histogram showing data distribution using d3.js
 * Use case: Distribution of repos, followers, commit counts
 *
 * @param data - Array of numeric values
 * @param width - Chart width (default: 600)
 * @param height - Chart height (default: 400)
 * @param bins - Number of bins (default: auto)
 * @param color - Bar color (defaults to theme green)
 * @param xLabel - X-axis label
 * @param yLabel - Y-axis label
 * @param showKDE - Show kernel density estimation curve (default: false)
 */
export default function Histogram({
  data,
  width = 600,
  height = 400,
  bins,
  color,
  xLabel,
  yLabel,
  showKDE = false,
}: HistogramProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0) return;

    d3.select(svgRef.current).selectAll('*').remove();

    const margin = { top: 20, right: 30, bottom: 60, left: 60 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const barColor =
      color ||
      getComputedStyle(document.documentElement)
        .getPropertyValue('--color-green-growth')
        .trim() ||
      '#43A047';

    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`);

    const g = svg
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // X scale
    const x = d3
      .scaleLinear()
      .domain([0, d3.max(data) || 0])
      .nice()
      .range([0, innerWidth]);

    // Create histogram bins
    const histogram = d3.bin<number, number>().domain(x.domain() as [number, number]);

    // Set thresholds based on type
    if (bins !== undefined) {
      histogram.thresholds(bins);
    } else {
      histogram.thresholds(x.ticks(20));
    }

    const binData = histogram(data);

    // Y scale
    const y = d3
      .scaleLinear()
      .domain([0, d3.max(binData, (d) => d.length) || 0])
      .nice()
      .range([innerHeight, 0]);

    // Draw bars
    g.selectAll('rect')
      .data(binData)
      .enter()
      .append('rect')
      .attr('x', (d) => x(d.x0 || 0) + 1)
      .attr('y', (d) => y(d.length))
      .attr('width', (d) => Math.max(0, x(d.x1 || 0) - x(d.x0 || 0) - 2))
      .attr('height', (d) => innerHeight - y(d.length))
      .attr('fill', barColor)
      .attr('opacity', 0.8)
      .style('cursor', 'pointer')
      .on('mouseover', function () {
        d3.select(this).attr('opacity', 1);
      })
      .on('mouseout', function () {
        d3.select(this).attr('opacity', 0.8);
      });

    // Axes
    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(d3.axisBottom(x))
      .selectAll('text')
      .attr('fill', '#e2e8f0');

    g.append('g').call(d3.axisLeft(y)).selectAll('text').attr('fill', '#e2e8f0');

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

    g.selectAll('.domain, .tick line').attr('stroke', '#475569');
  }, [data, width, height, bins, color, xLabel, yLabel, showKDE]);

  return <svg ref={svgRef} />;
}

import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

/**
 * Silverman's rule-of-thumb bandwidth for a Gaussian kernel:
 * h = 0.9 * min(sd, IQR / 1.34) * n^(-1/5).
 * Falls back to whichever spread measure is positive; returns 0 when the
 * sample has no spread (e.g. a single value).
 */
export function silvermanBandwidth(values: number[]): number {
  const n = values.length;
  if (n < 2) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const sd = d3.deviation(sorted) ?? 0;
  const iqr = (d3.quantileSorted(sorted, 0.75) ?? 0) - (d3.quantileSorted(sorted, 0.25) ?? 0);
  const spreads = [sd, iqr / 1.34].filter((v) => v > 0);
  if (spreads.length === 0) return 0;
  return 0.9 * Math.min(...spreads) * Math.pow(n, -0.2);
}

/**
 * Gaussian kernel density estimate evaluated at each point of `xs`.
 * Returns density values (integrating to 1 over the real line).
 */
export function gaussianKDE(values: number[], bandwidth: number, xs: number[]): number[] {
  const n = values.length;
  const norm = 1 / (n * bandwidth * Math.sqrt(2 * Math.PI));
  return xs.map((x) => {
    let sum = 0;
    for (const v of values) {
      const u = (x - v) / bandwidth;
      sum += Math.exp(-0.5 * u * u);
    }
    return sum * norm;
  });
}

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

    // X scale (starts at 0 unless there are negative values, which must be counted)
    const x = d3
      .scaleLinear()
      .domain([Math.min(0, d3.min(data) ?? 0), d3.max(data) || 0])
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

    // Kernel density curve, scaled to histogram counts (density * n * binWidth)
    let kdePoints: [number, number][] = [];
    if (showKDE) {
      const bandwidth = silvermanBandwidth(data);
      const binWidths = binData
        .map((b) => (b.x1 ?? 0) - (b.x0 ?? 0))
        .filter((w) => w > 0);
      const binWidth = binWidths.length > 0 ? d3.mean(binWidths) ?? 0 : 0;
      if (bandwidth > 0 && binWidth > 0) {
        const [x0, x1] = x.domain();
        const steps = 100;
        const xs = d3.range(steps + 1).map((i) => x0 + ((x1 - x0) * i) / steps);
        const densities = gaussianKDE(data, bandwidth, xs);
        kdePoints = xs.map((xv, i) => [xv, densities[i] * data.length * binWidth]);
      }
    }

    // Y scale
    const y = d3
      .scaleLinear()
      .domain([
        0,
        Math.max(d3.max(binData, (d) => d.length) || 0, d3.max(kdePoints, (p) => p[1]) || 0),
      ])
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

    if (kdePoints.length > 0) {
      const line = d3
        .line<[number, number]>()
        .x((p) => x(p[0]))
        .y((p) => y(p[1]))
        .curve(d3.curveBasis);

      g.append('path')
        .datum(kdePoints)
        .attr('class', 'kde-curve')
        .attr('fill', 'none')
        .attr('stroke', '#e2e8f0')
        .attr('stroke-width', 2)
        .attr('d', line);
    }

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

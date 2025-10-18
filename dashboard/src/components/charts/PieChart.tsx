import { useEffect, useRef } from 'react';
import * as d3 from 'd3';

interface PieChartData {
  label: string;
  value: number;
}

interface PieChartProps {
  data: PieChartData[];
  width?: number;
  height?: number;
  innerRadius?: number;
  colors?: string[];
  showLabels?: boolean;
}

/**
 * PieChart Component (Donut Chart)
 *
 * Creates a pie or donut chart using d3.js
 * Use case: Member contribution distribution, status breakdowns
 *
 * @param data - Array of {label, value} objects
 * @param width - Chart width (default: 400)
 * @param height - Chart height (default: 400)
 * @param innerRadius - Inner radius for donut effect (0 for pie chart, default: 60)
 * @param colors - Custom color array (defaults to theme colors)
 * @param showLabels - Show percentage labels (default: true)
 */
export default function PieChart({
  data,
  width = 400,
  height = 400,
  innerRadius = 60,
  colors,
  showLabels = true,
}: PieChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || data.length === 0) return;

    // Clear previous chart
    d3.select(svgRef.current).selectAll('*').remove();

    const radius = Math.min(width, height) / 2;

    // Get theme colors from CSS variables if not provided
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
      '#00BCD4',
      '#FF9800',
      '#4CAF50',
    ];

    const colorScale = d3
      .scaleOrdinal<string>()
      .domain(data.map((d) => d.label))
      .range(colors || defaultColors);

    // Create SVG
    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('aria-label', 'Gráfico de pizza');

    const g = svg
      .append('g')
      .attr('transform', `translate(${width / 2}, ${height / 2})`);

    // Create pie layout
    const pie = d3
      .pie<PieChartData>()
      .value((d) => d.value)
      .sort(null);

    // Create arc generator
    const arc = d3
      .arc<d3.PieArcDatum<PieChartData>>()
      .innerRadius(innerRadius)
      .outerRadius(radius - 10);

    // Create arc for labels (slightly outside the pie)
    const labelArc = d3
      .arc<d3.PieArcDatum<PieChartData>>()
      .innerRadius(radius - 30)
      .outerRadius(radius - 30);

    // Draw slices
    const slices = g
      .selectAll('path')
      .data(pie(data))
      .enter()
      .append('path')
      .attr('d', arc)
      .attr('fill', (d) => colorScale(d.data.label))
      .attr('stroke', '#1e293b')
      .attr('stroke-width', 2)
      .style('opacity', 0.9)
      .style('cursor', 'pointer')
      .on('mouseover', function () {
        d3.select(this).style('opacity', 1).style('filter', 'brightness(1.1)');
      })
      .on('mouseout', function () {
        d3.select(this).style('opacity', 0.9).style('filter', 'none');
      });

    // Add labels with percentages
    if (showLabels) {
      const total = d3.sum(data, (d) => d.value);

      g.selectAll('text')
        .data(pie(data))
        .enter()
        .append('text')
        .attr('transform', (d) => `translate(${labelArc.centroid(d)})`)
        .attr('text-anchor', 'middle')
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px')
        .attr('font-weight', 'bold')
        .text((d) => {
          const percentage = ((d.data.value / total) * 100).toFixed(1);
          return percentage !== '0.0' ? `${percentage}%` : '';
        });
    }

    // Add legend
    const legend = svg
      .append('g')
      .attr('transform', `translate(${width - 120}, 20)`);

    data.forEach((item, i) => {
      const legendRow = legend
        .append('g')
        .attr('transform', `translate(0, ${i * 25})`);

      legendRow
        .append('rect')
        .attr('width', 15)
        .attr('height', 15)
        .attr('fill', colorScale(item.label))
        .attr('rx', 2);

      legendRow
        .append('text')
        .attr('x', 20)
        .attr('y', 12)
        .attr('fill', '#e2e8f0')
        .attr('font-size', '12px')
        .text(item.label);
    });
  }, [data, width, height, innerRadius, colors, showLabels]);

  return <svg ref={svgRef} />;
}

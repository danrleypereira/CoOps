import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { VisualizationTabs } from './VisualizationTabs';

describe('VisualizationTabs', () => {
  test('destaca a aba treemap quando ativa', () => {
    render(<VisualizationTabs activeMode="treemap" onModeChange={vi.fn()} />);

    const treemap = screen.getByRole('button', { name: /Treemap/ });
    const circle = screen.getByRole('button', { name: /Circle Pack/ });

    expect(treemap).toHaveClass('bg-blue-600', 'text-white', 'shadow-lg');
    expect(treemap).not.toHaveClass('text-slate-300');
    expect(circle).toHaveClass('text-slate-300');
    expect(circle).not.toHaveClass('bg-blue-600');
  });

  test('destaca a aba circlepack quando ativa', () => {
    render(<VisualizationTabs activeMode="circlepack" onModeChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: /Circle Pack/ })).toHaveClass('bg-blue-600');
    expect(screen.getByRole('button', { name: /Treemap/ })).not.toHaveClass('bg-blue-600');
  });

  test('chama onModeChange com o modo correspondente ao clicar', () => {
    const onModeChange = vi.fn();
    render(<VisualizationTabs activeMode="treemap" onModeChange={onModeChange} />);

    fireEvent.click(screen.getByRole('button', { name: /Circle Pack/ }));
    expect(onModeChange).toHaveBeenLastCalledWith('circlepack');

    fireEvent.click(screen.getByRole('button', { name: /Treemap/ }));
    expect(onModeChange).toHaveBeenLastCalledWith('treemap');
    expect(onModeChange).toHaveBeenCalledTimes(2);
  });

  test('alterna o destaque ao trocar a prop activeMode', () => {
    const { rerender } = render(
      <VisualizationTabs activeMode="treemap" onModeChange={vi.fn()} />,
    );
    rerender(<VisualizationTabs activeMode="circlepack" onModeChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: /Circle Pack/ })).toHaveClass('bg-blue-600');
    expect(screen.getByRole('button', { name: /Treemap/ })).toHaveClass('text-slate-300');
  });
});

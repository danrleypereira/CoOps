import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Loading from './Loading';

const getSpinner = (container: HTMLElement): HTMLElement => {
  const spinner = container.querySelector<HTMLElement>('.animate-spin');
  if (!spinner) throw new Error('spinner not found');
  return spinner;
};

describe('Loading', () => {
  test('renderiza mensagem padrão e spinner médio inline', () => {
    const { container } = render(<Loading />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    const spinner = getSpinner(container);
    expect(spinner).toHaveClass('w-12', 'h-12', 'border-3');
    expect(spinner.style.borderTopColor).toBe('var(--color-blue-trust)');

    const wrapper = container.firstElementChild as HTMLElement;
    expect(wrapper).toHaveClass('min-h-[200px]');
    expect(wrapper).not.toHaveClass('absolute');
  });

  test('renderiza mensagem customizada', () => {
    render(<Loading message="Carregando dados..." />);
    expect(screen.getByText('Carregando dados...')).toHaveClass('animate-pulse');
    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
  });

  test('não renderiza parágrafo quando a mensagem é vazia', () => {
    const { container } = render(<Loading message="" />);
    expect(container.querySelector('p')).toBeNull();
    expect(getSpinner(container)).toBeInTheDocument();
  });

  test.each([
    ['sm', ['w-6', 'h-6', 'border-2']],
    ['md', ['w-12', 'h-12', 'border-3']],
    ['lg', ['w-16', 'h-16', 'border-4']],
  ] as const)('aplica classes do tamanho %s', (size, classes) => {
    const { container } = render(<Loading size={size} />);
    expect(getSpinner(container)).toHaveClass(...classes);
  });

  test('renderiza como overlay quando overlay=true', () => {
    const { container } = render(<Loading overlay message="Processando" />);
    const wrapper = container.firstElementChild as HTMLElement;

    expect(wrapper).toHaveClass('absolute', 'inset-0', 'z-50');
    expect(wrapper).not.toHaveClass('min-h-[200px]');
    expect(wrapper.style.backgroundColor).toBe('rgba(24, 24, 24, 0.8)');
    expect(screen.getByText('Processando')).toBeInTheDocument();
    expect(wrapper.contains(getSpinner(container))).toBe(true);
  });
});

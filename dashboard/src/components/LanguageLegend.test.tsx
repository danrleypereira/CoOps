import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageLegend } from './LanguageLegend';

const colorMap: Record<string, string> = {
  TypeScript: '#2b7489',
  Python: '#3572A5',
  Unknown: '#cccccc',
};

const languages = [
  { language: 'TypeScript', percentage: 62.345, total_bytes: 1536 },
  { language: 'Python', percentage: 30, total_bytes: 5 * 1024 * 1024 },
  { language: 'Elixir', percentage: 7.66, total_bytes: 0 },
];

const getRow = (language: string): HTMLElement => {
  const row = screen.getByText(language).closest<HTMLElement>('.justify-between');
  if (!row) throw new Error(`row for ${language} not found`);
  return row;
};

const getDot = (row: HTMLElement): HTMLElement => {
  const dot = row.querySelector<HTMLElement>('.rounded-full');
  if (!dot) throw new Error('color dot not found');
  return dot;
};

describe('LanguageLegend', () => {
  test('renderiza título e uma linha por linguagem', () => {
    const { container } = render(<LanguageLegend languages={languages} colorMap={colorMap} />);

    expect(screen.getByText('Languages Distribution')).toBeInTheDocument();
    expect(container.querySelectorAll('.justify-between')).toHaveLength(3);
  });

  test('formata tamanhos e percentuais', () => {
    render(<LanguageLegend languages={languages} colorMap={colorMap} />);

    const ts = getRow('TypeScript');
    expect(ts).toHaveTextContent('1.5 KB');
    expect(ts).toHaveTextContent('62.3%');

    const py = getRow('Python');
    expect(py).toHaveTextContent('5 MB');
    expect(py).toHaveTextContent('30.0%');

    const ex = getRow('Elixir');
    expect(ex).toHaveTextContent('0 Bytes');
    expect(ex).toHaveTextContent('7.7%');
  });

  test('usa a cor do colorMap e cai para Unknown quando a linguagem não existe', () => {
    render(<LanguageLegend languages={languages} colorMap={colorMap} />);

    expect(getDot(getRow('TypeScript')).style.backgroundColor).toBe('rgb(43, 116, 137)');
    expect(getDot(getRow('Python')).style.backgroundColor).toBe('rgb(53, 114, 165)');
    expect(getDot(getRow('Elixir')).style.backgroundColor).toBe('rgb(204, 204, 204)');
  });

  test('sem cor quando nem a linguagem nem Unknown estão no colorMap', () => {
    render(
      <LanguageLegend
        languages={[{ language: 'Go', percentage: 100, total_bytes: 10 }]}
        colorMap={{}}
      />,
    );
    const row = getRow('Go');
    expect(getDot(row).style.backgroundColor).toBe('');
    expect(row).toHaveTextContent('10 Bytes');
  });

  test('renderiza apenas o título com lista vazia', () => {
    const { container } = render(<LanguageLegend languages={[]} colorMap={colorMap} />);
    expect(screen.getByText('Languages Distribution')).toBeInTheDocument();
    expect(container.querySelectorAll('.justify-between')).toHaveLength(0);
  });
});

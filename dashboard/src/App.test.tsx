import { describe, test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

vi.mock('./pages/AIAnalysis', () => ({
  default: () => <div data-testid="ai-analysis-page" />,
}));
vi.mock('./pages/NotFound', () => ({
  default: () => <div data-testid="not-found-page" />,
}));

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );

describe('App routes', () => {
  test('/ai renders the AI analysis page', () => {
    renderAt('/ai');
    expect(screen.getByTestId('ai-analysis-page')).toBeInTheDocument();
    expect(screen.queryByTestId('not-found-page')).not.toBeInTheDocument();
  });

  test('unknown paths fall back to NotFound', () => {
    renderAt('/does-not-exist');
    expect(screen.getByTestId('not-found-page')).toBeInTheDocument();
  });
});

import { describe, test, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { RepoStructureAnalysis } from './RepoStructureAnalysis';

type RepoData = ComponentProps<typeof RepoStructureAnalysis>['data'];
type Lang = RepoData['languages'][number];

const lang = (language: string, percentage: number, file_count = 1, total_bytes = 1024): Lang => ({
  language,
  percentage,
  file_count,
  total_bytes,
});

const makeRepo = (overrides: Partial<RepoData> = {}): RepoData => ({
  repository: 'demo-repo',
  owner: 'org',
  branch: 'main',
  total_files: 10,
  total_bytes: 2048,
  languages: [lang('TypeScript', 100)],
  ...overrides,
});

const HEADER = /Intelligent Structure Analysis/;

const openAnalysis = (data: RepoData) => {
  const utils = render(<RepoStructureAnalysis data={data} />);
  fireEvent.click(screen.getByRole('button', { name: HEADER }));
  return utils;
};

describe('RepoStructureAnalysis', () => {
  test('inicia recolhido, sem análise', () => {
    render(<RepoStructureAnalysis data={makeRepo()} />);

    const header = screen.getByRole('button', { name: HEADER });
    expect(header).toHaveTextContent('▶');
    expect(screen.queryByText(/Repository Structure Analysis/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Generate Analysis/)).not.toBeInTheDocument();
  });

  test('expande, gera análise e recolhe/expande sem regenerar', () => {
    render(<RepoStructureAnalysis data={makeRepo()} />);
    const header = screen.getByRole('button', { name: HEADER });

    fireEvent.click(header);
    expect(header).toHaveTextContent('▼');
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Repository Structure Analysis');
    expect(screen.queryByText(/Analyzing repository structure/)).not.toBeInTheDocument();

    fireEvent.click(header);
    expect(header).toHaveTextContent('▶');
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();

    fireEvent.click(header);
    expect(header).toHaveTextContent('▼');
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1);
  });

  test('renderiza headings, listas e negrito a partir do markdown', () => {
    const { container } = openAnalysis(makeRepo());

    const h3 = screen.getAllByRole('heading', { level: 3 }).map(h => h.textContent);
    expect(h3).toEqual(expect.arrayContaining([
      '🎯 Primary Language',
      '🏗️ Inferred Architecture',
      '📊 Complexity Metrics',
      '💡 Recommendations',
    ]));
    // Sem linguagens secundárias -> sem seção complementar
    expect(h3).not.toContain('🔧 Complementary Languages');

    const strongTexts = Array.from(container.querySelectorAll('strong')).map(s => s.textContent);
    expect(strongTexts).toEqual(expect.arrayContaining(['TypeScript', '100.0%', 'Total Files']));
    expect(container.querySelectorAll('li').length).toBeGreaterThan(0);
    expect(container.querySelectorAll('br').length).toBeGreaterThan(0);
  });

  test('projeto TypeScript pequeno: insight, arquitetura JS/TS, baixa complexidade e recomendações', () => {
    openAnalysis(makeRepo({ total_bytes: 0 }));

    expect(screen.getByText(/demonstrates a modern project with static typing/)).toBeInTheDocument();
    expect(screen.getByText(/Modern web application \(React\/Vue\/Angular\)/)).toBeInTheDocument();
    expect(screen.getByText(/^: 0 Bytes$/)).toBeInTheDocument();
    expect(screen.getByText(/Compact project, possibly in an early stage/)).toBeInTheDocument();
    expect(screen.getByText(/10 files per language on average/)).toBeInTheDocument();
    // 100% em uma linguagem -> diversificação
    expect(screen.getByText(/of the code is in a single language/)).toBeInTheDocument();
    // Sem Markdown -> documentação
    expect(screen.getByText(/Add Markdown files/)).toBeInTheDocument();
    // total_files <= 30 -> sem recomendação de testes
    expect(screen.queryByText(/Consider adding automated tests/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Standardization/)).not.toBeInTheDocument();
  });

  test('arquitetura web completa com backend Python e linguagens secundárias', () => {
    openAnalysis(makeRepo({
      total_files: 120,
      total_bytes: 3 * 1024 * 1024,
      languages: [
        lang('Python', 50, 40, 2048),
        lang('HTML', 20),
        lang('SCSS', 15),
        lang('JavaScript', 10),
        lang('Markdown', 5),
      ],
    }));

    expect(screen.getByText(/Python is known for its versatility/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '🔧 Complementary Languages' })).toBeInTheDocument();
    expect(screen.getByText(/User interface and web content structuring/)).toBeInTheDocument();
    expect(screen.getByText(/Additional project support/)).toBeInTheDocument(); // SCSS
    expect(screen.getByText(/Interactivity and frontend logic/)).toBeInTheDocument();
    // Apenas 3 secundárias (Markdown fica de fora)
    expect(screen.queryByText(/Project documentation/)).not.toBeInTheDocument();

    expect(screen.getByText(/complete web architecture/)).toBeInTheDocument();
    expect(screen.getByText(/Likely separated using/).closest('li')).toHaveTextContent('Likely separated using Python');
    expect(screen.getByText(/Complete web application with separation of concerns/)).toBeInTheDocument();

    expect(screen.getByText(/^: 3 MB$/)).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
    expect(screen.getByText(/Adequate size for a functional application/)).toBeInTheDocument();

    expect(screen.queryByText(/single language/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Add Markdown files/)).not.toBeInTheDocument();
    expect(screen.getByText(/Consider adding automated tests/)).toBeInTheDocument();
  });

  test('backend Java e arquitetura web sem backend', () => {
    const webJava = makeRepo({
      languages: [lang('Java', 40), lang('HTML', 30), lang('CSS', 20), lang('TypeScript', 10)],
    });
    const { unmount } = openAnalysis(webJava);
    expect(screen.getByText(/robust enterprise application/)).toBeInTheDocument();
    expect(screen.getByText(/Likely separated using/).closest('li')).toHaveTextContent('Likely separated using Java');
    expect(screen.getByText(/Styling and visual presentation/)).toBeInTheDocument();
    expect(screen.getByText(/Static typing for more robust JavaScript code/)).toBeInTheDocument();
    unmount();

    openAnalysis(makeRepo({
      languages: [lang('HTML', 50), lang('CSS', 30), lang('JavaScript', 20)],
    }));
    expect(screen.getByText(/web project focused on page structure/)).toBeInTheDocument();
    expect(screen.getByText(/complete web architecture/)).toBeInTheDocument();
    expect(screen.queryByText(/Likely separated using/)).not.toBeInTheDocument();
  });

  test('projeto Python estruturado com alta complexidade e muitas linguagens', () => {
    const others = ['JSON', 'YAML', 'Shell', 'Dockerfile', 'Go', 'Rust', 'C++', 'Ruby', 'Lua', 'Perl']
      .map(name => lang(name, 1));
    openAnalysis(makeRepo({
      repository: 'backend-service',
      total_files: 500,
      languages: [lang('Python', 90, 400), ...others],
    }));

    expect(screen.getByText(/Structured/).closest('p')).toHaveTextContent('Structured Python project, possibly with:');
    expect(screen.getByText(/Backend API \(Flask\/Django\/FastAPI\)/)).toBeInTheDocument();
    expect(screen.getByText(/Configuration and data structures/)).toBeInTheDocument();
    expect(screen.getByText(/Configuration files and pipelines/)).toBeInTheDocument();
    expect(screen.getByText(/Automation and build scripts/)).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
    expect(screen.getByText(/This is a robust project/)).toBeInTheDocument();
    expect(screen.getByText(/45 files per language on average/)).toBeInTheDocument();
    expect(screen.getByText(/With 11 languages, consider standardizing/)).toBeInTheDocument();
    expect(screen.getByText(/90% of the code is in a single language/)).toBeInTheDocument();
    expect(screen.getByText(/Consider adding automated tests/)).toBeInTheDocument();
  });

  test('Python pequeno não é classificado como estruturado', () => {
    openAnalysis(makeRepo({ total_files: 5, languages: [lang('Python', 100)] }));
    expect(screen.queryByText(/Structured/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Modern web application/)).not.toBeInTheDocument();
  });

  test('linguagem desconhecida usa textos genéricos e secundárias com insights', () => {
    openAnalysis(makeRepo({
      total_files: 60,
      languages: [
        lang('Elixir', 60),
        lang('Dockerfile', 20),
        lang('Markdown', 10),
        lang('Python', 10),
      ],
    }));

    expect(screen.getByText(/offers specific characteristics for the project domain/)).toBeInTheDocument();
    expect(screen.getByText(/Container configuration and deployment/)).toBeInTheDocument();
    expect(screen.getByText(/Project documentation/)).toBeInTheDocument();
    expect(screen.getByText(/Auxiliary scripts or backend/)).toBeInTheDocument();
    // Nenhuma arquitetura inferida
    expect(screen.queryByText(/complete web architecture/)).not.toBeInTheDocument();
    expect(screen.queryByText(/project, indicating/)).not.toBeInTheDocument();
    expect(screen.getByText(/Consider adding automated tests/)).toBeInTheDocument();
  });

  test.each([
    ['Go', /concurrency, and microservices/],
    ['Rust', /memory safety and extreme performance/],
    ['C++', /high-performance systems, games/],
    ['Shell', /infrastructure automation/],
    ['CSS', /strong emphasis on styling/],
    ['JavaScript', /dynamic web project/],
  ])('insight da linguagem principal %s', (language, expected) => {
    openAnalysis(makeRepo({ languages: [lang(language, 100)] }));
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  test('não recomenda testes quando linguagem ou repositório indicam testes', () => {
    const { unmount } = openAnalysis(makeRepo({
      repository: 'my-test-suite',
      total_files: 100,
    }));
    expect(screen.queryByText(/Consider adding automated tests/)).not.toBeInTheDocument();
    unmount();

    openAnalysis(makeRepo({
      total_files: 100,
      languages: [lang('TypeScript', 70), lang('TestLang', 30)],
    }));
    expect(screen.queryByText(/Consider adding automated tests/)).not.toBeInTheDocument();
  });
});

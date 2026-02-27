import { useState } from 'react';

interface LanguageData {
  language: string;
  file_count: number;
  total_bytes: number;
  percentage: number;
}

interface RepoAnalysis {
  repository: string;
  owner: string;
  branch: string;
  total_files: number;
  total_bytes: number;
  languages: LanguageData[];
}

interface RepoStructureAnalysisProps {
  data: RepoAnalysis;
}

export const RepoStructureAnalysis: React.FC<RepoStructureAnalysisProps> = ({ data }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const generateAnalysis = () => {
    setLoading(true);

    // Analysis based on languages and structure
    const sortedLanguages = [...data.languages].sort((a, b) => b.percentage - a.percentage);
    const primaryLanguage = sortedLanguages[0];
    const secondaryLanguages = sortedLanguages.slice(1, 4);

    let analysisText = `## 🔍 Repository Structure Analysis\n\n`;

    // 1. Primary Language
    analysisText += `### 🎯 Primary Language\n`;
    analysisText += `**${primaryLanguage.language}** is the predominant language, representing **${primaryLanguage.percentage.toFixed(1)}%** of the code `;
    analysisText += `(${primaryLanguage.file_count} files, ${formatBytes(primaryLanguage.total_bytes)}). `;

    // Interpretation based on language
    const languageInsights: Record<string, string> = {
      'Python': 'This suggests a project focused on backend, data science, automation, or machine learning. Python is known for its versatility and productivity.',
      'JavaScript': 'This indicates a dynamic web project, possibly focused on interactive frontend features or a Node.js backend.',
      'TypeScript': 'This demonstrates a modern project with static typing, generally used in scalable, large-scale web applications.',
      'Java': 'This points to a robust enterprise application, focused on performance and object-oriented architecture.',
      'HTML': 'This suggests a web project focused on page structure and content.',
      'CSS': 'This indicates a strong emphasis on styling and visual design.',
      'Go': 'This suggests a project focused on performance, concurrency, and microservices.',
      'Rust': 'This indicates a project that prioritizes memory safety and extreme performance.',
      'C++': 'This points to high-performance systems, games, or applications that require fine-grained resource control.',
      'Shell': 'This demonstrates infrastructure automation, build scripts, or DevOps.'
    };

    analysisText += languageInsights[primaryLanguage.language] || 'This language offers specific characteristics for the project domain.';
    analysisText += `\n\n`;

    // 2. Secondary Languages
    if (secondaryLanguages.length > 0) {
      analysisText += `### 🔧 Complementary Languages\n`;
      secondaryLanguages.forEach(lang => {
        analysisText += `- **${lang.language}** (${lang.percentage.toFixed(1)}%): `;

        const complementaryInsights: Record<string, string> = {
          'HTML': 'User interface and web content structuring.',
          'CSS': 'Styling and visual presentation of the application.',
          'JavaScript': 'Interactivity and frontend logic.',
          'TypeScript': 'Static typing for more robust JavaScript code.',
          'JSON': 'Configuration and data structures.',
          'YAML': 'Configuration files and pipelines.',
          'Markdown': 'Project documentation.',
          'Shell': 'Automation and build scripts.',
          'Python': 'Auxiliary scripts or backend.',
          'Dockerfile': 'Container configuration and deployment.'
        };

        analysisText += complementaryInsights[lang.language] || 'Additional project support.';
        analysisText += `\n`;
      });
      analysisText += `\n`;
    }

    // 3. Inferred Architecture
    analysisText += `### 🏗️ Inferred Architecture\n`;

    const hasHTML = data.languages.some(l => l.language === 'HTML');
    const hasCSS = data.languages.some(l => l.language === 'CSS' || l.language === 'SCSS');
    const hasJS = data.languages.some(l => ['JavaScript', 'TypeScript'].includes(l.language));
    const hasPython = data.languages.some(l => l.language === 'Python');
    const hasJava = data.languages.some(l => l.language === 'Java');

    if (hasHTML && hasCSS && hasJS) {
      analysisText += `This repository features a **complete web architecture** with:\n`;
      analysisText += `- ✅ **Frontend**: HTML structure, CSS/SCSS styling, and JavaScript/TypeScript logic\n`;
      if (hasPython || hasJava) {
        analysisText += `- ✅ **Backend**: Likely separated using ${hasPython ? 'Python' : 'Java'}\n`;
        analysisText += `- ✅ **Full-Stack**: Complete web application with separation of concerns\n`;
      }
    } else if (primaryLanguage.language === 'Python' && data.total_files > 20) {
      analysisText += `Structured **Python** project, possibly with:\n`;
      analysisText += `- Backend API (Flask/Django/FastAPI)\n`;
      analysisText += `- Data processing or analysis scripts\n`;
      analysisText += `- Automated tests\n`;
    } else if (primaryLanguage.language === 'JavaScript' || primaryLanguage.language === 'TypeScript') {
      analysisText += `**JavaScript/TypeScript** project, indicating:\n`;
      analysisText += `- Modern web application (React/Vue/Angular)\n`;
      analysisText += `- Possibly a Node.js server\n`;
      analysisText += `- Build tools and bundling\n`;
    }
    analysisText += `\n`;

    // 4. Size and Complexity
    analysisText += `### 📊 Complexity Metrics\n`;
    analysisText += `- **Total Files**: ${data.total_files} files\n`;
    analysisText += `- **Total Size**: ${formatBytes(data.total_bytes)}\n`;
    analysisText += `- **Language Diversity**: ${data.languages.length} different languages\n`;

    const avgFilesPerLanguage = data.total_files / data.languages.length;
    const complexityLevel = data.total_files < 50 ? 'low' : data.total_files < 200 ? 'medium' : 'high';

    analysisText += `\n**Assessment**: Project of **${complexityLevel}** complexity `;
    analysisText += `(${avgFilesPerLanguage.toFixed(0)} files per language on average). `;

    if (complexityLevel === 'high') {
      analysisText += `This is a robust project that likely requires good organization and documentation.`;
    } else if (complexityLevel === 'medium') {
      analysisText += `Adequate size for a functional application with a well-defined scope.`;
    } else {
      analysisText += `Compact project, possibly in an early stage or with a focused scope.`;
    }
    analysisText += `\n\n`;

    // 5. Recommendations
    analysisText += `### 💡 Recommendations\n`;

    if (primaryLanguage.percentage > 80) {
      analysisText += `- ⚠️ **Diversification**: ${primaryLanguage.percentage.toFixed(0)}% of the code is in a single language. Consider whether there are opportunities for modularization.\n`;
    }

    if (!data.languages.some(l => l.language === 'Markdown')) {
      analysisText += `- 📝 **Documentation**: Add Markdown files (README.md, CONTRIBUTING.md) to improve documentation.\n`;
    }

    if (data.languages.length > 10) {
      analysisText += `- 🎯 **Standardization**: With ${data.languages.length} languages, consider standardizing the stack to ease maintenance.\n`;
    }

    const hasTests = data.languages.some(l =>
      l.language.toLowerCase().includes('test') ||
      data.repository.toLowerCase().includes('test')
    );

    if (!hasTests && data.total_files > 30) {
      analysisText += `- ✅ **Tests**: Consider adding automated tests to ensure quality.\n`;
    }

    setAnalysis(analysisText);
    setLoading(false);
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const renderMarkdown = (text: string) => {
    return text.split('\n').map((line, index) => {
      // Headings
      if (line.startsWith('### ')) {
        return <h3 key={index} className="text-lg font-bold text-white mt-4 mb-2">{line.replace('### ', '')}</h3>;
      }
      if (line.startsWith('## ')) {
        return <h2 key={index} className="text-xl font-bold text-white mt-6 mb-3">{line.replace('## ', '')}</h2>;
      }

      // Lists
      if (line.startsWith('- ')) {
        const content = line.replace('- ', '');
        return (
          <li key={index} className="text-slate-300 ml-4 mb-1">
            {renderInlineFormatting(content)}
          </li>
        );
      }

      // Empty paragraph
      if (line.trim() === '') {
        return <br key={index} />;
      }

      // Normal paragraph
      return (
        <p key={index} className="text-slate-300 mb-2">
          {renderInlineFormatting(line)}
        </p>
      );
    });
  };

  const renderInlineFormatting = (text: string) => {
    // **bold**
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('**') && part.endsWith('**')) {
        return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <div className="border rounded-lg mb-6" style={{ backgroundColor: '#222222', borderColor: '#333333' }}>
      {/* Header */}
      <button
        onClick={() => {
          if (!analysis && !loading) {
            generateAnalysis();
          }
          setIsExpanded(!isExpanded);
        }}
        className="w-full px-6 py-4 flex items-center justify-between text-white hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl">🤖</span>
          <div className="text-left">
            <h3 className="text-xl font-semibold">Intelligent Structure Analysis</h3>
            <p className="text-sm text-slate-400">
              Automatic interpretation of the repository's organization and languages
            </p>
          </div>
        </div>
        <span className="text-2xl">{isExpanded ? '▼' : '▶'}</span>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="px-6 pb-6 border-t" style={{ borderTopColor: '#333333' }}>
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="flex flex-col items-center gap-3">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-white"></div>
                <p className="text-slate-400">Analyzing repository structure...</p>
              </div>
            </div>
          )}

          {!loading && analysis && (
            <div className="mt-4 prose prose-invert max-w-none">
              {renderMarkdown(analysis)}
            </div>
          )}

          {!loading && !analysis && (
            <div className="py-8 text-center">
              <button
                onClick={generateAnalysis}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold transition-colors"
              >
                🚀 Generate Analysis
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

import DashboardLayout from '../components/DashboardLayout';
import AISummary from '../components/AI.summary';

/**
 * AI Analysis Page
 *
 * Shows the AI-generated analysis of each member's commits, pull requests and
 * issues (`silver/ai/members_ai.json`). The file is only produced when the
 * pipeline has a GEMINI_API_KEY secret; AISummary renders the "not generated
 * yet" state otherwise.
 */
export default function AIAnalysis() {
  return (
    <DashboardLayout currentPage="ai" currentSubPage="" onRepo={false}>
      <div className="space-y-8">
        {/* Header */}
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">AI Member Analysis</h1>
          <p className="text-slate-400">
            AI-generated summaries of each member&apos;s commits, pull requests and issues.
            Select one or more members to compare their analyses.
          </p>
        </div>

        <AISummary title="Select members" />
      </div>
    </DashboardLayout>
  );
}

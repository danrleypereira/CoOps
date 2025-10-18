import { ReactNode } from 'react';
import Sidebar from './Sidebar';
import RepositoryToolbar from './RepositoryToolbar';
import type { ProcessedActivityResponse } from '../pages/Utils';

interface DashboardLayoutProps {
  children: ReactNode;
  currentPage?: string;
  currentSubPage?: string;
  onRepo?: boolean;
  currentRepo?: string;
  data?: ProcessedActivityResponse | null;
  onNavigate?: (page: string) => void;
}

/**
 * DashboardLayout Component
 *
 * Main layout wrapper for dashboard pages.
 * Provides consistent structure with sidebar navigation and optional repository toolbar.
 *
 * @param children - Content to render in the main area
 * @param currentPage - Current main page for navigation highlighting
 * @param currentSubPage - Current sub-page for toolbar highlighting
 * @param onRepo - Whether to show the repository toolbar
 * @param currentRepo - Name of currently selected repository
 * @param data - Activity data for repository selection
 * @param onNavigate - Navigation handler callback
 */
export default function DashboardLayout({
  children,
  currentPage,
  currentSubPage,
  onRepo = true,
  currentRepo = 'No Repository Selected',
  data = null,
  onNavigate,
}: DashboardLayoutProps) {
  return (
    <div className="min-h-screen">
      <Sidebar currentPage={currentPage} onNavigate={onNavigate} />
      {/* Add left margin to account for fixed sidebar */}
      <div className="ml-46 flex flex-col min-h-screen">
        {onRepo && (
          <RepositoryToolbar
            currentRepo={currentRepo}
            currentPage={currentSubPage}
            data={data}
            onNavigate={onNavigate}
          />
        )}
        {/* Main Content */}
        <main className="flex-1 overflow-y-auto" style={{ backgroundColor: '#181818' }}>
          <div className="max-w-7xl mx-auto p-8">{children}</div>
        </main>
      </div>
    </div>
  );
}

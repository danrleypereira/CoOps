import { Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import Organization from './pages/Organization';
import Commits from './pages/Commits';
import Issues from './pages/Issues';
import PullRequests from './pages/PullRequests';
import Collaboration from './pages/Collaboration';
import Structure from './pages/Structure';
import NotFound from './pages/NotFound';

/**
 * App Component
 *
 * Root application component defining all routes.
 * Manages navigation between home, organization, and repository analysis pages.
 * Includes fallback route for unimplemented features.
 */
function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/organization" element={<Organization />} />
      <Route path="/repos" element={<Navigate to="/repos/commits" replace />} />
      <Route path="/repos/commits" element={<Commits />} />
      <Route path="/repos/issues" element={<Issues />} />
      <Route path="/repos/pullrequests" element={<PullRequests />} />
      <Route path="/repos/collaboration" element={<Collaboration />} />
      <Route path="/repos/structure" element={<Structure />} />

      {/* Fallback route for not implemented pages */}
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

export default App;

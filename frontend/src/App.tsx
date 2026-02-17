import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Layout } from './components/layout/Layout';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import CrawlPage from './pages/CrawlPage';
import Setup from './pages/Setup';
import Progress from './pages/Progress';
import Results from './pages/Results';
import Review from './pages/Review';
import Library from './pages/Library';
import Upload from './pages/Upload';
import AuditLog from './pages/AuditLog';
import Funnel from './pages/Funnel';

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Protected routes wrapped in Layout */}
          <Route path="/dashboard" element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>} />
          <Route path="/crawl" element={<ProtectedRoute><Layout><CrawlPage /></Layout></ProtectedRoute>} />
          <Route path="/setup" element={<ProtectedRoute><Layout><Setup /></Layout></ProtectedRoute>} />
          <Route path="/progress" element={<ProtectedRoute><Layout><Progress /></Layout></ProtectedRoute>} />
          <Route path="/results" element={<ProtectedRoute><Layout><Results /></Layout></ProtectedRoute>} />
          <Route path="/review" element={<ProtectedRoute><Layout><Review /></Layout></ProtectedRoute>} />
          <Route path="/library" element={<ProtectedRoute><Layout><Library /></Layout></ProtectedRoute>} />
          <Route path="/upload" element={<ProtectedRoute><Layout><Upload /></Layout></ProtectedRoute>} />
          <Route path="/audit" element={<ProtectedRoute><Layout><AuditLog /></Layout></ProtectedRoute>} />
          <Route path="/funnel" element={<ProtectedRoute><Layout><Funnel /></Layout></ProtectedRoute>} />

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;

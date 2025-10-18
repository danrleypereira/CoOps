import { Link } from 'react-router-dom';
import logo from '../assets/logo-no-background.png';
import banner from '../assets/alternative-banner.png';
import mascot from '../assets/mascot-coops.png';

/**
 * HomePage Component
 *
 * Landing page that provides an overview of the CoOps project.
 * Features:
 * - Logo and brand assets
 * - Main hero section with project description
 * - Call-to-action buttons for viewing metrics
 * - Animated SVG visualization showcasing data analysis capabilities
 * - Mascot for engaging user experience
 */
export default function HomePage() {
  return (
    <div
      className="min-h-screen text-white relative overflow-hidden"
      style={{
        backgroundColor: '#181818',
        backgroundImage: `linear-gradient(rgba(24, 24, 24, 0.85), rgba(24, 24, 24, 0.95)), url(${banner})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundAttachment: 'fixed',
      }}
    >
      {/* Logo Header */}
      <div className="absolute top-8 left-8 z-10 animate-fade-in">
        <img
          src={logo}
          alt="CoOps Logo"
          className="h-16 w-auto opacity-90 hover:opacity-100 transition-opacity"
        />
      </div>

      <div className="relative mx-auto w-full max-w-6xl px-6 py-24 opacity-100">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          {/* Left Column: Text and Buttons */}
          <div>
            <h1 className="text-6xl font-bold text-gray-100 leading-tight animate-fade-in">
              Real-Time Insights for
              <br />
              <span style={{ color: 'var(--color-blue-trust)' }}>
                High-Performing
              </span>{' '}
              Teams
            </h1>
            <h2 className="mt-6 text-xl font-normal text-gray-300 leading-relaxed animate-fade-in-delayed">
              CoOps transforms your GitHub activity into actionable intelligence.
              Track team dynamics, monitor collaboration patterns, and make
              data-driven decisions that accelerate your development velocity.
            </h2>

            {/* Feature List */}
            <div className="mt-8 space-y-3 animate-fade-in-delayed">
              <h3 className="text-lg font-semibold text-gray-200 mb-4">
                📊 What You'll Discover:
              </h3>
              <div className="space-y-2 text-gray-300">
                <div className="flex items-start gap-3">
                  <span
                    className="text-2xl mt-0.5"
                    style={{ color: 'var(--color-blue-trust)' }}
                  >
                    ●
                  </span>
                  <p>Real-time collaboration metrics across all repositories</p>
                </div>
                <div className="flex items-start gap-3">
                  <span
                    className="text-2xl mt-0.5"
                    style={{ color: 'var(--color-green-growth)' }}
                  >
                    ●
                  </span>
                  <p>Team contribution patterns and growth trends</p>
                </div>
                <div className="flex items-start gap-3">
                  <span
                    className="text-2xl mt-0.5"
                    style={{ color: 'var(--color-amber-accent)' }}
                  >
                    ●
                  </span>
                  <p>Performance insights that drive continuous improvement</p>
                </div>
              </div>
            </div>

            <div className="mt-10 space-y-4 animate-fade-in-delayed-2">
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="hover:scale-105 transition-transform duration-200">
                  <Link to="/repos/commits" className="botao-principal">
                    View Dashboard
                  </Link>
                </div>
              </div>

              <p className="text-white/60 text-sm">
                Explore metrics by repository or view organization-wide analytics
              </p>
            </div>
          </div>

          {/* Right Column: SVG Chart */}
          <div className="flex items-start justify-center relative grafico-container mt-0">
            <svg
              width="540"
              height="320"
              viewBox="0 0 540 320"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="grafico-principal animate-fade-in-delayed-2 rounded-md relative z-10 hover:scale-105 transition-transform duration-300 opacity-100"
            >
              <defs>
                <linearGradient id="gradient1" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#7db7ffb6" stopOpacity={100} />
                  <stop offset="100%" stopColor="#7db7ffff" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradient3" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#7db7ffb6" stopOpacity={10} />
                  <stop offset="100%" stopColor="#7db7ffb6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradient4" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#7db7ffb6" stopOpacity={10} />
                  <stop offset="95%" stopColor="#7db7ffb6" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="gradient5" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#7db8ffff" />
                  <stop offset="100%" stopColor="#1a1a1aff" />
                </linearGradient>
              </defs>
              <defs>
                <linearGradient id="gradient2" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="70%" stopColor="#222222" />
                  <stop offset="100%" stopColor="#181818" />
                </linearGradient>
              </defs>

              {/* Background */}
              <rect x="0" y="0" width="540" height="320" rx="10" fill="url(#gradient2)" />

              {/* Bars with gradients */}
              <g transform="translate(75,30)">
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '0ms' }}
                  x="0"
                  y="170"
                  width="70"
                  height="115"
                  rx="6"
                  fill="url(#barGradientUniform)"
                  opacity="0.69"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '120ms' }}
                  x="100"
                  y="80"
                  width="70"
                  height="150"
                  rx="6"
                  fill="url(#barGradientUniform)"
                  opacity="0.75"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '240ms' }}
                  x="200"
                  y="0"
                  width="70"
                  height="290"
                  rx="6"
                  fill="url(#barGradientUniform)"
                  opacity="0.95"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '360ms' }}
                  x="300"
                  y="150"
                  width="70"
                  height="80"
                  rx="6"
                  fill="url(#barGradientUniform)"
                  opacity="0.7"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  x="400"
                  y="230"
                  width="70"
                  height="60"
                  rx="6"
                  fill="url(#barGradientUniform)"
                  opacity="0.6"
                />
              </g>

              {/* Height markers and aligned mask */}
              <g transform="translate(40,30)">
                <mask id="barMask">
                  <rect
                    className="animate-fade-in-delayed-3"
                    style={{ animationDelay: '600ms' }}
                    x="0"
                    y="0"
                    width="470"
                    height="320"
                    fill="white"
                  />
                  <g>
                    <rect x="0" y="170" width="70" height="120" rx="6" fill="black" />
                    <rect x="100" y="80" width="70" height="220" rx="6" fill="black" />
                    <rect x="200" y="0" width="70" height="290" rx="6" fill="black" />
                    <rect x="300" y="150" width="70" height="140" rx="6" fill="black" />
                    <rect x="400" y="230" width="70" height="60" rx="6" fill="black" />
                  </g>
                </mask>
                {/* Horizontal lines with gradient opacity and mask */}
                <g mask="url(#barMask)">
                  <line
                    x1="0"
                    y1="50"
                    x2="540"
                    y2="50"
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="6.8"
                    opacity="0.25"
                  />
                  <line
                    x1="0"
                    y1="100"
                    x2="540"
                    y2="100"
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="6.8"
                    opacity="0.22"
                  />
                  <line
                    x1="0"
                    y1="150"
                    x2="540"
                    y2="150"
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="6.8"
                    opacity="0.18"
                  />
                  <line
                    x1="0"
                    y1="200"
                    x2="540"
                    y2="200"
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="6.8"
                    opacity="0.13"
                  />
                  <line
                    x1="0"
                    y1="250"
                    x2="540"
                    y2="250"
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="6.8"
                    opacity="0.08"
                  />
                  <line
                    x1="0"
                    y1="300"
                    x2="540"
                    y2="300"
                    stroke="#64748b"
                    strokeWidth="1"
                    strokeDasharray="6.8"
                    opacity="0.04"
                  />
                </g>
                {/* Bars with gradients */}
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '0ms' }}
                  x="0"
                  y="170"
                  width="70"
                  height="120"
                  rx="6"
                  fill="url(#gradient1)"
                  opacity="0.7"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '120ms' }}
                  x="100"
                  y="80"
                  width="70"
                  height="220"
                  rx="6"
                  fill="url(#gradient4)"
                  opacity="0.85"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '240ms' }}
                  x="200"
                  y="0"
                  width="70"
                  height="290"
                  rx="6"
                  fill="url(#gradient1)"
                  opacity="0.95"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '360ms' }}
                  x="300"
                  y="150"
                  width="70"
                  height="140"
                  rx="6"
                  fill="url(#gradient1)"
                  opacity="0.8"
                />
                <rect
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  x="400"
                  y="230"
                  width="70"
                  height="60"
                  rx="6"
                  fill="url(#gradient3)"
                  opacity="0.65"
                />
              </g>
              {/* Overlaid line chart */}
              <g transform="translate(40,30)">
                <polyline
                  points="35,205 135,115 235,35 335,185 435,265"
                  fill="none"
                  stroke="#ffffffff"
                  strokeWidth="3"
                  strokeLinejoin="round"
                  opacity="0.85"
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                />
                {/* Line points */}
                <circle
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  cx="35"
                  cy="205"
                  r="5"
                  fill="#ffffffff "
                />
                <circle
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  cx="135"
                  cy="115"
                  r="5"
                  fill="#ffffffff"
                />
                <circle
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  cx="235"
                  cy="35"
                  r="5"
                  fill="#ffffffff"
                />
                <circle
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  cx="335"
                  cy="185"
                  r="5"
                  fill="#ffffffff"
                />
                <circle
                  className="animate-fade-in-delayed-3"
                  style={{ animationDelay: '480ms' }}
                  cx="435"
                  cy="265"
                  r="5"
                  fill="#ffffffff"
                />
              </g>
            </svg>
          </div>
        </div>

        {/* Mascot Section */}
        <div className="mt-16 flex justify-center animate-fade-in-delayed-3">
          <img
            src={mascot}
            alt="CoOps Mascot"
            className="h-48 w-auto opacity-80 hover:opacity-100 hover:scale-110 transition-all duration-300"
          />
        </div>
      </div>
    </div>
  );
}

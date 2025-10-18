/**
 * Loading Component
 *
 * Reusable loading spinner for data fetching and processing states.
 * Can be used inline or as a full-screen overlay.
 */

interface LoadingProps {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
  overlay?: boolean;
}

export default function Loading({
  message = 'Loading...',
  size = 'md',
  overlay = false
}: LoadingProps) {
  const sizeClasses = {
    sm: 'w-6 h-6 border-2',
    md: 'w-12 h-12 border-3',
    lg: 'w-16 h-16 border-4',
  };

  const spinner = (
    <div className="flex flex-col items-center justify-center gap-4">
      <div
        className={`${sizeClasses[size]} border-slate-600 border-t-blue-500 rounded-full animate-spin`}
        style={{ borderTopColor: 'var(--color-blue-trust)' }}
      />
      {message && (
        <p className="text-slate-400 text-sm animate-pulse">{message}</p>
      )}
    </div>
  );

  if (overlay) {
    return (
      <div
        className="absolute inset-0 flex items-center justify-center z-50"
        style={{ backgroundColor: 'rgba(24, 24, 24, 0.8)' }}
      >
        {spinner}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-[200px]">
      {spinner}
    </div>
  );
}

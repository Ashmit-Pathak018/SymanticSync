import React from 'react';
import { AlertTriangle, CheckCircle, Info, XCircle } from 'lucide-react';

export function Alert({ variant = 'info', title, children, className = '' }) {
  const styles = {
    info: {
      bg: 'bg-primary-light/70 border-primary/30 text-primary',
      icon: Info,
    },
    success: {
      bg: 'bg-success-light border-success/30 text-success',
      icon: CheckCircle,
    },
    warning: {
      bg: 'bg-warning-light border-warning/30 text-warning',
      icon: AlertTriangle,
    },
    danger: {
      bg: 'bg-danger-light border-danger/30 text-danger',
      icon: XCircle,
    },
  }[variant] || {
    bg: 'bg-gray-100 border-gray-200 text-gray-800',
    icon: Info,
  };

  const Icon = styles.icon;

  return (
    <div className={`p-4 rounded-lg border flex items-start gap-3 text-sm ${styles.bg} ${className}`}>
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div className="flex-1">
        {title && <h4 className="font-semibold mb-1 leading-snug">{title}</h4>}
        <div className="text-text-primary text-xs leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

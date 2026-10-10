import React from 'react';

export function Card({ children, className = '', title, subtitle, headerAction, footer }) {
  return (
    <div className={`bg-white rounded-lg border border-border shadow-xs overflow-hidden ${className}`}>
      {(title || subtitle || headerAction) && (
        <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-4">
          <div>
            {title && <h3 className="font-semibold text-text-primary text-base leading-tight">{title}</h3>}
            {subtitle && <p className="text-xs text-text-secondary mt-1">{subtitle}</p>}
          </div>
          {headerAction && <div className="flex items-center gap-2">{headerAction}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
      {footer && <div className="px-5 py-3 bg-gray-50/70 border-t border-border">{footer}</div>}
    </div>
  );
}

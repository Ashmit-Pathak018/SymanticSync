import React from 'react';
import { Loader2 } from 'lucide-react';

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  loading = false,
  icon: Icon,
  onClick,
  type = 'button',
  title,
}) {
  const sizeClasses = {
    sm: 'px-2.5 py-1.5 text-xs rounded-md',
    md: 'px-4 py-2 text-sm rounded-md',
    lg: 'px-5 py-2.5 text-base rounded-lg',
  }[size] || 'px-4 py-2 text-sm rounded-md';

  const variantClasses = {
    primary: 'bg-primary text-white hover:bg-primary-hover shadow-sm font-medium',
    secondary: 'bg-white border border-border text-text-primary hover:bg-gray-50 shadow-sm font-medium',
    success: 'bg-success text-white hover:opacity-95 shadow-sm font-medium',
    danger: 'bg-danger text-white hover:opacity-95 shadow-sm font-medium',
    outline: 'border border-primary text-primary hover:bg-primary-light font-medium',
    ghost: 'text-text-secondary hover:text-text-primary hover:bg-gray-100 font-medium',
  }[variant] || 'bg-primary text-white hover:bg-primary-hover font-medium';

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      className={`inline-flex items-center justify-center gap-2 transition-all select-none disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer ${sizeClasses} ${variantClasses} ${className}`}
    >
      {loading ? (
        <Loader2 className="w-4 h-4 animate-spin" />
      ) : Icon ? (
        <Icon className="w-4 h-4 flex-shrink-0" />
      ) : null}
      <span>{children}</span>
    </button>
  );
}

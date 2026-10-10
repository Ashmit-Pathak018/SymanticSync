import React from 'react';
import { CheckCircle2, Clock, AlertTriangle, XCircle, Tag } from 'lucide-react';

export function Badge({ variant = 'default', children, className = '', size = 'md' }) {
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  let variantStyles = 'bg-gray-100 text-gray-700 border-gray-200';
  let Icon = null;

  switch (variant) {
    case 'success':
    case 'resolved':
      variantStyles = 'bg-[#EAF7F0] text-[#2D9B62] border-[#2D9B62]/30';
      Icon = CheckCircle2;
      break;
    case 'warning':
    case 'pending':
      variantStyles = 'bg-[#FEF8EC] text-[#C98A1B] border-[#C98A1B]/30';
      Icon = Clock;
      break;
    case 'danger':
    case 'flagged':
      variantStyles = 'bg-[#FDF2F3] text-[#D94B5B] border-[#D94B5B]/30';
      Icon = AlertTriangle;
      break;
    case 'invalid':
      variantStyles = 'bg-[#FDF2F3] text-[#D94B5B] border-[#D94B5B]/30';
      Icon = XCircle;
      break;
    case 'primary':
    case 'policy':
      variantStyles = 'bg-[#EBF0FF] text-[#315CFF] border-[#315CFF]/30 font-mono font-semibold';
      Icon = Tag;
      break;
    case 'neutral':
      variantStyles = 'bg-gray-100 text-gray-700 border-gray-200 font-mono';
      break;
    default:
      variantStyles = 'bg-gray-100 text-gray-700 border-gray-200';
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${sizeClasses} ${variantStyles} ${className}`}
    >
      {Icon && <Icon className="w-3.5 h-3.5 flex-shrink-0" />}
      <span>{children}</span>
    </span>
  );
}

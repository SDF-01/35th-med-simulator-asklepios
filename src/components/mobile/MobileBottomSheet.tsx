import type { ReactNode } from 'react';

interface MobileBottomSheetProps {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
  peek?: boolean;
}

export function MobileBottomSheet({
  title,
  open,
  onToggle,
  children,
  peek = false,
}: MobileBottomSheetProps) {
  return (
    <div className={`mobile-sheet ${open ? 'mobile-sheet--open' : ''} ${peek ? 'mobile-sheet--peek' : ''}`}>
      <button
        type="button"
        className="mobile-sheet__handle"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className="mobile-sheet__grab" aria-hidden />
        <span className="mobile-sheet__title">{title}</span>
        <span className="mobile-sheet__action">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && <div className="mobile-sheet__body">{children}</div>}
    </div>
  );
}

export type RoleIconId = 'provider' | 'wit' | 'command';

interface RoleIconProps {
  role: RoleIconId;
  className?: string;
}

export function RoleIcon({ role, className = '' }: RoleIconProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={`h-7 w-7 ${className}`}
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {role === 'provider' && (
        <>
          <rect x="8" y="10" width="16" height="14" rx="3" />
          <path d="M16 13v8M12 17h8" strokeWidth="2" />
        </>
      )}
      {role === 'wit' && (
        <>
          <rect x="6" y="8" width="20" height="16" rx="3" />
          <path d="M10 13h12M10 17h8M10 21h10" />
        </>
      )}
      {role === 'command' && (
        <>
          <circle cx="16" cy="12" r="4" />
          <path d="M8 26c0-4 3.5-7 8-7s8 3 8 7" />
          <path d="M22 10l2-2M10 10L8 8" opacity="0.6" />
        </>
      )}
    </svg>
  );
}

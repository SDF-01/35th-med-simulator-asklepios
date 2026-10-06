import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { RoleIcon, type RoleIconId } from '@/components/ui/RoleIcon';

type RoleCardVariant = 'default' | 'featured';

interface RoleCardProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  role: RoleIconId;
  title: string;
  subtitle: string;
  description: string;
  variant?: RoleCardVariant;
  children?: ReactNode;
}

export function RoleCard({
  role,
  title,
  subtitle,
  description,
  variant = 'default',
  className = '',
  ...props
}: RoleCardProps) {
  return (
    <button
      type="button"
      className={[
        'role-card group w-full text-left',
        variant === 'featured' ? 'role-card--featured' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      <div className="role-card__icon-wrap">
        <RoleIcon role={role} />
      </div>
      <h2 className="role-card__title">{title}</h2>
      <p className="role-card__subtitle">{subtitle}</p>
      <p className="role-card__description">{description}</p>
      <span className="role-card__action">Open role</span>
    </button>
  );
}

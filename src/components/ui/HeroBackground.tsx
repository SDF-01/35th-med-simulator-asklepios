interface HeroBackgroundProps {
  intensity?: 'full' | 'subtle';
}

export function HeroBackground({ intensity = 'full' }: HeroBackgroundProps) {
  const subtle = intensity === 'subtle';

  return (
    <div className="hero-bg" aria-hidden="true">
      <div className="hero-bg__base" />
      <div className={`hero-bg__glow hero-bg__glow--primary ${subtle ? 'hero-bg__glow--subtle' : ''}`} />
      <div className={`hero-bg__glow hero-bg__glow--secondary ${subtle ? 'hero-bg__glow--subtle' : ''}`} />
      {!subtle && <div className="hero-bg__grain" />}
    </div>
  );
}

/** Kept for API compatibility; app pages no longer use a grid overlay. */
export function TacticalGridOverlay() {
  return null;
}

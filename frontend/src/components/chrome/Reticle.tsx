/** Fadenkreuz-Auge — das Markenzeichen von Auerbachs Auge. */
export default function Reticle({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="10.5" stroke="currentColor" strokeWidth="1.2" opacity="0.85" />
      <circle cx="16" cy="16" r="4.2" fill="currentColor" className="animate-led" />
      <circle cx="16" cy="16" r="1.6" fill="currentColor" />
      <line x1="16" y1="1" x2="16" y2="6.5" stroke="currentColor" strokeWidth="1.2" />
      <line x1="16" y1="25.5" x2="16" y2="31" stroke="currentColor" strokeWidth="1.2" />
      <line x1="1" y1="16" x2="6.5" y2="16" stroke="currentColor" strokeWidth="1.2" />
      <line x1="25.5" y1="16" x2="31" y2="16" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

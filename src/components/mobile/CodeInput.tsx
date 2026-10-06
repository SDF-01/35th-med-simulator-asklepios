import { useEffect, useRef, useState } from 'react';
import { normalizeLobbyCode } from '@/utils/lobbyCode';

const CODE_LENGTH = 6;

interface CodeInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  autoFocus?: boolean;
}

export function CodeInput({ value, onChange, disabled = false, autoFocus = false }: CodeInputProps) {
  const hiddenRef = useRef<HTMLInputElement | null>(null);
  const normalized = normalizeLobbyCode(value).slice(0, CODE_LENGTH);
  const cells = Array.from({ length: CODE_LENGTH }, (_, i) => normalized[i] ?? '');
  const [focusIndex, setFocusIndex] = useState(0);

  useEffect(() => {
    if (autoFocus) hiddenRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    setFocusIndex(Math.min(normalized.length, CODE_LENGTH - 1));
  }, [normalized.length]);

  function handleChange(raw: string) {
    onChange(normalizeLobbyCode(raw).slice(0, CODE_LENGTH));
  }

  return (
    <div className="code-input">
      <input
        ref={hiddenRef}
        className="code-input__hidden"
        value={normalized}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => setFocusIndex(Math.min(normalized.length, CODE_LENGTH - 1))}
        disabled={disabled}
        autoComplete="one-time-code"
        inputMode="text"
        autoCapitalize="characters"
        autoCorrect="off"
        spellCheck={false}
        maxLength={CODE_LENGTH}
        aria-label="Exercise code"
      />
      <div className="code-input__cells" aria-hidden>
        {cells.map((char, index) => (
          <button
            key={index}
            type="button"
            className={[
              'code-input__cell',
              char ? 'code-input__cell--filled' : '',
              focusIndex === index ? 'code-input__cell--focus' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            disabled={disabled}
            onClick={() => {
              hiddenRef.current?.focus();
              setFocusIndex(index);
            }}
          >
            {char}
          </button>
        ))}
      </div>
    </div>
  );
}

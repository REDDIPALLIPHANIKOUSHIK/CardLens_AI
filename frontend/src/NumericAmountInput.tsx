import { useEffect, useState } from 'react';

type NumericAmountInputProps = {
  value: number;
  max?: number;
  onCommit: (value: number) => void;
};

/** Keeps keystrokes as text while editing, then commits a bounded whole amount on blur. */
export default function NumericAmountInput({ value, max = 10_000_000, onCommit }: NumericAmountInputProps) {
  const [draft, setDraft] = useState(String(value ?? 0));

  useEffect(() => setDraft(String(value ?? 0)), [value]);

  function commit() {
    const parsed = draft === '' ? 0 : Number(draft);
    const amount = Number.isFinite(parsed) ? Math.min(max, Math.max(0, Math.trunc(parsed))) : 0;
    setDraft(String(amount));
    onCommit(amount);
  }

  return <input
    type="text"
    className="numeric-amount-input"
    inputMode="numeric"
    pattern="[0-9]*"
    maxLength={String(max).length}
    value={draft}
    onFocus={() => { if (draft === '0') setDraft(''); }}
    onChange={event => {
      const raw = event.target.value.replace(/[\s,₹]/g, '');
      if (/^\d*$/.test(raw) && raw.length <= String(max).length) setDraft(raw);
    }}
    onBlur={commit}
    aria-valuemin={0}
    aria-valuemax={max}
  />;
}


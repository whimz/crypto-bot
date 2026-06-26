import { useRef, useState } from "react";

const VIEWPORT_MARGIN = 12;

export default function Tooltip({ what, optimal, risk }) {
  const [visible, setVisible] = useState(false);
  const [align, setAlign] = useState("left");
  const wrapperRef = useRef(null);

  const show = () => {
    setVisible(true);
    const rect = wrapperRef.current?.getBoundingClientRect();
    if (!rect) return;
    // Tooltip body is ~280px wide; flip to right-aligned if it would overflow the viewport.
    const wouldOverflowRight = rect.left + 280 > window.innerWidth - VIEWPORT_MARGIN;
    setAlign(wouldOverflowRight ? "right" : "left");
  };

  return (
    <span
      className="tooltip-wrapper"
      ref={wrapperRef}
      onMouseEnter={show}
      onMouseLeave={() => setVisible(false)}
      onFocus={show}
      onBlur={() => setVisible(false)}
    >
      <button type="button" className="tooltip-trigger" aria-label="More info" tabIndex={0}>
        ?
      </button>
      {visible && (
        <div className={`tooltip-body tooltip-${align}`} role="tooltip">
          <div className="tooltip-what">{what}</div>
          {optimal && <div className="tooltip-optimal">Оптимально: {optimal}</div>}
          {risk && <div className="tooltip-risk">Риск: {risk}</div>}
        </div>
      )}
    </span>
  );
}

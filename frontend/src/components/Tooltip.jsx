import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { closeTooltip, openTooltip, subscribeTooltip } from "../tooltipBus.js";

const VIEWPORT_MARGIN = 12;
const TOOLTIP_GAP = 8; // matches the body's old "calc(100% + 8px)" offset

export default function Tooltip({ what, optimal, risk }) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState(null);
  const triggerRef = useRef(null);

  // Rendered in a portal (see below) so the slide-over panel's overflow:auto can never
  // clip it - close this instance whenever another tooltip becomes the active one.
  useEffect(
    () =>
      subscribeTooltip((newActiveId) => {
        if (newActiveId !== id) setVisible(false);
      }),
    [id]
  );

  const show = () => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({ top: rect.bottom + TOOLTIP_GAP, left: rect.left });
    setVisible(true);
    openTooltip(id);
  };

  const hide = () => {
    setVisible(false);
    closeTooltip(id);
  };

  const toggle = () => {
    if (visible) hide();
    else show();
  };

  return (
    <span className="tooltip-wrapper" onMouseEnter={show} onMouseLeave={hide}>
      <button
        ref={triggerRef}
        type="button"
        className="tooltip-trigger"
        aria-label="More info"
        onClick={toggle}
      >
        ?
      </button>
      {visible &&
        position &&
        createPortal(
          <TooltipBody what={what} optimal={optimal} risk={risk} position={position} />,
          document.body
        )}
    </span>
  );
}

function TooltipBody({ what, optimal, risk, position }) {
  const bodyRef = useRef(null);
  const [left, setLeft] = useState(position.left);

  useEffect(() => {
    const width = bodyRef.current?.getBoundingClientRect().width ?? 0;
    const maxLeft = window.innerWidth - width - VIEWPORT_MARGIN;
    setLeft(Math.max(VIEWPORT_MARGIN, Math.min(position.left, maxLeft)));
  }, [position.left]);

  return (
    <div
      ref={bodyRef}
      className="tooltip-body"
      role="tooltip"
      style={{ position: "fixed", top: position.top, left }}
    >
      <div className="tooltip-what">{what}</div>
      {optimal && <div className="tooltip-optimal">Оптимально: {optimal}</div>}
      {risk && <div className="tooltip-risk">Риск: {risk}</div>}
    </div>
  );
}

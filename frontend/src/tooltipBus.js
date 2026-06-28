// Coordinates "only one tooltip open at a time" across all Tooltip instances.
let activeId = null;
let listeners = [];

export function subscribeTooltip(listener) {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}

export function openTooltip(id) {
  activeId = id;
  listeners.forEach((listener) => listener(activeId));
}

export function closeTooltip(id) {
  if (activeId !== id) return;
  activeId = null;
  listeners.forEach((listener) => listener(activeId));
}

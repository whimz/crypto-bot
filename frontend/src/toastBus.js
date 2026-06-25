let nextId = 1;
let listeners = [];

export function subscribeToasts(listener) {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}

export function showToast({ title, description, requestId, retry }) {
  const toast = { id: nextId++, title, description, requestId, retry };
  listeners.forEach((listener) => listener(toast));
  return toast.id;
}

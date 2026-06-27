import { useEffect, useRef, useState } from "react";

const VIEWPORT_THRESHOLD = 0.1;

// Fades each card in once it first enters the viewport (including on initial mount if
// already visible), and never re-triggers when scrolling back into view.
export default function FadeInSection({ children }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: VIEWPORT_THRESHOLD }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`transition-opacity duration-700 ease-out ${visible ? "opacity-100" : "opacity-0"}`}
    >
      {children}
    </div>
  );
}

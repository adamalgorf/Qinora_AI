/**
 * The QiNora mark: a routed path between two nodes, traced from the
 * design system PDF's own vector data (page 3, "Primary lockup").
 */
export function Logo({ size = 18 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M5.76 16.8C5.76 9.12 18.24 14.88 18.24 7.2"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="1.8"
      />
      <circle cx="5.76" cy="16.8" fill="currentColor" r="2.04" />
      <circle cx="18.24" cy="7.2" fill="currentColor" r="2.04" />
    </svg>
  );
}

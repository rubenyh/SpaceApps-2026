import type { ReactNode } from "react";

interface Props {
  toggle: ReactNode;
  astronautId: string;
  displayName: string;
  onCheckin: () => void;
  onShare: () => void;
  onLock: () => void;
}

// Placeholder: built in the personal view step.
export function PersonalView({ toggle, displayName }: Props) {
  return <div className="screen"><div className="wellbeing__bar">{toggle}<span>{displayName}</span></div></div>;
}

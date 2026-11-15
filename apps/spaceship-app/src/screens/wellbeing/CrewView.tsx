import type { ReactNode } from "react";

// Placeholder: built in the crew view step.
export function CrewView({ toggle }: { toggle: ReactNode }) {
  return <div className="screen"><div className="wellbeing__bar">{toggle}</div></div>;
}

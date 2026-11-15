interface Props {
  astronautId: string;
  displayName: string;
  onBack: () => void;
}

// Placeholder: built in its own step.
export function CheckinView({ onBack }: Props) {
  return <div className="screen"><button type="button" className="btn btn--ghost" onClick={onBack}>Back to Personal</button></div>;
}

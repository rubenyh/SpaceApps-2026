import { useState } from "react";
import type { Astronaut } from "../api/types";
import { PersonalLock } from "../components/PersonalLock";
import { SegmentedControl } from "../components/SegmentedControl";
import { CheckinView } from "./wellbeing/CheckinView";
import { CrewView } from "./wellbeing/CrewView";
import { GroundView } from "./wellbeing/GroundView";
import { PersonalView } from "./wellbeing/PersonalView";

type View = "crew" | "personal";
type PersonalPage = "summary" | "checkin" | "ground";

interface Props {
  /** The astronaut chosen in the Header: Personal always shows this person. */
  astronautId: string;
  astronauts: Astronaut[];
}

const VIEWS: { key: View; label: string }[] = [
  { key: "crew", label: "Crew" },
  { key: "personal", label: "Personal" },
];

/**
 * Wellbeing tab. The screen is remounted when the astronaut or tab changes (App keys it),
 * so the personal unlock (memory only) never carries over to another person.
 */
export function WellbeingScreen({ astronautId, astronauts }: Props) {
  const [view, setView] = useState<View>("crew");
  const [page, setPage] = useState<PersonalPage>("summary");
  const [unlocked, setUnlocked] = useState(false);
  const displayName = astronauts.find((a) => a.id === astronautId)?.display_name ?? astronautId;

  // Leaving Personal re-locks it, so nobody walks up to an unlocked detail later.
  const changeView = (next: View) => {
    if (next === "crew") setUnlocked(false);
    setPage("summary");
    setView(next);
  };
  const toggle = <SegmentedControl label="Wellbeing view" options={VIEWS} value={view} onChange={changeView} />;

  if (view === "crew") return <CrewView toggle={toggle} />;

  if (!unlocked) {
    return (
      <div className="screen">
        <div className="wellbeing__bar">{toggle}</div>
        <PersonalLock astronautId={astronautId} displayName={displayName} onUnlock={() => setUnlocked(true)} />
      </div>
    );
  }

  const back = () => setPage("summary");
  if (page === "checkin") {
    return <CheckinView astronautId={astronautId} displayName={displayName} onBack={back} />;
  }
  if (page === "ground") {
    return <GroundView astronautId={astronautId} displayName={displayName} onBack={back} />;
  }
  return (
    <PersonalView
      toggle={toggle}
      astronautId={astronautId}
      displayName={displayName}
      onCheckin={() => setPage("checkin")}
      onShare={() => setPage("ground")}
      onLock={() => changeView("crew")}
    />
  );
}

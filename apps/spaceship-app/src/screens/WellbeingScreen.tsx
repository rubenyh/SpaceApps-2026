import { useState } from "react";
import type { Astronaut } from "../api/types";
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
 * so the personal unlock never carries over to another person.
 */
export function WellbeingScreen({ astronautId, astronauts }: Props) {
  const [view, setView] = useState<View>("crew");
  const [page, setPage] = useState<PersonalPage>("summary");
  const displayName = astronauts.find((a) => a.id === astronautId)?.display_name ?? astronautId;

  const toggle = <SegmentedControl label="Wellbeing view" options={VIEWS} value={view} onChange={setView} />;

  if (view === "crew") return <CrewView toggle={toggle} />;

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
      onLock={() => setView("crew")}
    />
  );
}

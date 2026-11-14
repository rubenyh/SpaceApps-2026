import { formatAge } from "../lib/format";

interface Props {
  seconds: number | null | undefined;
  /** Emphasise the age (used for stale data). */
  emphasis?: boolean;
  prefix?: string;
}

export function AgeLabel({ seconds, emphasis = false, prefix }: Props) {
  const text = formatAge(seconds);
  if (!text) return null;
  return (
    <span className={emphasis ? "age age--emph" : "age"}>
      {prefix ? `${prefix} ` : ""}
      {text}
    </span>
  );
}

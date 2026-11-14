import { isHexColor } from "../lib/format";

interface Props {
  value: string | null | undefined;
}

/** The only non-green element: the urine colour painted with its real hex value. */
export function ColorSwatch({ value }: Props) {
  if (!isHexColor(value)) {
    return <span className="swatch-text">{value ?? "---"}</span>;
  }
  return (
    <span className="swatch-text">
      <span className="swatch" style={{ backgroundColor: value }} aria-hidden="true" />
      {value.toUpperCase()}
    </span>
  );
}

import type { ReadingStatus } from "../api/types";
import { STATE_LABELS } from "./StatusPill";

interface Props {
  /** Status per organ. null draws it neutral (still loading). */
  lungs: ReadingStatus | null;
  heart: ReadingStatus | null;
  kidneys: ReadingStatus | null;
  limbs: ReadingStatus | null;
}

const HEART = "M150,160 C150,154 142,152 140,158 C138,152 130,154 130,160 C130,168 140,174 140,180 C140,174 150,168 150,160 Z";

const LABELS: { text: string; x: number; y: number; w: number }[] = [
  { text: "Lungs", x: 6, y: 109, w: 87 },
  { text: "Heart", x: 383, y: 109, w: 79 },
  { text: "Limbs", x: 6, y: 375, w: 121 },
  { text: "Kidneys", x: 383, y: 375, w: 79 },
];

const organClass = (status: ReadingStatus | null) =>
  `bodymap__organ bodymap__organ--${status ?? "loading"}`;

/** Front silhouette with four organs, each drawn in the style of its reading status. */
export function BodyMap({ lungs, heart, kidneys, limbs }: Props) {
  const word = (s: ReadingStatus | null) => (s ? STATE_LABELS[s].toLowerCase() : "loading");
  const summary =
    `Body map. Lungs: ${word(lungs)}. Heart: ${word(heart)}. ` +
    `Kidneys: ${word(kidneys)}. Limbs: ${word(limbs)}.`;
  return (
    <svg className="bodymap" viewBox="0 0 468 460" role="img" aria-label={summary}>
      <g transform="translate(117,-10) scale(0.9)">
        <g className="bodymap__figure">
          <ellipse cx="130" cy="56" rx="26" ry="32" />
          <path d="M118,100 L118,108 Q80,112 66,124 Q56,134 54,160 L46,250 Q42,290 40,320 L52,322 Q58,290 64,256 L74,180 L78,250 Q80,280 84,300 L86,330 L84,420 Q82,470 82,500 L106,500 Q108,460 112,420 L124,330 L130,320 L136,330 L148,420 Q152,460 154,500 L178,500 Q178,470 176,420 L174,330 L176,300 Q180,280 182,250 L186,180 L196,256 Q202,290 208,322 L220,320 Q218,290 214,250 L206,160 Q204,134 194,124 Q180,112 142,108 L142,100 Z" />
          <path className="bodymap__neck" d="M121,86 L118,100 L142,100 L139,86 Z" />
        </g>
        <g className={organClass(lungs)}>
          <path d="M123,122 Q100,124 95,150 Q91,180 98,200 Q112,204 123,192 Z" />
          <path d="M137,122 Q160,124 165,150 Q169,180 162,200 Q148,204 137,192 Z" />
        </g>
        {/* Opaque backing so the heart reads on top of the lung. */}
        <path className="bodymap__neck" d={HEART} />
        <g className={organClass(heart)}>
          <path d={HEART} />
        </g>
        <g className={organClass(kidneys)}>
          <ellipse cx="112" cy="238" rx="7" ry="12" />
          <ellipse cx="148" cy="238" rx="7" ry="12" />
        </g>
        <g className={organClass(limbs)}>
          <path d="M52,190 L68,192 M50,210 L67,212 M208,190 L192,192 M210,210 L193,212" />
          <path d="M86,350 L121,350 M85,370 L119,370 M85,390 L117,390" />
          <path d="M174,350 L139,350 M175,370 L141,370 M175,390 L143,390" />
        </g>
      </g>
      <g className="bodymap__leaders">
        <polyline points="207,134 130,123 0,123" />
        <polyline points="243,141 340,123 468,123" />
        <polyline points="250,204 340,389 468,389" />
        <polyline points="211,323 130,389 0,389" />
      </g>
      {LABELS.map((l) => (
        <g key={l.text} className="bodymap__label">
          <rect x={l.x} y={l.y} width={l.w} height={26} rx={13} />
          <text x={l.x + l.w / 2} y={l.y + 18} textAnchor="middle">
            {l.text}
          </text>
        </g>
      ))}
    </svg>
  );
}

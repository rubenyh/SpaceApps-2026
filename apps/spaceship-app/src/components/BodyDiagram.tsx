import type { ReactNode } from "react";

interface Props {
  lungs: ReactNode;
  heart: ReactNode;
  kidneys: ReactNode;
  limbs: ReactNode;
}

// Layout shared by the SVG and the HTML callout column (px, unscaled).
const SVG_W = 240;
const CALLOUT_H = 118;
const CALLOUT_GAP = 10;
const LINE_Y = 24; // where the leader line meets each callout, from its top
const TOTAL_H = 4 * CALLOUT_H + 3 * CALLOUT_GAP;

const calloutY = (i: number) => i * (CALLOUT_H + CALLOUT_GAP) + LINE_Y;

// Anchor points on the silhouette, in callout order.
const ANCHORS: [number, number][] = [
  [137, 136], // right lung (viewer's right)
  [124, 156], // heart
  [130, 214], // kidney
  [128, 340], // thigh
];

/**
 * Hand-drawn line silhouette (front view) with four leader lines to callouts.
 * The body's left side is drawn on the viewer's right, so the heart sits there.
 */
export function BodyDiagram({ lungs, heart, kidneys, limbs }: Props) {
  const callouts = [lungs, heart, kidneys, limbs];
  return (
    <div className="body-diagram" style={{ height: TOTAL_H }}>
      <svg
        className="body-diagram__svg"
        width={SVG_W}
        height={TOTAL_H}
        viewBox={`0 0 ${SVG_W} ${TOTAL_H}`}
        aria-hidden="true"
      >
        <g className="body-diagram__figure">
          {/* head and neck */}
          <circle cx={110} cy={52} r={26} />
          <path d="M101 77 L101 90 M119 77 L119 90" />
          {/* shoulders, arms */}
          <path d="M101 90 Q68 93 60 108 L48 198 L40 268" />
          <path d="M54 270 L62 200 L72 134" />
          <path d="M119 90 Q152 93 160 108 L172 198 L180 268" />
          <path d="M166 270 L158 200 L148 134" />
          <circle cx={47} cy={278} r={8} />
          <circle cx={173} cy={278} r={8} />
          {/* torso */}
          <path d="M72 134 L76 214 Q73 238 78 256" />
          <path d="M148 134 L144 214 Q147 238 142 256" />
          <path className="body-diagram__thin" d="M78 256 Q110 266 142 256" />
          {/* legs */}
          <path d="M78 256 L82 366 L86 470 L72 484 L100 484 L102 470 L106 366 L110 280" />
          <path d="M142 256 L138 366 L134 470 L148 484 L120 484 L118 470 L114 366 L110 280" />
        </g>
        <g className="body-diagram__organs">
          {/* lungs */}
          <path d="M104 116 Q86 112 84 134 L82 168 Q94 175 104 166 Z" />
          <path d="M116 116 Q134 112 136 134 L138 168 Q126 175 116 166 Z" />
          {/* heart */}
          <path d="M120 150 q4 -7 9 -3 q5 5 -9 15 q-14 -10 -9 -15 q5 -4 9 3 z" />
          {/* kidneys */}
          <ellipse cx={96} cy={214} rx={6} ry={11} />
          <ellipse cx={124} cy={214} rx={6} ry={11} />
          {/* limb measurement point */}
          <circle cx={128} cy={340} r={6} />
          <path className="body-diagram__thin" d="M120 340 L136 340 M128 332 L128 348" />
        </g>
        <g className="body-diagram__leaders">
          {ANCHORS.map(([ax, ay], i) => {
            const cy = calloutY(i);
            return (
              <g key={i}>
                <circle cx={ax} cy={ay} r={2.5} />
                <polyline points={`${ax},${ay} 196,${ay} 214,${cy} ${SVG_W},${cy}`} />
              </g>
            );
          })}
        </g>
      </svg>
      <div className="body-diagram__callouts" style={{ gap: CALLOUT_GAP }}>
        {callouts.map((c, i) => (
          <div key={i} className="body-diagram__slot" style={{ height: CALLOUT_H }}>
            {c}
          </div>
        ))}
      </div>
    </div>
  );
}

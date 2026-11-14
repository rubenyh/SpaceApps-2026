import { S } from "../surface";
import { StatusBadge } from "spaceship-app";

export const Normal = () => (
  <S>
    <StatusBadge status="normal" />
  </S>
);
export const Alert = () => (
  <S>
    <StatusBadge status="alert" />
  </S>
);
export const NoData = () => (
  <S>
    <StatusBadge status="no_data" />
  </S>
);
export const Stale = () => (
  <S>
    <StatusBadge status="stale" />
  </S>
);
export const NoRange = () => (
  <S>
    <StatusBadge status="no_range" />
  </S>
);
export const SampleValidity = () => (
  <S>
    <div style={{ display: "flex", gap: 12 }}>
      <StatusBadge status="normal" rangeRole="sample_validity" />
      <StatusBadge status="alert" rangeRole="sample_validity" />
    </div>
  </S>
);

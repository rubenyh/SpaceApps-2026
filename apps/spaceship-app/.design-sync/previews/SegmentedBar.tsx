import { S } from "../surface";
import { SegmentedBar } from "spaceship-app";

export const InRange = () => (
  <S>
    <SegmentedBar value={72} normalMin={50} normalMax={100} label="PULSO" />
  </S>
);
export const AboveRange = () => (
  <S>
    <SegmentedBar value={118} normalMin={50} normalMax={100} label="PULSO" />
  </S>
);
export const BelowRange = () => (
  <S>
    <SegmentedBar value={88} normalMin={94} normalMax={100} label="SpO₂" />
  </S>
);
export const NoValue = () => (
  <S>
    <SegmentedBar value={null} normalMin={50} normalMax={100} label="PULSO" />
  </S>
);
export const NoRange = () => (
  <S>
    <SegmentedBar value={1.02} normalMin={null} normalMax={null} label="SALINIDAD" />
  </S>
);

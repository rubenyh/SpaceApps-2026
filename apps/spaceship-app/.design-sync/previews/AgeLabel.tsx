import { S } from "../surface";
import { AgeLabel } from "spaceship-app";

export const Fresh = () => (
  <S>
    <AgeLabel seconds={42} />
  </S>
);
export const StaleEmphasis = () => (
  <S>
    <AgeLabel seconds={5400} emphasis />
  </S>
);
export const WithPrefix = () => (
  <S>
    <AgeLabel seconds={780} prefix="última muestra:" />
  </S>
);

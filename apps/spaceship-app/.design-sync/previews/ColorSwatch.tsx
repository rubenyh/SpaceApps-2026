import { S } from "../surface";
import { ColorSwatch } from "spaceship-app";

export const HexColor = () => (
  <S>
    <ColorSwatch value="#e8c84a" />
  </S>
);
export const DarkSample = () => (
  <S>
    <ColorSwatch value="#b5651d" />
  </S>
);
export const NotAHexValue = () => (
  <S>
    <ColorSwatch value="ámbar" />
  </S>
);
export const Missing = () => (
  <S>
    <ColorSwatch value={null} />
  </S>
);

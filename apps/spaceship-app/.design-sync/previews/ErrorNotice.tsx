import { S } from "../surface";
import { ErrorNotice, HttpError, NetworkError } from "spaceship-app";

export const HttpFailure = () => (
  <S>
    <ErrorNotice error={new HttpError(404, "astronaut 'ast-09' not found")} hasData={false} />
  </S>
);
export const OfflineWithPreviousData = () => (
  <S>
    <ErrorNotice error={new NetworkError("Failed to fetch")} hasData />
  </S>
);
export const OfflineWithoutData = () => (
  <S>
    <ErrorNotice error={new NetworkError("Failed to fetch")} hasData={false} />
  </S>
);

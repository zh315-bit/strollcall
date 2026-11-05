import { Composition } from "remotion";
import { Promo } from "./Promo";
export const Root = () => (
  <Composition id="Promo" component={Promo} durationInFrames={2400} fps={30} width={1920} height={1080} defaultProps={{ captions: true }} />
);

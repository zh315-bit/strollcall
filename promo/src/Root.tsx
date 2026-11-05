import { Composition } from "remotion";
import { Promo } from "./Promo";
import script from "./script.json";
export const Root = () => (
  <Composition id="Promo" component={Promo} durationInFrames={Math.round(script[script.length - 1].end * 30)} fps={30} width={1920} height={1080} defaultProps={{ captions: true }} />
);

import React from "react";
import { Composition } from "remotion";
import { Film, FILM_LENGTH } from "./v2/Film";
import { BugShot, SHOT_H, SHOT_W } from "./v2/Screens";

const HeroShot: React.FC = () => <BugShot notification />;

export const Root: React.FC = () => (
  <>
    <Composition id="Squint" component={Film} durationInFrames={FILM_LENGTH} fps={30} width={1920} height={1080} />
    {/* The screenshot Squint redacts for real in the finale (render with --scale=2). */}
    <Composition id="HeroShot" component={HeroShot} durationInFrames={1} fps={30} width={SHOT_W} height={SHOT_H} />
  </>
);

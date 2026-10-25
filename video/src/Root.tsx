import React from "react";
import { Audio, Composition, Sequence, staticFile } from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { Call, Mentor, Ordinary, Refusal, Return, Reward, Threshold, Trials } from "./Scenes";

const FADE = 15;
// The hero's journey, one scene per chapter (frames at 30 fps).
const SCENES: [React.FC, number][] = [
  [Ordinary, 300],
  [Call, 330],
  [Refusal, 220],
  [Mentor, 240],
  [Threshold, 300],
  [Trials, 360],
  [Reward, 270],
  [Return, 330],
];
export const DURATION = SCENES.reduce((t, [, d]) => t + d, 0) - FADE * (SCENES.length - 1);

/** Absolute start frame of each scene, for placing sound effects. */
const startOf = (index: number) =>
  SCENES.slice(0, index).reduce((t, [, d]) => t + d - FADE, 0);

const Sfx: React.FC<{ at: number; file: string; volume?: number }> = ({ at, file, volume = 0.6 }) => (
  <Sequence from={at} layout="none">
    <Audio src={staticFile(`sfx/${file}`)} volume={volume} />
  </Sequence>
);

const Squint: React.FC = () => (
  <>
    <TransitionSeries>
      {SCENES.map(([Scene, duration], i) => (
        <React.Fragment key={i}>
          {i > 0 && <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: FADE })} />}
          <TransitionSeries.Sequence durationInFrames={duration}>
            <Scene />
          </TransitionSeries.Sequence>
        </React.Fragment>
      ))}
    </TransitionSeries>
    <Audio src={staticFile("sfx/music.wav")} volume={(f) => Math.min(0.5, f / 60) * Math.min(1, (DURATION - f) / 60)} />
    {[100, 175, 228].map((f) => <Sfx key={f} at={startOf(0) + f} file="key.wav" />)}
    <Sfx at={startOf(1) + 30} file="alert.wav" volume={0.35} />
    <Sfx at={startOf(1) + 200} file="whoosh.wav" />
    {[70, 82, 94].map((f) => <Sfx key={f} at={startOf(2) + f} file="strike.wav" volume={0.4} />)}
    <Sfx at={startOf(3) + 52} file="chime.wav" volume={0.5} />
    {[40, 42, 44, 46].map((f) => <Sfx key={f} at={startOf(4) + f} file="key.wav" volume={0.45} />)}
    <Sfx at={startOf(4) + 116} file="shutter.wav" />
    <Sfx at={startOf(4) + 150} file="chime.wav" volume={0.45} />
    <Sfx at={startOf(5) + 250} file="whoosh.wav" volume={0.4} />
    <Sfx at={startOf(6) + 26} file="key.wav" />
    <Sfx at={startOf(7) + 165} file="chime.wav" volume={0.5} />
  </>
);

export const Root: React.FC = () => (
  <Composition id="Squint" component={Squint} durationInFrames={DURATION} fps={30} width={1920} height={1080} />
);

/**
 * What the user chose for the race flags. Pure on purpose: tests/js runs it under node.
 * secs: how long it shows; 0, for as long as the flag is out. The checkered counts from the driver's own line.
 */
export const FLAGS = {
  green: { name: 'Green', secs: 8 },
  yellow: { name: 'Yellow', secs: 0 },
  blue: { name: 'Blue', secs: 0 },
  debris: { name: 'Slippery surface', secs: 0 },
  white: { name: 'White', secs: 8 },
  checkered: { name: 'Checkered', secs: 2, note: 'Seconds after you cross the line' },
  black: { name: 'Black', secs: 0 },
  meatball: { name: 'Meatball', secs: 0 },
};

/** The saved choices over the defaults; raceFlags is the switch from before this page. */
export function flagCfg(prefs) {
  const saved = prefs.flags ?? {}, items = {};
  for (const [k, f] of Object.entries(FLAGS)) items[k] = { on: saved.items?.[k]?.on ?? true, secs: saved.items?.[k]?.secs ?? f.secs };
  return { on: saved.on ?? prefs.raceFlags !== false, items };
}

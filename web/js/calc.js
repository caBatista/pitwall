/** Fuel plan. Pure, tests/js runs it under node.
 *
 * How to reach the flag with reserve laps of fuel left. Enough already: {stops: 0, toGo, spare}.
 * Otherwise how many stops and the laps of the next one. A stop on lap N means entering the pits at the
 * end of lap N: last is the last lap the fuel in the tank completes, first the earliest from which full
 * tanks at every stop still get there; this lap counts until the pit entry is behind me. add: what
 * goes in on first.
 * laps: to go from here; lap: the lap I am on; pct: how far into it. */
const PIT_ENTRY = 0.95;   // the telemetry doesn't say where it is: the stop is at the very end of the lap

export function pitPlan(level, avg, laps, reserve, tank, lap, pct = 0) {
  if (!avg || level == null || laps == null) return null;
  const toGo = laps * avg, spare = level - toGo;
  if (spare >= reserve * avg) return { stops: 0, toGo, spare };
  const missing = toGo + reserve * avg - level;
  // laps after this one, counted to the end of the lap of the stop
  const reach = Math.max(0, Math.floor(pct + level / avg + 1e-9) - 1);
  let stops = tank ? Math.max(1, Math.ceil(missing / tank)) : 1, wait = 0;
  for (; tank; stops++) {   // stopping too early would need one stop more
    wait = Math.max(0, Math.ceil(laps + reserve - stops * tank / avg + pct - 1 - 1e-9));
    if (wait <= reach) break;
  }
  if (pct > PIT_ENTRY) wait = Math.max(wait, Math.min(1, reach));
  const atStop = level - (wait + 1 - pct) * avg;   // what is left when pitting on first
  const add = tank ? Math.min(missing, tank - Math.max(0, atStop)) : missing;
  return { stops, add, first: lap + wait, last: lap + reach };
}

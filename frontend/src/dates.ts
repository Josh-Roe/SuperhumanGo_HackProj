export function localTime(iso: string, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const get = (name: string) => parts.find((p) => p.type === name)?.value;
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}
// Resolve local wall time against IANA rules. Reject nonexistent/ambiguous DST times.
export function toInstant(wallTime: string, timezone: string): string {
  const guess = Date.parse(`${wallTime}:00Z`);
  if (!Number.isFinite(guess))
    throw new Error("Enter valid start and end dates.");
  const candidates = new Set<string>();
  for (const hours of [-36, -12, 0, 12, 36]) {
    const instant = guess + hours * 3600000;
    const rendered = Date.parse(
      `${localTime(new Date(instant).toISOString(), timezone)}:00Z`,
    );
    const possible = new Date(guess - (rendered - instant)).toISOString();
    if (localTime(possible, timezone) === wallTime) candidates.add(possible);
  }
  if (candidates.size !== 1)
    throw new Error(
      "This local time is ambiguous or unavailable during a daylight-saving change. Choose a time outside the clock change.",
    );
  return [...candidates][0];
}
export function eventDate(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(iso));
}

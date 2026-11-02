export function introProgress(
  distance: number,
  viewportHeight: number,
): number {
  if (viewportHeight <= 0) return 0;
  return Math.max(0, Math.min(1, distance / (viewportHeight * 0.7)));
}

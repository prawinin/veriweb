export function sameOrigin(
  origin: string | null,
  host: string | null,
  protocol: string,
  configured?: string,
): boolean {
  if (!origin) return true;
  if (!host && !configured) return false;
  try {
    const expected = new URL(configured?.trim() || `${protocol}//${host}`);
    const supplied = new URL(origin);
    return (
      !supplied.username &&
      !supplied.password &&
      supplied.origin === expected.origin
    );
  } catch {
    return false;
  }
}

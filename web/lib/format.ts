// Display helpers. Rounding is display only (RFC-0009 S4, RFC-0012): the full value goes in `title`.

export type Stats = { n: number; n_failed: number; mean: number; stdev: number; min: number; max: number };

/** 4 significant digits, thousands separated, exponent outside [1e-4, 1e9). */
export function sig4(v: number | null | undefined): string {
  if (v === null || v === undefined) return "null"; // a statistic over no successful repetition
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a < 1e-4 || a >= 1e9) return v.toExponential(3).replace("e+", "e");
  if (Number.isInteger(v) && a < 1e4) return v.toLocaleString("en-US");
  const r = Number(v.toPrecision(4));
  const decimals = Math.max(0, 3 - Math.floor(Math.log10(Math.abs(r))));
  return r.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Statistics over successful repetitions (RFC-0004 §Statistics): sample standard deviation, 0 when n = 1. */
export function stats(values: number[], n_failed = 0): Stats {
  const n = values.length;
  if (n === 0) throw new Error("stats over no successful repetition (D-STAT null rule n = 0)");
  const mean = values.reduce((s, v) => s + v, 0) / n;
  const stdev = n > 1 ? Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1)) : 0;
  return { n, n_failed, mean, stdev, min: Math.min(...values), max: Math.max(...values) };
}

export const short = (hash: string, n = 12) => hash.slice(0, n);

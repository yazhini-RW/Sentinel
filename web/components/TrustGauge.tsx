import { formatScore, scoreColor } from "@/lib/format";

const SIZE = 148;
const STROKE = 12;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function TrustGauge({ score }: { score: number | null }) {
  const clamped = score === null ? 0 : Math.max(0, Math.min(100, score));
  const color = scoreColor(score);
  const label =
    score === null ? "Trust score not available" : `Trust score ${formatScore(score)} out of 100`;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label={label}
      >
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          strokeWidth={STROKE}
          className="stroke-zinc-200 dark:stroke-zinc-800"
        />
        {score !== null && (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - clamped / 100)}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          />
        )}
        <text
          x="50%"
          y="50%"
          textAnchor="middle"
          dominantBaseline="central"
          fill={color}
          className="text-4xl font-bold"
        >
          {formatScore(score)}
        </text>
      </svg>
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        Trust score
      </span>
    </div>
  );
}

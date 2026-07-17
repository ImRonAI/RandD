import { useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export type YoloDetection = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confidence: number;
  classId: number;
  label: string;
};

export type YoloDetectionFrame = {
  timestamp: number;
  width: number;
  height: number;
  detections: YoloDetection[];
};

type YoloOverlayProps = {
  frame: YoloDetectionFrame | null;
  facing: "environment" | "user";
  className?: string;
};

type Viewport = {
  width: number;
  height: number;
};

type RenderableDetection = YoloDetection & {
  key: string;
  accent: string;
  left: number;
  top: number;
  right: number;
  bottom: number;
  displayLabel: string;
  plateWidth: number;
  plateX: number;
  plateY: number;
};

type LabelRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const ACCENTS = ["#B8FF43", "#4DE7FF", "#62F6C5", "#E4FF77"] as const;
const PLATE_HEIGHT = 24;
const PLATE_GAP = 3;
const CONFIDENCE_COLUMN_WIDTH = 46;

const clampUnit = (value: number) => Math.min(1, Math.max(0, value));
const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

const isValidFrame = (frame: YoloDetectionFrame | null) =>
  Boolean(
    frame &&
      Number.isFinite(frame.width) &&
      Number.isFinite(frame.height) &&
      frame.width > 0 &&
      frame.height > 0
  );

const compactLabel = (label: string, maxLength: number) => {
  const normalized = label.trim().toUpperCase();
  return normalized.length > maxLength
    ? `${normalized.slice(0, Math.max(1, maxLength - 1))}…`
    : normalized;
};

const spatialKey = (
  detection: YoloDetection,
  left: number,
  top: number,
  right: number,
  bottom: number
) => {
  const quantize = (value: number) => Math.round(value * 24);
  const centerX = (left + right) / 2;
  const centerY = (top + bottom) / 2;

  return [
    Math.trunc(detection.classId),
    detection.label.trim().toLowerCase(),
    quantize(centerX),
    quantize(centerY),
    quantize(right - left),
    quantize(bottom - top),
  ].join(":");
};

const intersects = (left: LabelRect, right: LabelRect) =>
  left.x < right.x + right.width + PLATE_GAP &&
  left.x + left.width + PLATE_GAP > right.x &&
  left.y < right.y + right.height + PLATE_GAP &&
  left.y + left.height + PLATE_GAP > right.y;

const chooseLabelPosition = (
  preferredX: number,
  preferredY: number,
  boxTop: number,
  boxBottom: number,
  plateWidth: number,
  viewport: Viewport,
  occupied: LabelRect[]
) => {
  const maxX = Math.max(4, viewport.width - plateWidth - 4);
  const maxY = Math.max(4, viewport.height - PLATE_HEIGHT - 4);
  const alternateX = clamp(preferredX + 14, 4, maxX);
  const insideTop = clamp(boxTop + 4, 4, maxY);
  const insideBottom = clamp(boxBottom - PLATE_HEIGHT - 4, 4, maxY);
  const step = PLATE_HEIGHT + PLATE_GAP;
  const candidates = [
    [preferredX, preferredY],
    [preferredX, insideTop],
    [preferredX, insideBottom],
    [preferredX, preferredY - step],
    [preferredX, preferredY + step],
    [alternateX, preferredY - step * 2],
    [alternateX, preferredY + step * 2],
  ];

  for (const [candidateX, candidateY] of candidates) {
    const candidate = {
      x: clamp(candidateX, 4, maxX),
      y: clamp(candidateY, 4, maxY),
      width: plateWidth,
      height: PLATE_HEIGHT,
    };
    if (!occupied.some((label) => intersects(candidate, label))) {
      occupied.push(candidate);
      return candidate;
    }
  }

  const fallback = {
    x: clamp(preferredX, 4, maxX),
    y: clamp(preferredY, 4, maxY),
    width: plateWidth,
    height: PLATE_HEIGHT,
  };
  occupied.push(fallback);
  return fallback;
};

const buildDetections = (
  frame: YoloDetectionFrame,
  viewport: Viewport,
  facing: YoloOverlayProps["facing"]
) => {
  const scale = Math.max(
    viewport.width / frame.width,
    viewport.height / frame.height
  );
  const offsetX = (viewport.width - frame.width * scale) / 2;
  const offsetY = (viewport.height - frame.height * scale) / 2;
  const keyCounts = new Map<string, number>();

  const detections = frame.detections
    .map((detection): Omit<RenderableDetection, "plateX" | "plateY"> | null => {
      const values = [
        detection.x1,
        detection.y1,
        detection.x2,
        detection.y2,
        detection.confidence,
        detection.classId,
      ];
      if (
        values.some((value) => !Number.isFinite(value)) ||
        typeof detection.label !== "string" ||
        detection.label.trim().length === 0
      ) {
        return null;
      }

      const sourceLeft = clampUnit(Math.min(detection.x1, detection.x2));
      const sourceRight = clampUnit(Math.max(detection.x1, detection.x2));
      const top = clampUnit(Math.min(detection.y1, detection.y2));
      const bottom = clampUnit(Math.max(detection.y1, detection.y2));
      if (sourceRight <= sourceLeft || bottom <= top) {
        return null;
      }

      const normalizedLeft = facing === "user" ? 1 - sourceRight : sourceLeft;
      const normalizedRight = facing === "user" ? 1 - sourceLeft : sourceRight;
      const left = normalizedLeft * frame.width * scale + offsetX;
      const right = normalizedRight * frame.width * scale + offsetX;
      const displayTop = top * frame.height * scale + offsetY;
      const displayBottom = bottom * frame.height * scale + offsetY;
      if (
        right <= 0 ||
        left >= viewport.width ||
        displayBottom <= 0 ||
        displayTop >= viewport.height
      ) {
        return null;
      }

      const baseKey = spatialKey(
        detection,
        normalizedLeft,
        top,
        normalizedRight,
        bottom
      );
      const occurrence = keyCounts.get(baseKey) ?? 0;
      keyCounts.set(baseKey, occurrence + 1);
      const maxPlateWidth = Math.max(76, viewport.width - 8);
      const maxLabelLength = Math.max(
        3,
        Math.min(18, Math.floor((maxPlateWidth - 64) / 7.3))
      );
      const displayLabel = compactLabel(detection.label, maxLabelLength);
      const plateWidth = Math.min(
        maxPlateWidth,
        Math.max(110, displayLabel.length * 7.3 + 64)
      );
      const classIndex =
        Math.abs(Math.trunc(detection.classId)) % ACCENTS.length;

      return {
        ...detection,
        key: occurrence === 0 ? baseKey : `${baseKey}:${occurrence}`,
        accent: ACCENTS[classIndex],
        confidence: clampUnit(detection.confidence),
        left,
        top: displayTop,
        right,
        bottom: displayBottom,
        displayLabel,
        plateWidth,
      };
    })
    .filter(
      (
        detection
      ): detection is Omit<RenderableDetection, "plateX" | "plateY"> =>
        detection !== null
    )
    .sort((left, right) => left.top - right.top || left.left - right.left);

  const occupied: LabelRect[] = [];
  return detections.map((detection): RenderableDetection => {
    const preferredX = clamp(
      detection.left,
      4,
      Math.max(4, viewport.width - detection.plateWidth - 4)
    );
    const preferredY =
      detection.top >= PLATE_HEIGHT + 6
        ? detection.top - PLATE_HEIGHT - 3
        : detection.top + 4;
    const label = chooseLabelPosition(
      preferredX,
      preferredY,
      detection.top,
      detection.bottom,
      detection.plateWidth,
      viewport,
      occupied
    );

    return {
      ...detection,
      plateX: label.x,
      plateY: label.y,
    };
  });
};

const cornerPath = (
  left: number,
  top: number,
  right: number,
  bottom: number
) => {
  const length = Math.max(
    2,
    Math.min(14, (right - left) / 2, (bottom - top) / 2)
  );

  return [
    `M ${left} ${top + length} V ${top} H ${left + length}`,
    `M ${right - length} ${top} H ${right} V ${top + length}`,
    `M ${right} ${bottom - length} V ${bottom} H ${right - length}`,
    `M ${left + length} ${bottom} H ${left} V ${bottom - length}`,
  ].join(" ");
};

export const YoloOverlay = ({
  frame,
  facing,
  className,
}: YoloOverlayProps) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [viewport, setViewport] = useState<Viewport>({ width: 0, height: 0 });
  const validFrame = isValidFrame(frame);

  useLayoutEffect(() => {
    if (!validFrame || !svgRef.current) {
      return;
    }

    const svg = svgRef.current;
    const updateViewport = (width: number, height: number) => {
      if (width <= 0 || height <= 0) {
        return;
      }
      setViewport((current) =>
        current.width === width && current.height === height
          ? current
          : { width, height }
      );
    };
    const initial = svg.getBoundingClientRect();
    updateViewport(initial.width, initial.height);

    const observer = new ResizeObserver(([entry]) => {
      if (entry) {
        updateViewport(entry.contentRect.width, entry.contentRect.height);
      }
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, [validFrame]);

  if (!validFrame || !frame) {
    return null;
  }

  const hasViewport = viewport.width > 0 && viewport.height > 0;
  const detections = hasViewport
    ? buildDetections(frame, viewport, facing)
    : [];
  const viewBoxWidth = hasViewport ? viewport.width : 1;
  const viewBoxHeight = hasViewport ? viewport.height : 1;

  return (
    <svg
      aria-hidden="true"
      className={cn(
        "pointer-events-none absolute inset-0 h-full w-full select-none",
        className
      )}
      focusable="false"
      preserveAspectRatio="xMidYMid slice"
      ref={svgRef}
      viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
    >
      <style>{`
        @keyframes yolo-acquire {
          0%, 100% { opacity: 0.38; }
          50% { opacity: 0.9; }
        }

        .yolo-acquire {
          animation: yolo-acquire 2.4s ease-in-out infinite;
        }

        @media (prefers-reduced-motion: reduce) {
          .yolo-acquire { animation: none; opacity: 0.68; }
        }
      `}</style>

      {detections.map((detection) => {
        const boxWidth = detection.right - detection.left;
        const boxHeight = detection.bottom - detection.top;
        const confidence = Math.round(detection.confidence * 100);

        return (
          <g key={detection.key}>
            <rect
              fill="none"
              height={boxHeight}
              rx="1.5"
              stroke={detection.accent}
              strokeOpacity="0.38"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              width={boxWidth}
              x={detection.left}
              y={detection.top}
            />

            <path
              d={cornerPath(
                detection.left,
                detection.top,
                detection.right,
                detection.bottom
              )}
              fill="none"
              stroke={detection.accent}
              strokeLinecap="square"
              strokeWidth="2"
              vectorEffect="non-scaling-stroke"
            />

            {boxWidth > 16 && boxHeight > 10 ? (
              <path
                className="yolo-acquire"
                d={`M ${detection.left + 5} ${detection.top + 5} H ${Math.min(
                  detection.right - 5,
                  detection.left + Math.max(10, boxWidth * 0.28)
                )}`}
                fill="none"
                stroke={detection.accent}
                strokeLinecap="round"
                strokeWidth="1.5"
                vectorEffect="non-scaling-stroke"
              />
            ) : null}

            <g>
              <rect
                fill="rgba(5, 12, 15, 0.88)"
                height={PLATE_HEIGHT}
                rx="3"
                stroke="rgba(255, 255, 255, 0.18)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
                width={detection.plateWidth}
                x={detection.plateX}
                y={detection.plateY}
              />
              <rect
                fill={detection.accent}
                height={PLATE_HEIGHT - 8}
                rx="1"
                width="3"
                x={detection.plateX + 5}
                y={detection.plateY + 4}
              />
              <text
                fill="#F5FAF8"
                fontFamily="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
                fontSize="11.5"
                fontWeight="650"
                letterSpacing="0.5"
                x={detection.plateX + 14}
                y={detection.plateY + 16}
              >
                {detection.displayLabel}
              </text>
              <line
                stroke="rgba(255, 255, 255, 0.18)"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
                x1={
                  detection.plateX +
                  detection.plateWidth -
                  CONFIDENCE_COLUMN_WIDTH
                }
                x2={
                  detection.plateX +
                  detection.plateWidth -
                  CONFIDENCE_COLUMN_WIDTH
                }
                y1={detection.plateY + 6}
                y2={detection.plateY + PLATE_HEIGHT - 6}
              />
              <text
                fill={detection.accent}
                fontFamily="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
                fontSize="11"
                fontWeight="700"
                textAnchor="end"
                x={detection.plateX + detection.plateWidth - 8}
                y={detection.plateY + 16}
              >
                {confidence}%
              </text>
            </g>
          </g>
        );
      })}
    </svg>
  );
};

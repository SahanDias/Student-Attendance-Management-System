/**
 * Describes each stage of the backend's OpenCV pipeline. Used both for the
 * real display of stage output (name/description alongside a backend-served
 * image) and, via services/mock-data.ts, to synthesize a plausible mock run.
 */
export const PIPELINE_STAGES: { name: string; description: string; filter: string }[] = [
  {
    name: "Resize",
    description:
      "The photograph is scaled to a fixed working width (1600px) with INTER_AREA interpolation so downstream kernel sizes behave consistently regardless of camera resolution.",
    filter: "none",
  },
  {
    name: "Grayscale",
    description:
      "BGR channels are collapsed to a single luminance channel via cv2.cvtColor(COLOR_BGR2GRAY), discarding ink colour which carries no signal for presence detection.",
    filter: "grayscale(1)",
  },
  {
    name: "Denoise",
    description:
      "A bilateral filter smooths paper grain and JPEG artefacts while preserving the hard edges of printed rules and pen strokes.",
    filter: "grayscale(1) blur(0.6px)",
  },
  {
    name: "Deskew",
    description:
      "Dominant line angles are estimated with a Hough transform and the page is rotated back to horizontal using a warpAffine matrix about the image centre.",
    filter: "grayscale(1) contrast(1.05)",
  },
  {
    name: "Binarize",
    description:
      "Adaptive Gaussian thresholding converts the page to pure black/white per local neighbourhood, which tolerates the uneven lighting typical of handheld photos.",
    filter: "grayscale(1) contrast(2.6) brightness(1.15)",
  },
  {
    name: "Grid Detection",
    description:
      "Morphological opening with long horizontal and vertical kernels isolates the table rules; their intersections give the row and column boundaries of the sheet.",
    filter: "grayscale(1) contrast(2.2) invert(1)",
  },
  {
    name: "Cell Extraction",
    description:
      "Each detected row is cropped at the configured signature column, with a small inward margin so the printed rules do not leak into the cell.",
    filter: "grayscale(1) contrast(1.6) sepia(0.15)",
  },
  {
    name: "Presence Detection",
    description:
      "Per cell, connected components smaller than the minimum area are discarded and the remaining ink pixel ratio is compared against the ink-ratio threshold to decide present/absent.",
    filter: "grayscale(1) contrast(1.4) hue-rotate(190deg) saturate(2)",
  },
];

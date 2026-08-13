
export interface ProcessingSettings {
  // PROCESSING
  resizeWidth: number;
  adaptiveBlockSize: number;
  adaptiveConstant: number;
  deskewSearchRangeDegrees: number;
  // GRID DETECTION
  horizontalThresholdFraction: number;
  verticalThresholdFraction: number;
  horizontalKernelScale: number;
  verticalKernelScale: number;
  minCols: number;
  headerRows: number;
  // CELL EXTRACTION
  signatureHorizontalShrink: number;
  signatureVerticalShrink: number;
  signatureVerticalExpansion: number;
  presenceHorizontalShrink: number;
  presenceVerticalShrink: number;
  // PRESENCE DETECTION
  minInkRatio: number;
  minComponentArea: number;
  // SIGNATURE MATCHING
  similarityThreshold: number;
  orbNfeatures: number;
  minKeypoints: number;
}

export const PROCESSING_SETTINGS_DEFAULTS: ProcessingSettings = {
  resizeWidth: 1600,
  adaptiveBlockSize: 31,
  adaptiveConstant: 10,
  deskewSearchRangeDegrees: 6,

  horizontalThresholdFraction: 0.25,
  verticalThresholdFraction: 0.2,
  horizontalKernelScale: 25,
  verticalKernelScale: 40,
  minCols: 4,
  headerRows: 1,

  signatureHorizontalShrink: 0.06,
  signatureVerticalShrink: 0.04,
  signatureVerticalExpansion: 0.06,
  presenceHorizontalShrink: 0.1,
  presenceVerticalShrink: 0.1,

  minInkRatio: 0.03,
  minComponentArea: 40,

  similarityThreshold: 0.6,
  orbNfeatures: 500,
  minKeypoints: 10,
};

const STORAGE_KEY = "sams.processing_settings";

export function loadProcessingSettings(): ProcessingSettings {
  if (typeof window === "undefined") return PROCESSING_SETTINGS_DEFAULTS;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (!stored) return PROCESSING_SETTINGS_DEFAULTS;
  try {
    return {
      ...PROCESSING_SETTINGS_DEFAULTS,
      ...(JSON.parse(stored) as Partial<ProcessingSettings>),
    };
  } catch {
    return PROCESSING_SETTINGS_DEFAULTS;
  }
}

export function saveProcessingSettings(settings: ProcessingSettings): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

/** Maps the form's camelCase fields onto ProcessOptions' snake_case wire shape. */
export function toProcessOptionsPayload(settings: ProcessingSettings): Record<string, number> {
  return {
    resize_width: settings.resizeWidth,
    adaptive_block_size: settings.adaptiveBlockSize,
    adaptive_constant: settings.adaptiveConstant,
    deskew_search_range_degrees: settings.deskewSearchRangeDegrees,

    horizontal_threshold_fraction: settings.horizontalThresholdFraction,
    vertical_threshold_fraction: settings.verticalThresholdFraction,
    horizontal_kernel_scale: settings.horizontalKernelScale,
    vertical_kernel_scale: settings.verticalKernelScale,
    min_cols: settings.minCols,
    header_rows: settings.headerRows,

    signature_horizontal_shrink: settings.signatureHorizontalShrink,
    signature_vertical_shrink: settings.signatureVerticalShrink,
    signature_vertical_expansion: settings.signatureVerticalExpansion,
    presence_horizontal_shrink: settings.presenceHorizontalShrink,
    presence_vertical_shrink: settings.presenceVerticalShrink,

    min_ink_ratio: settings.minInkRatio,
    min_component_area: settings.minComponentArea,

    similarity_threshold: settings.similarityThreshold,
    orb_nfeatures: settings.orbNfeatures,
    min_keypoints: settings.minKeypoints,
  };
}

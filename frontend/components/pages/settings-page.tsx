"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/utils";
import {
  PROCESSING_SETTINGS_DEFAULTS,
  loadProcessingSettings,
  saveProcessingSettings,
  type ProcessingSettings,
} from "@/lib/processing-settings";

interface SettingField {
  key: keyof ProcessingSettings;
  label: string;
  description?: string;
  min: number;
  max: number;
  step: number;
  decimals: number;
  unit?: string;
}

interface SettingGroup {
  name: string;
  description: string;
  fields: SettingField[];
}

// Every field here is sent on every POST /sheets/{id}/process request (see
// lib/processing-settings.ts's toProcessOptionsPayload) and overrides the
// matching service constructor's own default -- ResizeStep/DeskewStep,
// GridDetector, CellExtractor, PresenceDetector, or SignatureMatcher via the
// session document (see app/api/routes/signatures.py _matcher_for_session).
const SETTING_GROUPS: SettingGroup[] = [
  {
    name: "Processing",
    description: "Resize target and the deskew step's own internal angle-search tuning.",
    fields: [
      {
        key: "resizeWidth",
        label: "Resize width",
        min: 800,
        max: 3000,
        step: 50,
        decimals: 0,
        unit: "px",
      },
      {
        key: "adaptiveBlockSize",
        label: "Adaptive threshold block size",
        description: "Odd values only.",
        min: 11,
        max: 51,
        step: 2,
        decimals: 0,
      },
      {
        key: "adaptiveConstant",
        label: "Adaptive threshold constant",
        min: 2,
        max: 30,
        step: 1,
        decimals: 0,
      },
      {
        key: "deskewSearchRangeDegrees",
        label: "Deskew search range",
        min: 2,
        max: 15,
        step: 1,
        decimals: 0,
        unit: "°",
      },
    ],
  },
  {
    name: "Grid Detection",
    description: "How the printed table's row/column rules are located and validated.",
    fields: [
      {
        key: "horizontalThresholdFraction",
        label: "Horizontal threshold fraction",
        min: 0.05,
        max: 0.6,
        step: 0.01,
        decimals: 2,
      },
      {
        key: "verticalThresholdFraction",
        label: "Vertical threshold fraction",
        min: 0.05,
        max: 0.6,
        step: 0.01,
        decimals: 2,
      },
      {
        key: "horizontalKernelScale",
        label: "Horizontal kernel scale",
        min: 10,
        max: 60,
        step: 1,
        decimals: 0,
      },
      {
        key: "verticalKernelScale",
        label: "Vertical kernel scale",
        min: 10,
        max: 60,
        step: 1,
        decimals: 0,
      },
      { key: "minCols", label: "Minimum columns", min: 2, max: 8, step: 1, decimals: 0 },
      {
        key: "headerRows",
        label: "Header rows",
        description: "Default for new uploads.",
        min: 0,
        max: 3,
        step: 1,
        decimals: 0,
      },
    ],
  },
  {
    name: "Cell Extraction",
    description:
      "Signature crops are generous (for matching); presence crops are tight (to exclude the printed rule).",
    fields: [
      {
        key: "signatureHorizontalShrink",
        label: "Signature crop: horizontal shrink",
        min: 0,
        max: 0.25,
        step: 0.01,
        decimals: 2,
      },
      {
        key: "signatureVerticalShrink",
        label: "Signature crop: vertical shrink",
        min: 0,
        max: 0.25,
        step: 0.01,
        decimals: 2,
      },
      {
        key: "signatureVerticalExpansion",
        label: "Signature crop: vertical expansion",
        min: 0,
        max: 0.25,
        step: 0.01,
        decimals: 2,
      },
      {
        key: "presenceHorizontalShrink",
        label: "Presence crop: horizontal shrink",
        min: 0,
        max: 0.25,
        step: 0.01,
        decimals: 2,
      },
      {
        key: "presenceVerticalShrink",
        label: "Presence crop: vertical shrink",
        min: 0,
        max: 0.25,
        step: 0.01,
        decimals: 2,
      },
    ],
  },
  {
    name: "Presence Detection",
    description: "Applied to the tight presence crop of every extracted signature cell.",
    fields: [
      {
        key: "minInkRatio",
        label: "Ink ratio threshold",
        description: "Fraction of dark pixels above which the row counts as signed.",
        min: 0.005,
        max: 0.2,
        step: 0.005,
        decimals: 3,
      },
      {
        key: "minComponentArea",
        label: "Minimum component area",
        description: "Connected components smaller than this are discarded as speckle noise.",
        min: 10,
        max: 500,
        step: 5,
        decimals: 0,
        unit: "px²",
      },
    ],
  },
  {
    name: "Signature Matching",
    description: "Governs how a session's crops are compared once it's processed.",
    fields: [
      {
        key: "similarityThreshold",
        label: "Similarity flag threshold",
        description: "Comparisons scoring below this are flagged for review.",
        min: 0.1,
        max: 0.95,
        step: 0.05,
        decimals: 2,
      },
      {
        key: "orbNfeatures",
        label: "ORB feature count",
        min: 100,
        max: 2000,
        step: 50,
        decimals: 0,
      },
      { key: "minKeypoints", label: "Minimum keypoints", min: 5, max: 50, step: 1, decimals: 0 },
    ],
  },
];

function formatValue(field: SettingField, value: number): string {
  return `${value.toFixed(field.decimals)}${field.unit ?? ""}`;
}

function SettingsGroupCard({
  group,
  settings,
  onFieldChange,
  onReset,
}: {
  group: SettingGroup;
  settings: ProcessingSettings;
  onFieldChange: (key: keyof ProcessingSettings, value: number) => void;
  onReset: () => void;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setExpanded((prev) => !prev)}
        role="button"
        aria-expanded={expanded}
      >
        <div className="flex items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">{group.name}</CardTitle>
            <CardDescription>{group.description}</CardDescription>
          </div>
          <ChevronDown
            className={cn(
              "size-4 shrink-0 text-muted-foreground transition-transform",
              expanded && "rotate-180",
            )}
            aria-hidden
          />
        </div>
      </CardHeader>
      {expanded ? (
        <CardContent className="space-y-6">
          {group.fields.map((field) => (
            <div key={field.key} className="space-y-2">
              <div className="flex items-baseline justify-between gap-4">
                <Label htmlFor={field.key}>{field.label}</Label>
                <span className="text-num shrink-0 text-sm">
                  {formatValue(field, settings[field.key])}
                </span>
              </div>
              <Slider
                id={field.key}
                min={field.min}
                max={field.max}
                step={field.step}
                value={[settings[field.key]]}
                onValueChange={([value]) => onFieldChange(field.key, value ?? settings[field.key])}
              />
              {field.description ? (
                <p className="text-xs text-muted-foreground">{field.description}</p>
              ) : null}
            </div>
          ))}
          <Button variant="outline" size="sm" onClick={onReset}>
            Reset to defaults
          </Button>
        </CardContent>
      ) : null}
    </Card>
  );
}

export function SettingsPage() {
  const [settings, setSettings] = useState<ProcessingSettings>(PROCESSING_SETTINGS_DEFAULTS);

  useEffect(() => {
    // Reads browser-only persisted settings once mounted; the literal
    // initial state above is what both the server and the client's first
    // render use, so this can't run any earlier without touching `window`
    // during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSettings(loadProcessingSettings());
  }, []);

  const updateField = (key: keyof ProcessingSettings, value: number) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const resetGroup = (group: SettingGroup) => {
    setSettings((prev) => {
      const next = { ...prev };
      for (const field of group.fields) {
        next[field.key] = PROCESSING_SETTINGS_DEFAULTS[field.key];
      }
      return next;
    });
  };

  const save = () => {
    saveProcessingSettings(settings);
    toast.success("Settings saved", { description: "Applied to the next processing run." });
  };

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        title="Settings"
        description="Operator-side configuration for the CV pipeline's per-stage parameters."
        actions={<Button onClick={save}>Save settings</Button>}
      />

      {SETTING_GROUPS.map((group) => (
        <SettingsGroupCard
          key={group.name}
          group={group}
          settings={settings}
          onFieldChange={updateField}
          onReset={() => resetGroup(group)}
        />
      ))}
    </div>
  );
}

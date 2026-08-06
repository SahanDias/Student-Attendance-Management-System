"use client";

import { FileCode2, FileImage, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { loadProcessingSettings, toProcessOptionsPayload } from "@/lib/processing-settings";
import { startProcessing, uploadSheet } from "@/services/sessions.service";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function DropZone({
  label,
  hint,
  accept,
  file,
  onFile,
  icon: Icon,
}: {
  label: string;
  hint: string;
  accept: string;
  file: File | null;
  onFile: (f: File | null) => void;
  icon: typeof FileImage;
}) {
  const [over, setOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const dropped = e.dataTransfer.files[0];
        if (dropped) onFile(dropped);
      }}
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-dashed p-4 transition-colors",
        over ? "border-primary bg-accent/60" : "border-border bg-card",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <Icon className="size-4 text-muted-foreground" aria-hidden />
      </div>

      {file ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-background p-2.5">
          <div className="flex h-16 w-14 items-center justify-center rounded border border-border bg-muted">
            <FileCode2 className="size-5 text-muted-foreground" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-num truncate text-xs font-medium text-foreground">{file.name}</p>
            <p className="text-num text-xs text-muted-foreground">{formatBytes(file.size)}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onFile(null)}
            aria-label={`Remove ${file.name}`}
          >
            <X className="size-4" />
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex flex-col items-center gap-2 rounded-md border border-border bg-muted/40 px-4 py-7 text-center transition-colors hover:bg-accent/50"
        >
          <UploadCloud className="size-5 text-muted-foreground" aria-hidden />
          <span className="text-xs text-muted-foreground">
            Drag &amp; drop or <span className="font-medium text-primary">browse</span>
          </span>
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

type Phase = "idle" | "processing" | "failed";

export function UploadPage() {
  const [image, setImage] = useState<File | null>(null);
  const [xml, setXml] = useState<File | null>(null);
  const [subject, setSubject] = useState("CS 202");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [headerRows, setHeaderRows] = useState(() => loadProcessingSettings().headerRows);
  const [signatureCol, setSignatureCol] = useState("-1");

  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    if (!image || !xml) return;
    setPhase("processing");
    setError(null);
    try {
      const { session_id } = await uploadSheet(image, xml, subject, date);
      await startProcessing(session_id, {
        ...toProcessOptionsPayload(loadProcessingSettings()),
        header_rows: headerRows,
        signature_col: Number(signatureCol),
      });
    } catch (e) {
      setError((e as Error).message);
      setPhase("failed");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Upload sheet"
        description="Send a photographed signing sheet and its info.xml roster through the OpenCV presence-detection pipeline."
      />

      <div className="space-y-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <DropZone
            label="Sheet image"
            hint="JPG or PNG photograph of the signed sheet"
            accept="image/jpeg,image/png"
            file={image}
            onFile={setImage}
            icon={FileImage}
          />
          <DropZone
            label="info.xml"
            hint="Roster metadata exported for this session"
            accept=".xml,text/xml,application/xml"
            file={xml}
            onFile={setXml}
            icon={FileCode2}
          />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Processing settings</CardTitle>
            <CardDescription>
              Optional — defaults match the standard department sheet layout.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="subject">Subject code</Label>
              <Input
                id="subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="text-num"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="date">Session date</Label>
              <Input
                id="date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="text-num"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="headers">Header rows</Label>
              <Input
                id="headers"
                type="number"
                min={0}
                max={5}
                value={headerRows}
                onChange={(e) => setHeaderRows(Number(e.target.value))}
                className="text-num"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sigcol">Signature column</Label>
              <Select value={signatureCol} onValueChange={setSignatureCol}>
                <SelectTrigger id="sigcol">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="-1">Last column (default)</SelectItem>
                  <SelectItem value="1">Column 1</SelectItem>
                  <SelectItem value="2">Column 2</SelectItem>
                  <SelectItem value="3">Column 3</SelectItem>
                  <SelectItem value="4">Column 4</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={start} disabled={!image || !xml}>
            Start processing
          </Button>
          {!image || !xml ? (
            <p className="text-xs text-muted-foreground">
              Both the sheet image and info.xml are required.
            </p>
          ) : null}
        </div>

        {phase === "failed" && error ? (
          <p role="alert" className="text-num text-xs text-absent">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
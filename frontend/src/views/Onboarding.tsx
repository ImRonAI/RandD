import Papa from "papaparse";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/auth/AuthContext";

type ImportIssue = {
  type: string;
  severity: string;
  source: string;
  row: number | null;
  propertyCode: string | null;
  message: string;
};

type ImportResult = {
  kind: string;
  rowsParsed: number;
  propertiesUpserted?: number;
  tasksCreated?: number;
  errors: number;
  warnings: number;
  issues: ImportIssue[];
};

type Kind = "roster" | "master";

type Preview = {
  kind: Kind;
  file: File;
  headers: string[];
  rows: string[][];
  totalRows: number;
  parseErrors: string[];
};

export const Onboarding = ({ onClose }: { onClose: () => void }) => {
  const { user } = useAuth();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  // Platform admin must name a target tenant; tenant users import into their own.
  const [targetTenantId, setTargetTenantId] = useState<string>("");

  const onPick = (kind: Kind) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setResult(null);
    Papa.parse<string[]>(file, {
      skipEmptyLines: true,
      complete: (parsed) => {
        const rows = parsed.data as unknown as string[][];
        const headers = rows[0] ?? [];
        const body = rows.slice(1);
        setPreview({
          kind,
          file,
          headers,
          rows: body.slice(0, 20),
          totalRows: body.length,
          parseErrors: parsed.errors.map((x) => `row ${x.row}: ${x.message}`),
        });
      },
    });
    e.target.value = "";
  };

  const confirmUpload = async () => {
    if (!preview) return;
    setBusy(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", preview.file);
      const q =
        user?.is_platform_admin && targetTenantId
          ? `?tenant_id=${encodeURIComponent(targetTenantId)}`
          : "";
      const res = await fetch(`/api/import/${preview.kind}${q}`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      const data = (await res.json()) as ImportResult & { detail?: string };
      if (!res.ok) {
        setResult({
          kind: preview.kind,
          rowsParsed: preview.totalRows,
          errors: 1,
          warnings: 0,
          issues: [
            {
              type: "request_failed",
              severity: "ERROR",
              source: preview.kind,
              row: null,
              propertyCode: null,
              message: data.detail ?? `Upload failed (${res.status}).`,
            },
          ],
        });
      } else {
        setResult(data);
      }
    } catch {
      setResult({
        kind: preview.kind,
        rowsParsed: preview.totalRows,
        errors: 1,
        warnings: 0,
        issues: [
          {
            type: "network_error",
            severity: "ERROR",
            source: preview.kind,
            row: null,
            propertyCode: null,
            message: "Could not reach the server.",
          },
        ],
      });
    } finally {
      setBusy(false);
      setPreview(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl p-4">
      <Card>
        <CardHeader>
          <CardTitle className="font-serif text-xl">Tenant Onboarding</CardTitle>
          <CardDescription>
            Upload an Address Roster and a Master Checklist CSV to load a tenant's data.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {user?.is_platform_admin && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="targetTenant">Target tenant id</Label>
              <input
                className="h-9 w-40 rounded-md border bg-transparent px-3 text-sm"
                id="targetTenant"
                onChange={(e) => setTargetTenantId(e.target.value)}
                placeholder="e.g. 2"
                type="number"
                value={targetTenantId}
              />
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label>Address Roster CSV</Label>
              <input accept=".csv" onChange={onPick("roster")} type="file" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>Master Checklist CSV</Label>
              <input accept=".csv" onChange={onPick("master")} type="file" />
            </div>
          </div>

          {result && (
            <div className="rounded-md border p-3 text-sm">
              <p className="font-medium">
                {result.kind} import — {result.rowsParsed} rows parsed
                {typeof result.propertiesUpserted === "number"
                  ? `, ${result.propertiesUpserted} properties`
                  : ""}
                {typeof result.tasksCreated === "number"
                  ? `, ${result.tasksCreated} tasks`
                  : ""}
                . {result.errors} errors, {result.warnings} warnings.
              </p>
              {result.issues.length > 0 && (
                <ul className="mt-2 max-h-56 list-disc overflow-auto pl-5">
                  {result.issues.map((issue, i) => (
                    <li
                      className={
                        issue.severity === "ERROR" ? "text-destructive" : "text-muted-foreground"
                      }
                      key={i}
                    >
                      [{issue.severity}] {issue.type}
                      {issue.row ? ` row ${issue.row}` : ""}
                      {issue.propertyCode ? ` (${issue.propertyCode})` : ""}: {issue.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="flex justify-end">
            <Button onClick={onClose} variant="ghost">
              Close
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog onOpenChange={(open) => !open && setPreview(null)} open={!!preview}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Preview {preview?.kind} CSV</DialogTitle>
            <DialogDescription>
              {preview?.totalRows} data rows. Showing the first {preview?.rows.length}.
            </DialogDescription>
          </DialogHeader>
          {preview && (
            <div className="max-h-72 overflow-auto rounded-md border">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-muted">
                  <tr>
                    {preview.headers.map((h, i) => (
                      <th className="px-2 py-1 font-medium" key={i}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, ri) => (
                    <tr className="border-t" key={ri}>
                      {row.map((cell, ci) => (
                        <td className="px-2 py-1" key={ci}>
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {preview && preview.parseErrors.length > 0 && (
            <p className="text-destructive text-xs">
              Parse issues: {preview.parseErrors.slice(0, 5).join("; ")}
            </p>
          )}
          <DialogFooter>
            <Button onClick={() => setPreview(null)} variant="ghost">
              Cancel
            </Button>
            <Button disabled={busy} onClick={confirmUpload}>
              {busy ? "Uploading…" : "Confirm import"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

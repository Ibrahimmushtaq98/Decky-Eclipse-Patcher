import { useState } from "react";
import { ButtonItem, PanelSectionRow } from "@decky/ui";
import { PatchDetails as PatchDetailsType, getPatchDetails, logError } from "../api";

const stateColor: Record<string, string> = {
  intact: "#22c55e",
  modified: "#f97316",
  missing: "#ef4444",
  unknown: "#9ca3af",
};

const mono: React.CSSProperties = {
  fontSize: "11px",
  fontFamily: "monospace",
  overflowWrap: "anywhere",
};

export function PatchDetails({ appid }: { appid: string }) {
  const [details, setDetails] = useState<PatchDetailsType | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setLoading(true);
    try {
      const result = await getPatchDetails(appid);
      if (result.status !== "success") throw new Error(result.message || "Failed to load details.");
      setDetails(result);
      setOpen(true);
    } catch (err) {
      logError(`patchDetails: ${String(err)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={toggle} disabled={loading}>
          {loading ? "Loading…" : open ? "Hide patch details" : "Show patch details"}
        </ButtonItem>
      </PanelSectionRow>
      {open && details ? (
        <PanelSectionRow>
          <div
            style={{
              padding: "8px",
              borderRadius: "8px",
              backgroundColor: "rgba(0,0,0,0.25)",
              fontSize: "12px",
              lineHeight: "1.5",
            }}
          >
            <div style={mono}>mod: {details.mod_zip_name}</div>
            <div style={mono}>sha256: {(details.mod_zip_sha256 ?? "").slice(0, 16)}…</div>
            <div style={mono}>applied: {details.applied_at}</div>
            <div style={mono}>target: {details.install_root}</div>
            {details.zip_root_prefix ? (
              <div style={mono}>archive root: {details.zip_root_prefix}</div>
            ) : null}
            {details.proxy_dlls && details.proxy_dlls.length ? (
              <div style={mono}>proxy: {details.proxy_dlls.join(", ")}</div>
            ) : null}
            {details.managed_launch_options ? (
              <div style={mono}>launch opts: {details.managed_launch_options}</div>
            ) : null}
            <div style={{ ...mono, marginTop: "6px" }}>
              files: {details.counts?.intact ?? 0} intact / {details.counts?.modified ?? 0} modified /{" "}
              {details.counts?.missing ?? 0} missing
            </div>
            <div style={{ maxHeight: "180px", overflowY: "auto", marginTop: "6px" }}>
              {(details.files ?? []).map((f) => (
                <div key={f.relpath} style={mono}>
                  <span style={{ color: stateColor[f.state] ?? "#fff" }}>●</span>{" "}
                  {f.action === "overwrite" ? "[ovr]" : "[new]"} {f.relpath}
                  {f.action === "overwrite" && !f.backup_present ? " (backup missing!)" : ""}
                </div>
              ))}
              {details.files_truncated ? (
                <div style={mono}>… and {details.files_truncated} more</div>
              ) : null}
            </div>
          </div>
        </PanelSectionRow>
      ) : null}
    </>
  );
}

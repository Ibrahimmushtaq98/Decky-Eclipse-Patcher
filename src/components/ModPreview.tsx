import { PanelSectionRow } from "@decky/ui";
import { ScanResult } from "../api";

const box: React.CSSProperties = {
  padding: "10px",
  borderRadius: "8px",
  fontSize: "13px",
  lineHeight: "1.45",
  backgroundColor: "rgba(255,255,255,0.06)",
};

function formatSize(bytes: number): string {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  if (bytes > 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${bytes} B`;
}

export function ModPreview({ scan }: { scan: ScanResult }) {
  return (
    <PanelSectionRow>
      <div style={box}>
        <div style={{ fontWeight: "bold", marginBottom: "4px" }}>{scan.zip_name}</div>
        <div>
          {scan.files?.length ?? 0} files ({formatSize(scan.total_uncompressed ?? 0)}) —{" "}
          <span style={{ color: "#f97316" }}>{scan.overwrite_count} overwrite</span>,{" "}
          <span style={{ color: "#22c55e" }}>{scan.new_count} new</span>
        </div>
        {scan.zip_root_prefix ? <div>Mod root folder: {scan.zip_root_prefix}</div> : null}
        {scan.proxy_dlls && scan.proxy_dlls.length > 0 ? (
          <div>
            Proxy DLL detected: {scan.proxy_dlls.join(", ")} — launch options will be set
            automatically.
          </div>
        ) : null}
        {(scan.warnings ?? []).map((w, i) => (
          <div key={i} style={{ color: "#f97316", marginTop: "4px" }}>
            ⚠ {w}
          </div>
        ))}
      </div>
    </PanelSectionRow>
  );
}

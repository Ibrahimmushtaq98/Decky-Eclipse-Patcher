import { PanelSectionRow } from "@decky/ui";
import { ModStatus } from "../api";

const box: React.CSSProperties = {
  padding: "10px",
  borderRadius: "8px",
  fontSize: "13px",
  lineHeight: "1.45",
  backgroundColor: "rgba(255,255,255,0.06)",
};

const stateInfo: Record<string, { label: string; color: string }> = {
  intact: { label: "Mod installed", color: "#22c55e" },
  modified: { label: "Mod installed — files changed (game update?)", color: "#f97316" },
  incomplete: { label: "Interrupted install — remove to roll back", color: "#ef4444" },
};

export function StatusCard({ modStatus }: { modStatus: ModStatus }) {
  const info = stateInfo[modStatus.state] ?? { label: modStatus.state, color: "#ffffff" };
  return (
    <PanelSectionRow>
      <div style={box}>
        <div style={{ color: info.color, fontWeight: "bold" }}>{info.label}</div>
        {modStatus.mod_zip_name ? <div>Mod: {modStatus.mod_zip_name}</div> : null}
        {modStatus.applied_at ? (
          <div>Applied: {new Date(modStatus.applied_at).toLocaleString()}</div>
        ) : null}
        {modStatus.state === "modified" ? (
          <div>
            {modStatus.files_intact}/{modStatus.file_count} mod files intact,{" "}
            {(modStatus.files_modified ?? 0) + (modStatus.files_missing ?? 0)} changed/missing.
          </div>
        ) : null}
        {modStatus.proxy_dll ? <div>Proxy DLL: {modStatus.proxy_dll}</div> : null}
      </div>
    </PanelSectionRow>
  );
}

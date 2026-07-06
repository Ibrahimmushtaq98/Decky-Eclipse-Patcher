import { useState } from "react";
import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { getActivityLog, logError } from "../api";

export function ActivityLog() {
  const [lines, setLines] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (lines !== null) {
      setLines(null);
      return;
    }
    setLoading(true);
    try {
      const result = await getActivityLog(80);
      setLines(result.lines ?? []);
    } catch (err) {
      logError(`activityLog: ${String(err)}`);
      setLines([`Failed to load log: ${String(err)}`]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <PanelSection title="Activity Log">
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={toggle} disabled={loading}>
          {loading ? "Loading…" : lines !== null ? "Hide log" : "Show log"}
        </ButtonItem>
      </PanelSectionRow>
      {lines !== null ? (
        <PanelSectionRow>
          <div
            style={{
              maxHeight: "220px",
              overflowY: "auto",
              padding: "8px",
              borderRadius: "8px",
              backgroundColor: "rgba(0,0,0,0.25)",
            }}
          >
            {lines.length ? (
              lines.map((line, i) => (
                <div
                  key={i}
                  style={{
                    fontSize: "11px",
                    fontFamily: "monospace",
                    overflowWrap: "anywhere",
                    color: line.includes("ERROR") ? "#ef4444" : "#d1d5db",
                    marginBottom: "3px",
                  }}
                >
                  {line}
                </div>
              ))
            ) : (
              <div style={{ fontSize: "12px", color: "#9ca3af" }}>No activity yet.</div>
            )}
          </div>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}

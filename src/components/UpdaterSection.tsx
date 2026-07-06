import { useState } from "react";
import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { UpdateCheck, checkForUpdate, logError, selfUpdate } from "../api";

export function UpdaterSection() {
  const [check, setCheck] = useState<UpdateCheck | null>(null);
  const [busy, setBusy] = useState<"check" | "update" | null>(null);
  const [message, setMessage] = useState<string>("");

  const doCheck = async () => {
    setBusy("check");
    setMessage("");
    try {
      const result = await checkForUpdate();
      if (result.status !== "success") throw new Error(result.message || "Check failed.");
      setCheck(result);
      if (!result.update_available) {
        setMessage(`Up to date (v${result.installed_version}).`);
      }
    } catch (err) {
      logError(`checkForUpdate: ${String(err)}`);
      setMessage(`Error: ${String(err)}`);
    } finally {
      setBusy(null);
    }
  };

  const doUpdate = async () => {
    setBusy("update");
    setMessage("");
    try {
      const result = await selfUpdate();
      if (result.status !== "success") throw new Error(result.message || "Update failed.");
      setMessage(result.message || "Updated.");
      toaster.toast({ title: "Eclipse Patcher", body: result.message || "Updated." });
      setCheck(null);
    } catch (err) {
      logError(`selfUpdate: ${String(err)}`);
      setMessage(`Error: ${String(err)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <PanelSection title="Plugin Update">
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={doCheck} disabled={busy !== null}>
          {busy === "check" ? "Checking…" : "Check for updates"}
        </ButtonItem>
      </PanelSectionRow>
      {check?.update_available ? (
        <>
          <PanelSectionRow>
            <div style={{ fontSize: "13px" }}>
              <span style={{ color: "#22c55e", fontWeight: "bold" }}>
                {check.latest_tag} available
              </span>{" "}
              (installed: v{check.installed_version})
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={doUpdate} disabled={busy !== null}>
              {busy === "update" ? "Downloading & installing…" : `Update to ${check.latest_tag}`}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : null}
      {message ? (
        <PanelSectionRow>
          <div
            style={{
              fontSize: "12px",
              whiteSpace: "pre-wrap",
              color: message.startsWith("Error") ? "#ef4444" : "#9ca3af",
            }}
          >
            {message}
          </div>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}

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

  const tryDeckyInstaller = async (): Promise<boolean> => {
    if (!check?.zip_url) return false;
    const loader = (window as unknown as { DeckyPluginLoader?: any }).DeckyPluginLoader;
    const version = (check.latest_tag || "").replace(/^v/, "");
    try {
      if (typeof loader?.installPlugin === "function") {
        await loader.installPlugin(check.zip_url, "Eclipse Patcher", version, check.sha256 || undefined);
        return true;
      }
      if (typeof loader?.callServerMethod === "function") {
        await loader.callServerMethod("install_plugin", {
          artifact: check.zip_url,
          name: "Eclipse Patcher",
          version,
          hash: check.sha256 || false,
        });
        return true;
      }
    } catch (err) {
      logError(`deckyInstaller: ${String(err)}`);
    }
    return false;
  };

  const waitForInstall = async (expectedTag: string, seconds: number): Promise<boolean> => {
    for (let i = 0; i < seconds / 3; i++) {
      await new Promise((resolve) => setTimeout(resolve, 3000));
      try {
        const status = await checkForUpdate();
        if (status.status === "success" && !status.update_available) return true;
      } catch {
        // backend restarting mid-update also means progress; keep waiting
      }
    }
    return false;
  };

  const doUpdate = async () => {
    setBusy("update");
    setMessage("");
    const expectedTag = check?.latest_tag || "";
    try {
      // Preferred: Decky's own installer (runs as root, handles permissions & reload).
      if (await tryDeckyInstaller()) {
        setMessage("Waiting for the Decky installer… confirm the prompt if one appears.");
        if (await waitForInstall(expectedTag, 21)) {
          setMessage(`Updated to ${expectedTag}. Reload the plugin (or restart Steam) to finish.`);
          toaster.toast({ title: "Eclipse Patcher", body: `Updated to ${expectedTag}.` });
          setCheck(null);
          return;
        }
        setMessage("Decky installer didn't complete — installing directly instead…");
      }
      // Fallback: in-place file copy (backend runs as root, so this always works).
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

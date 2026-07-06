import { useCallback, useEffect, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  showModal,
} from "@decky/ui";
import { openFilePicker, FileSelectionType, toaster } from "@decky/api";
import {
  GameEntry,
  ModStatus,
  ScanResult,
  applyMod,
  getGameModStatus,
  getPathDefaults,
  listInstalledGames,
  logError,
  reapplyMod,
  removeMod,
  scanModZip,
} from "../api";
import { getAppLaunchOptions, setAppLaunchOptions } from "../steamClient";
import { ModPreview } from "./ModPreview";
import { PatchDetails } from "./PatchDetails";
import { StatusCard } from "./StatusCard";

let lastSelectedAppId = "";

export function EclipsePanel() {
  const [games, setGames] = useState<GameEntry[]>([]);
  const [selectedAppId, setSelectedAppId] = useState<string>(() => lastSelectedAppId);
  const [modStatus, setModStatus] = useState<ModStatus | null>(null);
  const [zipPath, setZipPath] = useState<string>("");
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [result, setResult] = useState<string>("");

  const toast = (body: string) => toaster.toast({ title: "Eclipse Patcher", body });

  const loadGames = useCallback(async () => {
    try {
      const response = await listInstalledGames();
      if (response.status !== "success" || !response.games) {
        throw new Error(response.message || "Failed to list games.");
      }
      setGames(response.games);
      setSelectedAppId((current) => {
        const valid = current && response.games!.some((g) => g.appid === current);
        const next = valid ? current : response.games!.length ? response.games![0].appid : "";
        lastSelectedAppId = next;
        return next;
      });
    } catch (err) {
      logError(`loadGames: ${String(err)}`);
      toast(String(err));
    }
  }, []);

  const loadStatus = useCallback(async (appid: string) => {
    if (!appid) {
      setModStatus(null);
      return;
    }
    try {
      const status = await getGameModStatus(appid);
      setModStatus(status);
    } catch (err) {
      logError(`loadStatus: ${String(err)}`);
      setModStatus(null);
    }
  }, []);

  useEffect(() => {
    loadGames();
  }, [loadGames]);

  useEffect(() => {
    setScan(null);
    setZipPath("");
    setResult("");
    loadStatus(selectedAppId);
  }, [selectedAppId, loadStatus]);

  const pickZip = async () => {
    try {
      const defaults = await getPathDefaults();
      const start = defaults.downloads || defaults.home || "/home/deck";
      const file = await openFilePicker(FileSelectionType.FILE, start, true, true, undefined, [
        "zip",
        "rar",
        "7z",
      ]);
      if (!file?.realpath && !file?.path) return;
      const path = file.realpath || file.path;
      setZipPath(path);
      setScan(null);
      setResult("");
      const scanned = await scanModZip(selectedAppId, path);
      if (scanned.status !== "success") {
        setResult(`Error: ${scanned.message}`);
        return;
      }
      setScan(scanned);
    } catch (err) {
      // file picker cancel rejects the promise; ignore silently
      if (String(err).toLowerCase().includes("cancel")) return;
      logError(`pickZip: ${String(err)}`);
      setResult(`Error: ${String(err)}`);
    }
  };

  const doApply = () => {
    if (!scan || !selectedAppId) return;
    const game = games.find((g) => g.appid === selectedAppId);
    showModal(
      <ConfirmModal
        strTitle={`Apply ${scan.zip_name} to ${game?.name ?? "game"}?`}
        strDescription={
          `${scan.overwrite_count} file(s) will be backed up and overwritten, ` +
          `${scan.new_count} new file(s) added.` +
          (scan.proxy_dll ? ` Launch options will be set for ${scan.proxy_dll}.` : "") +
          " You can fully revert with Remove Mod."
        }
        strOKButtonText="Apply Mod"
        strCancelButtonText="Cancel"
        onOK={async () => {
          setBusy(true);
          try {
            const current = await getAppLaunchOptions(Number(selectedAppId));
            const res = await applyMod(selectedAppId, zipPath, current);
            if (res.status !== "success") throw new Error(res.message || "Apply failed.");
            if (res.launch_options) {
              setAppLaunchOptions(Number(selectedAppId), res.launch_options);
            }
            setResult(res.message || "Mod applied.");
            toast(res.message || "Mod applied.");
            setScan(null);
            setZipPath("");
            await loadStatus(selectedAppId);
            await loadGames();
          } catch (err) {
            logError(`apply: ${String(err)}`);
            setResult(`Error: ${String(err)}`);
            toast(String(err));
          } finally {
            setBusy(false);
          }
        }}
      />
    );
  };

  const doRemove = () => {
    if (!selectedAppId) return;
    const game = games.find((g) => g.appid === selectedAppId);
    showModal(
      <ConfirmModal
        strTitle={`Remove mod from ${game?.name ?? "game"}?`}
        strDescription="All backed-up files will be restored and files added by the mod deleted."
        strOKButtonText="Remove Mod"
        strCancelButtonText="Cancel"
        onOK={async () => {
          setBusy(true);
          try {
            const res = await removeMod(selectedAppId);
            if (res.status !== "success") throw new Error(res.message || "Remove failed.");
            setAppLaunchOptions(Number(selectedAppId), res.launch_options ?? "");
            setResult(res.message || "Mod removed.");
            toast(res.message || "Mod removed.");
            await loadStatus(selectedAppId);
            await loadGames();
          } catch (err) {
            logError(`remove: ${String(err)}`);
            setResult(`Error: ${String(err)}`);
            toast(String(err));
          } finally {
            setBusy(false);
          }
        }}
      />
    );
  };

  const doReapply = async () => {
    if (!selectedAppId) return;
    setBusy(true);
    try {
      const current = await getAppLaunchOptions(Number(selectedAppId));
      const res = await reapplyMod(selectedAppId, current);
      if (res.status !== "success") throw new Error(res.message || "Re-apply failed.");
      if (res.launch_options) setAppLaunchOptions(Number(selectedAppId), res.launch_options);
      setResult(res.message || "Mod re-applied.");
      toast(res.message || "Mod re-applied.");
      await loadStatus(selectedAppId);
    } catch (err) {
      logError(`reapply: ${String(err)}`);
      setResult(`Error: ${String(err)}`);
      toast(String(err));
    } finally {
      setBusy(false);
    }
  };

  const patched = modStatus?.patched === true;

  return (
    <PanelSection title="Eclipse Patcher">
      <PanelSectionRow>
        <DropdownItem
          label="Game"
          rgOptions={games.map((g) => ({
            data: g.appid,
            label: `${g.patched ? "✓ " : ""}${g.name}`,
          }))}
          selectedOption={selectedAppId}
          onChange={(option) => {
            lastSelectedAppId = String(option.data);
            setSelectedAppId(String(option.data));
          }}
          strDefaultLabel={games.length ? "Select a game" : "No games found"}
        />
      </PanelSectionRow>

      {selectedAppId && modStatus && patched ? <StatusCard modStatus={modStatus} /> : null}

      {selectedAppId && !patched ? (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={pickZip} disabled={busy}>
            {zipPath ? "Choose a different file…" : "Choose mod file (zip/rar/7z)…"}
          </ButtonItem>
        </PanelSectionRow>
      ) : null}

      {scan && !patched ? (
        <>
          <ModPreview scan={scan} />
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={doApply} disabled={busy}>
              {busy ? "Applying…" : "Apply Mod"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : null}

      {patched ? (
        <>
          <PatchDetails appid={selectedAppId} />
          {modStatus?.state === "modified" && modStatus?.has_managed_zip ? (
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={doReapply} disabled={busy}>
                {busy ? "Working…" : "Re-apply Mod (after game update)"}
              </ButtonItem>
            </PanelSectionRow>
          ) : null}
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={doRemove} disabled={busy}>
              {busy ? "Working…" : "Remove Mod"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      ) : null}

      {result ? (
        <PanelSectionRow>
          <div
            style={{
              fontSize: "13px",
              whiteSpace: "pre-wrap",
              color: result.startsWith("Error") ? "#ef4444" : "#22c55e",
            }}
          >
            {result}
          </div>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
}

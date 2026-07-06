import { callable } from "@decky/api";

export type GameEntry = {
  appid: string;
  name: string;
  install_found: boolean;
  patched: boolean;
};

export type ScanFileEntry = {
  relpath: string;
  zip_path: string;
  action: "overwrite" | "new";
  size: number;
};

export type ScanResult = {
  status: string;
  message?: string;
  zip_name?: string;
  zip_root_prefix?: string;
  files?: ScanFileEntry[];
  overwrite_count?: number;
  new_count?: number;
  created_dirs?: string[];
  ignored?: string[];
  proxy_dlls?: string[];
  proxy_dll?: string | null;
  total_uncompressed?: number;
  warnings?: string[];
  managed_launch_options?: string;
};

export type ModStatus = {
  status: string;
  message?: string;
  appid?: string;
  name?: string;
  patched: boolean;
  state: "none" | "intact" | "modified" | "incomplete";
  mod_zip_name?: string;
  applied_at?: string;
  proxy_dll?: string | null;
  proxy_dlls?: string[];
  managed_launch_options?: string;
  original_launch_options?: string;
  files_intact?: number;
  files_modified?: number;
  files_missing?: number;
  file_count?: number;
  has_managed_zip?: boolean;
};

export type ActionResult = {
  status: string;
  message?: string;
  appid?: string;
  name?: string;
  mod_zip_name?: string;
  overwrite_count?: number;
  new_count?: number;
  proxy_dll?: string | null;
  launch_options?: string;
  restored?: number;
  deleted?: number;
  missing_backups?: string[];
};

export const listInstalledGames = callable<[], { status: string; message?: string; games?: GameEntry[] }>(
  "list_installed_games"
);
export const getGameModStatus = callable<[appid: string], ModStatus>("get_game_mod_status");
export const scanModZip = callable<[appid: string, zip_path: string], ScanResult>("scan_mod_zip");
export const applyMod = callable<[appid: string, zip_path: string, current_launch_options: string], ActionResult>(
  "apply_mod"
);
export const removeMod = callable<[appid: string], ActionResult>("remove_mod");
export const reapplyMod = callable<[appid: string, current_launch_options: string], ActionResult>("reapply_mod");
export const getPathDefaults = callable<[], { status: string; home?: string; downloads?: string }>(
  "get_path_defaults"
);

export type PatchFileDetail = {
  relpath: string;
  action: "overwrite" | "new";
  state: "intact" | "modified" | "missing" | "unknown";
  backup_present: boolean;
};

export type PatchDetails = {
  status: string;
  message?: string;
  appid?: string;
  name?: string | null;
  patched: boolean;
  state?: string;
  mod_zip_name?: string;
  mod_zip_sha256?: string;
  applied_at?: string;
  install_root?: string;
  zip_root_prefix?: string;
  proxy_dlls?: string[];
  original_launch_options?: string;
  managed_launch_options?: string;
  created_dirs?: string[];
  managed_zip?: string | null;
  counts?: { intact: number; modified: number; missing: number; unknown: number };
  files?: PatchFileDetail[];
  files_truncated?: number;
};

export const getPatchDetails = callable<[appid: string], PatchDetails>("get_patch_details");
export const logError = callable<[error: string], void>("log_error");

export type UpdateCheck = {
  status: string;
  message?: string;
  installed_version?: string;
  latest_tag?: string;
  latest_title?: string;
  published_at?: string;
  zip_size?: number;
  notes?: string;
  update_available?: boolean;
};

export const checkForUpdate = callable<[], UpdateCheck>("check_for_update");
export const selfUpdate = callable<[], { status: string; message?: string; updated?: boolean }>(
  "self_update"
);

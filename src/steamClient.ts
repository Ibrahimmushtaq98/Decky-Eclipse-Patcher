// Minimal SteamClient wrappers (globals injected by the Steam UI).

declare const SteamClient: any;

export const getAppLaunchOptions = (appId: number): Promise<string> =>
  new Promise((resolve) => {
    try {
      if (typeof SteamClient === "undefined" || !SteamClient?.Apps?.RegisterForAppDetails) {
        resolve("");
        return;
      }
      let settled = false;
      let unregister = () => {};
      const timeout = window.setTimeout(() => {
        if (!settled) {
          settled = true;
          unregister();
          resolve("");
        }
      }, 5000);
      const registration = SteamClient.Apps.RegisterForAppDetails(
        appId,
        (details: { strLaunchOptions?: string }) => {
          if (settled) return;
          settled = true;
          window.clearTimeout(timeout);
          unregister();
          resolve(details?.strLaunchOptions ?? "");
        }
      );
      unregister = registration.unregister;
    } catch {
      resolve("");
    }
  });

export const setAppLaunchOptions = (appId: number, options: string): void => {
  try {
    if (typeof SteamClient !== "undefined" && SteamClient?.Apps?.SetAppLaunchOptions) {
      SteamClient.Apps.SetAppLaunchOptions(appId, options);
    }
  } catch {
    // non-fatal: user can set launch options manually
  }
};

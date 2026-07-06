import { definePlugin } from "@decky/api";
import { GiEclipse } from "react-icons/gi";
import { EclipsePanel } from "./components/EclipsePanel";
import { UpdaterSection } from "./components/UpdaterSection";
import { ActivityLog } from "./components/ActivityLog";

export default definePlugin(() => ({
  name: "Eclipse Patcher",
  titleView: <div>Eclipse Patcher</div>,
  // Keep the panel mounted while overlays (file picker) are open, so state
  // updates from scans render immediately instead of after re-entering.
  alwaysRender: true,
  content: (
    <>
      <EclipsePanel />
      <ActivityLog />
      <UpdaterSection />
    </>
  ),
  icon: <GiEclipse />,
}));

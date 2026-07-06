import { definePlugin } from "@decky/api";
import { GiEclipse } from "react-icons/gi";
import { EclipsePanel } from "./components/EclipsePanel";
import { UpdaterSection } from "./components/UpdaterSection";
import { ActivityLog } from "./components/ActivityLog";

export default definePlugin(() => ({
  name: "Eclipse Patcher",
  titleView: <div>Eclipse Patcher</div>,
  content: (
    <>
      <EclipsePanel />
      <ActivityLog />
      <UpdaterSection />
    </>
  ),
  icon: <GiEclipse />,
}));

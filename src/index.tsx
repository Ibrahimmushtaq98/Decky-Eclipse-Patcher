import { definePlugin } from "@decky/api";
import { GiEclipse } from "react-icons/gi";
import { EclipsePanel } from "./components/EclipsePanel";

export default definePlugin(() => ({
  name: "Eclipse Patcher",
  titleView: <div>Eclipse Patcher</div>,
  content: <EclipsePanel />,
  icon: <GiEclipse />,
}));

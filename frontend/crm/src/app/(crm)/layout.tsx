import "./crm.css";
import Shell from "@/components/crm/Shell";

// Every CRM screen sits in the design's frame: sidebar, top bar, panel, pop-up form, messages.
export default function CrmLayout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}

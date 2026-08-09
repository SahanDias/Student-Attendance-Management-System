import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, PenLine, ScanLine, Settings, Users, Layers } from "lucide-react";

<SidebarHeader className="border-b border-sidebar-border">
  <div className="flex items-center gap-2.5 px-1 py-1.5">
    <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-sidebar-primary text-sidebar-primary-foreground">
      <ScanLine className="size-4" aria-hidden />
    </div>
    {!collapsed && (
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-sidebar-foreground">SAMS</p>
        <p className="text-num truncate text-[11px] text-muted-foreground">
          Signing sheet analyser
        </p>
      </div>
    )}
  </div>
</SidebarHeader>;

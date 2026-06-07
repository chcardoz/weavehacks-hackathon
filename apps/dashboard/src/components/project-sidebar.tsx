"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  ArrowLeft,
  Bot,
  Brain,
  LayoutDashboard,
  Settings,
  TriangleAlert,
} from "lucide-react"
import { NavUser } from "@/components/nav-user"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

export function ProjectSidebar({
  projectId,
  projectName,
  userEmail,
  ...props
}: React.ComponentProps<typeof Sidebar> & {
  projectId: string
  projectName: string
  userEmail: string
}) {
  const pathname = usePathname()
  const base = `/projects/${projectId}`

  const nav = [
    { title: "Overview", href: base, icon: LayoutDashboard, exact: true },
    {
      title: "Incidents",
      href: `${base}/incidents`,
      icon: TriangleAlert,
      exact: false,
    },
    { title: "Agents", href: `${base}/agents`, icon: Bot, exact: false },
    { title: "Memory", href: `${base}/memory`, icon: Brain, exact: false },
    {
      title: "Settings",
      href: `${base}/settings`,
      icon: Settings,
      exact: false,
    },
  ]

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="All projects">
              <Link href="/projects">
                <ArrowLeft />
                <span>All projects</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="truncate">
            {projectName}
          </SidebarGroupLabel>
          <SidebarMenu>
            {nav.map((item) => (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  asChild
                  isActive={
                    item.exact
                      ? pathname === item.href
                      : pathname === item.href ||
                        pathname.startsWith(`${item.href}/`)
                  }
                  tooltip={item.title}
                >
                  <Link href={item.href}>
                    <item.icon />
                    <span>{item.title}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <NavUser email={userEmail} />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

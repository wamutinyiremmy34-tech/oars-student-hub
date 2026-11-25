/**
 * Role-specific navigation item definitions.
 *
 * Each role gets exactly the links relevant to its workflow.
 * The AppShell imports these and renders only the set that matches the current user's role.
 * This prevents navigation bleed: a Student never sees "Print queue" in their nav,
 * an Operator never sees "My resources", etc.
 *
 * Account is intentionally included in every role nav so it is always reachable
 * via the sidebar / mobile menu, not only via the header avatar.
 */

export interface NavItem {
  to: string;
  label: string;
}

export const STUDENT_NAV: NavItem[] = [
  { to: "/dashboard",     label: "Dashboard" },
  { to: "/resources",     label: "Resources" },
  { to: "/catalog",       label: "Courses" },
  { to: "/bookmarks",     label: "Saved" },
  { to: "/print",         label: "New print order" },
  { to: "/print/orders",  label: "My orders" },
  { to: "/notifications", label: "Notifications" },
  { to: "/account",       label: "Account" },
  { to: "/help",          label: "Help" },
];

export const PROVIDER_NAV: NavItem[] = [
  { to: "/provider/dashboard",      label: "Dashboard" },
  { to: "/provider/resources",      label: "My resources" },
  { to: "/provider/resources/new",  label: "Upload resource" },
  { to: "/moderation",              label: "Moderation" },
  { to: "/notifications",           label: "Notifications" },
  { to: "/account",                 label: "Account" },
  { to: "/help",                    label: "Help" },
];

export const OPERATOR_NAV: NavItem[] = [
  { to: "/operator/dashboard", label: "Dashboard" },
  { to: "/operator",           label: "Print queue" },
  { to: "/notifications",      label: "Notifications" },
  { to: "/account",            label: "Account" },
  { to: "/help",               label: "Help" },
];

export const ADMIN_NAV: NavItem[] = [
  { to: "/admin",         label: "Admin dashboard" },
  { to: "/moderation",    label: "Moderation" },
  { to: "/resources",     label: "Resources" },
  { to: "/notifications", label: "Notifications" },
  { to: "/account",       label: "Account" },
  { to: "/help",          label: "Help" },
];

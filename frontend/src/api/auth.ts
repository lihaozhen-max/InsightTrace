export type UserRole = "analyst" | "admin";

export interface CurrentUser {
  id: string;
  username: string;
  display_name: string;
  role: UserRole;
  status: "active" | "disabled";
  created_at: string;
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const response = await fetch("/api/me", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error("无法读取当前登录用户");
  }

  return (await response.json()) as CurrentUser;
}

export async function logout(): Promise<void> {
  const response = await fetch("/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error("退出登录失败");
  }
}

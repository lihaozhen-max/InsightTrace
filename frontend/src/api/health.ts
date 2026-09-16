export interface ComponentHealth {
  status: "ok" | "error";
  detail?: string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  service: string;
  environment: string;
  components: {
    database: ComponentHealth;
    storage: ComponentHealth;
  };
}

export async function getReadiness(): Promise<ReadinessResponse> {
  const response = await fetch("/health/ready", {
    headers: { Accept: "application/json" },
  });

  const body = (await response.json()) as ReadinessResponse;

  if (!response.ok) {
    throw new Error("服务尚未就绪");
  }

  return body;
}

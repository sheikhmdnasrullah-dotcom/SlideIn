/** Optional official LogSnag SDK bridge for non-personal operational events. */
const FORBIDDEN_TAGS = new Set(["email", "name", "ip", "visitor_id", "user_id", "company_domain"]);

export async function publishOperationalEvent({ token, project, channel, event, description = "", tags = {} }) {
  if (!token || !project || !channel || !event) {
    throw new Error("LogSnag requires token, project, channel, and event");
  }
  for (const key of Object.keys(tags)) {
    if (FORBIDDEN_TAGS.has(key.toLowerCase())) {
      throw new Error(`Personal/visitor tag is not allowed in operational events: ${key}`);
    }
  }
  const { LogSnag } = await import("logsnag");
  const client = new LogSnag({ token, project });
  await client.track({ channel, event, description, tags, notify: false });
  return { delivered: true, provider: "logsnag" };
}

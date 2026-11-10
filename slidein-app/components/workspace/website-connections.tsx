import { connectWebsite } from "@/app/(workspace)/settings/actions";
import { Surface } from "@/components/system/surface";
import { EmptyState } from "@/components/system/states";
import { client, workspacePath } from "@/lib/api/client";
import { API_BASE_URL, WORKSPACE_ID } from "@/lib/api/config";

interface Website {
  id: string;
  domain: string;
  status: string;
  provider: string;
  snippet_url: string;
}

interface WebsiteList {
  websites: Website[];
}

export async function WebsiteConnections() {
  let data: WebsiteList | null = null;
  try {
    data = await client.get<WebsiteList>(workspacePath("/websites", WORKSPACE_ID));
  } catch {
    // The existing Settings page remains usable when this optional module is off.
  }

  return (
    <div className="space-y-4">
      <Surface variant="raised" className="p-6">
        <form action={connectWebsite} className="grid gap-3 md:grid-cols-[1fr_180px_auto]">
          <label className="grid gap-1 text-sm">
            <span>Website domain</span>
            <input
              name="domain"
              required
              placeholder="https://client.example"
              className="rounded-md border border-rule bg-surface px-3 py-2"
            />
          </label>
          <label className="grid gap-1 text-sm">
            <span>Event pipeline</span>
            <select name="provider" defaultValue="native" className="rounded-md border border-rule bg-surface px-3 py-2">
              <option value="native">Slidein first-party</option>
              <option value="snowplow">Snowplow</option>
              <option value="rudderstack">RudderStack</option>
            </select>
          </label>
          <button type="submit" className="self-end rounded-md bg-accent px-4 py-2 text-sm font-medium text-white">
            Connect website
          </button>
        </form>
        <p className="mt-3 text-sm text-muted">
          This creates the connection and installation snippet. It does not modify your website remotely or collect email from anonymous visitors.
        </p>
      </Surface>

      {data && data.websites.length > 0 ? data.websites.map((website) => (
        <Surface key={website.id} variant="raised" className="space-y-3 p-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong>{website.domain}</strong>
            <span className="text-sm text-muted">{website.status} · {website.provider}</span>
          </div>
          <p className="text-sm">1. Add this script to the website:</p>
          <pre className="overflow-x-auto rounded-md bg-surface-2 p-3 text-xs"><code>{`<script async src="${API_BASE_URL.replace(/\/$/, "")}${website.snippet_url}"></script>`}</code></pre>
          <p className="text-sm">2. Mark the lead form and its explicit consent checkbox:</p>
          <pre className="overflow-x-auto rounded-md bg-surface-2 p-3 text-xs"><code>{`<form data-slidein-lead-capture>\n  <input type="email" name="email" required>\n  <label><input type="checkbox" data-slidein-consent required> I agree to be contacted.</label>\n  <button>Submit</button>\n</form>`}</code></pre>
          <p className="text-sm text-muted">Only an explicitly submitted email creates a lead. Consented prior session events then attach to the same prospect.</p>
        </Surface>
      )) : (
        <Surface variant="raised">
          <EmptyState
            icon="inbox"
            title={data ? "No websites connected" : "Website capture unavailable"}
            description={data ? "Connect a client-owned site to generate its consent-aware lead form integration." : "Check the API and website-capture module configuration."}
          />
        </Surface>
      )}
    </div>
  );
}

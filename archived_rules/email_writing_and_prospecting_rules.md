## 1. PRIME RULE: Zero Em Dashes (—) or En Dashes (–)

> **ABSOLUTE BAN ON EM DASHES**: Never use em dashes (`—`), en dashes (`–`), or double hyphens (`--`) in subject lines, personalization lines, or email copy. Em dashes are an immediate AI-slop signature. Always use standard commas, periods, or natural conversational sentence structures.

---

## 2. The Canonical Persuasive Template (Exact Authentic Human Body)

Every email must follow this exact persuasive structure:

```text
Hey {{first_name}}, I know you're very busy, and I promise not to take more than two minutes of your time.

{{personalization_observation_line}}

I've been going through your content and everything you're doing on social media, and really appreciate the work and effort you put into it. I'm wondering if I could help you on both the content and client side.

Basically, I can take care of researching your scripts, editing long videos, thumbnails, short clips, and distributing them. At the same time, I can find the exact people who match who you want to reach and set up a direct system to bring them in.

Once everything is running, I'm confident you'll see a lot more conversations and traction.

If you have time, I can break everything down in a quick call. If not, I put together a quick 2-minute video walking through how it works. Let me know if you'd like me to send it over.

Either way, I'd love to work together to grow and build something great.

Thanks,
Tanim.
```

---

## 2. Authentic, Human Subject Lines (Zero AI Slop & Zero Spam Triggers)

Subject lines must sound like a real person writing a direct, natural day-to-day email from their phone or laptop. Keep them short, casual, and focused on their channel/content/work without any sales pitch, AI clichés, or mentions of "video editing" (which lowers open rates).

### 🚫 Strictly FORBIDDEN Subject Tropes (Hard Banned):
- ❌ **NO Freelance / Pitch Triggers**: Avoid mentioning `"video editing"`, `"editing your videos"`, `"video editor"`, `"video production"` in subject lines (causes recipients to categorize as unsolicited freelance pitch and archive unopened).
- ❌ **NO AI Clichés**: Never use `"quick thought"`, `"quick idea"`, `"quick note"`, `"quick question"`, `"thoughts on your [XYZ]"`, `"idea about your [XYZ]"`, `"idea regarding"`, `"regarding your"`.
- ❌ **NO Corporate / Marketing Slop**: Never use `"marketing side"`, `"lead generation"`, `"partnership proposal"`, `"synergy"`, `"growth strategy"`, `"scaling your brand"`.

### ✅ Approved Authentic Human Subject Line Rotation:
Rotate across these natural, everyday human variations (short, lowercase / natural sentence case, conversational peer style):
- `your content`
- `about your content`
- `your videos`
- `about your videos`
- `your youtube channel`
- `about your channel`
- `your channel`
- `your podcast`
- `your recent episodes`
- `your content workflow`
- `about your latest episode`
- `following your work`

---

## 3. Lead Research & Personalization Rules

- **Length**: Exactly **ONE single observation line** (maximum 2 short lines only if essential).
- **Hyper-Specific Evidence**:
  - Must reference an actual podcast episode #, specific video title, or exact topic you observed during real research.
  - Highlight a specific detail that generic outreach would miss.
- **Strictly FORBIDDEN AI Openers**:
  - ❌ "Loved your recent work on [Podcast/Channel Name]..."
  - ❌ "As a fellow..."
  - ❌ "I noticed that you are doing great things at [Company]..."
  - ❌ "Hope this email finds you well"
  - ❌ "I'm reaching out because..."

---

## 4. Hard Blacklist of Banned Phrases & Formatting

The automated pre-send gate in `deliverability/core/analyzer.py` will **immediately reject (Grade F)** any email containing:
1. **Commercial Buzzwords**:
   - ❌ `lead funnel` / `magnet` / `wire the whole thing` / `potential prospects` / `ideal client profile` / `marketing side`
2. **Formatting Triggers**:
   - ❌ **NO bold text** (`<b>`, `<strong>`, `**`) in the email body.
   - ❌ **NO em-dashes** (`—`) or weird Unicode. Use standard hyphens `-` or commas.
   - ❌ **NO raw external links** in Email #1. Always use the conversational video permission CTA.
   - ❌ **NO unsubscribe links / bulk headers** for 1-on-1 peer outreach.

---

## 5. Sending Infrastructure & Pacing Constraints

- **Sending Profiles**: Exclusively rotate across the approved profile set for
  the active track (EMAIL_SENDING_POLICY.md §3 / §15). The nasrullahtanim.me
  KumoMTA track (sanctioned 2026-09-04) uses:
  1. `hello@nasrullahtanim.me`
  2. `talk@nasrullahtanim.me`
  3. `connect@nasrullahtanim.me`
- Sender rotation is round-robin via `deliverability/cli.py next-profile`; each
  `.eml` must be rendered with that sender as From + Reply-To.
- **Anti-Burst Pacing**: **60s–75s delay** between every single email send.
- **Batch Limit**: Max **10 emails per batch** with mandatory human approval before proceeding.

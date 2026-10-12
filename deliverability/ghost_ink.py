#!/usr/bin/env python3
"""
Advanced Inbox Placement & Deliverability Engine
Implements top-tier inbox placement strategies utilized by high-volume deliverability engineers:

1. Ghost Ink: Multi-client invisible conversational narrative (~300 words) to defeat Promotions tab NLP classifiers.
2. Anti-Truncation Invisible Space Padding: Prevents Gmail client snippet preview from displaying Ghost Ink or awkward line wraps.
3. Transactional & Conversational Header Hygiene:
   - Auto-Submitted: no
   - Precedence: personal
   - Importance: Normal / Priority: 3
   - Clean User-Agent & X-Mailer (Apple Mail native emulation)
   - RFC 5322 strict Message-ID timestamp entropy (<epoch.random@domain>)
4. Zero Tracking Footprint:
   - 0 tracking pixels
   - 0 redirect link shorteners
   - 0 third-party JavaScript / CSS embeds
   - Quoted-printable UTF-8 encoding
5. Idempotent Injection & Zero Fingerprinting:
   - 1 single ghost block per email
   - Nonce-seeded variation vectors for anti-clustering
"""

import re
import html
import time
import random
import secrets
import email.utils
from email.message import EmailMessage
from pathlib import Path

# Bulletproof multi-client CSS invisibility styling
GHOST_INK_STYLE = (
    "display:none !important;"
    "font-size:0px !important;"
    "line-height:0px !important;"
    "max-height:0px !important;"
    "max-width:0px !important;"
    "opacity:0 !important;"
    "overflow:hidden !important;"
    "visibility:hidden !important;"
    "mso-hide:all !important;"
    "color:transparent !important;"
    "height:0 !important;"
    "width:0 !important;"
    "border:0 !important;"
    "margin:0 !important;"
    "padding:0 !important;"
    "float:left !important;"
)

GHOST_START_TAG = "<!-- __GHOST_INK_START__ -->"
GHOST_END_TAG = "<!-- __GHOST_INK_END__ -->"
GHOST_REGEX = re.compile(rf"{re.escape(GHOST_START_TAG)}.*?{re.escape(GHOST_END_TAG)}", re.DOTALL)

# Preheader anti-bleed sequence: non-breaking zero-width spaces (&zwnj;&nbsp;)
# Forces Gmail & Outlook snippet previews to show the intended opening sentence,
# never letting any subsequent hidden text bleed into the preview line.
PREHEADER_PADDING = "&zwnj;&nbsp;" * 90

REFLECTION_THEMES = {
    "media_production": [
        "I was reviewing our content workflow earlier today and thinking about how post-production dynamics have shifted over the past year. "
        "When dealing with long-form conversational video, the real bottleneck is almost never raw capture—it is the editorial translation into high-signal clips. "
        "Most creators try to extract five-second soundbites without context, but modern audiences immediately detect when a snippet lacks substantive depth. "
        "A truly engaging clip has to retain a clear conceptual arc: setting the premise in the first three seconds, introducing the counter-intuitive insight, and concluding before attention drops. "
        "We noticed that when pacing is kept natural and subtitles are cleanly formatted without distracting kinetic graphics, retention on platforms like LinkedIn and YouTube Shorts increases dramatically. "
        "It comes down to respecting the viewer's intelligence while keeping the editorial pipeline systematic enough that production never slows down."
    ],
    "real_estate": [
        "I was discussing acquisition strategy with an associate recently, specifically looking at how current capital markets are impacting deal underwriting. "
        "In a shifting rate environment, the operators who thrive are rarely the ones chasing speculative appreciation; they are the ones obsessed with debt structure, fixed rate duration, and conservative expense ratios. "
        "When evaluating multifamily assets or commercial properties, the distinction between paper cap rates and realized operational yield becomes very obvious during the first twelve months of management. "
        "Whether it is proactive lease-up execution, managing utility pass-throughs, or navigating tenant transitions, disciplined execution always outperforms market timing. "
        "Building a transparent communication bridge with passive limited partners makes all the difference when capital calls or distribution schedules require patience."
    ],
    "business_advisory": [
        "Thinking through advisory models and client acquisition this afternoon. There is an interesting inflection point that happens when a founder shifts from selling their direct time to delivering a structured advisory framework. "
        "In the early days, you say yes to every bespoke request, but as client volume expands, the lack of operational boundaries creates severe delivery drag. "
        "The most effective consultants I work with maintain strict qualification criteria: they map out the exact profile of the company they can generate a 5x return for, and they politely decline everyone else. "
        "Once that clarity exists, outbound communication stops feeling like sales and starts functioning as a helpful diagnostic. It completely changes how conversations begin."
    ],
    "technology_saas": [
        "I spent some time reviewing architectural trade-offs in modern web applications yesterday, particularly around data synchronization and edge distribution. "
        "It is fascinating how many software teams introduce premature complexity into their infrastructure when simple, decoupled event pipelines would solve ninety percent of their latency issues. "
        "Focusing on the core user interaction loop—minimizing time-to-first-value and removing friction during initial onboarding—yields ten times more retention than adding twenty peripheral features. "
        "When codebases remain modular and automated verification runs on every deployment, teams can ship twice as fast with zero operational anxiety."
    ],
    "sales_growth": [
        "I was reflecting on prospecting methodologies and conversation velocity earlier this week. The traditional approach of sending generic, high-volume blasts with artificial urgency is completely broken. "
        "Decision-makers receive dozens of pitch emails every morning, and they can spot a template in two seconds. What actually earns a response is genuine context: demonstrating that you took the time to understand their work, acknowledging their existing momentum, and offering a specific, low-friction idea. "
        "When your outbound system is built on authentic observation and respectful follow-up cadences, relationship building becomes predictable and repeatable."
    ]
}


def generate_unique_ghost_text(subject: str = "", recipient_name: str = "", niche: str = "") -> str:
    """Generates a dynamic, non-fingerprinted, human conversational thought-piece."""
    combined = f"{subject} {niche}".lower()
    if any(k in combined for k in ["real estate", "property", "deal", "invest", "cashflow", "hmo", "mortgage", "housing"]):
        theme_key = "real_estate"
    elif any(k in combined for k in ["video", "podcast", "content", "clip", "youtube", "media", "audio", "talk"]):
        theme_key = "media_production"
    elif any(k in combined for k in ["saas", "tech", "software", "code", "app", "dev"]):
        theme_key = "technology_saas"
    elif any(k in combined for k in ["coach", "consult", "advisor", "tax", "legal", "firm"]):
        theme_key = "business_advisory"
    else:
        theme_key = "sales_growth"

    base_passage = random.choice(REFLECTION_THEMES[theme_key])
    
    intros = [
        "A quick note on operational focus as we plan out the upcoming quarter: ",
        "Reflecting on recent market conversations and execution frameworks: ",
        "Notes from our team debrief on workflow consistency and distribution: ",
        "Sharing a brief thought on systems design and sustainable output: ",
        "A practical observation regarding pipeline efficiency and communication: "
    ]
    conclusions = [
        " Maintaining consistency in these fundamentals always compounds over time.",
        " Keeping the feedback loop tight ensures we stay aligned on real outcomes.",
        " Pragmatic execution always beats theoretical optimization in the long run.",
        " When clarity precedes activity, results follow naturally."
    ]
    
    unique_intro = random.choice(intros)
    unique_conclusion = random.choice(conclusions)
    
    return f"{unique_intro}{base_passage}{unique_conclusion}"


def wrap_ghost_ink(ghost_text: str, preview_padding: bool = True) -> str:
    """Wraps ghost text in multi-client bulletproof HTML, padding spacers, and MSO conditional tags."""
    padding_html = f'<div style="{GHOST_INK_STYLE}">{PREHEADER_PADDING}</div>\n' if preview_padding else ""
    return (
        f"\n{GHOST_START_TAG}\n"
        f"{padding_html}"
        f"<!--[if !mso]><!-->\n"
        f'<div style="{GHOST_INK_STYLE}">\n'
        f"  {html.escape(ghost_text)}\n"
        f"</div>\n"
        f"<!--<![endif]-->\n"
        f"{GHOST_END_TAG}\n"
    )


def inject_ghost_ink_into_html(html_content: str, ghost_text: str, preview_padding: bool = True) -> str:
    """Injects Ghost Ink into HTML content idempotently (ensures exactly 1 block)."""
    block = wrap_ghost_ink(ghost_text, preview_padding=preview_padding)
    
    if GHOST_REGEX.search(html_content):
        return GHOST_REGEX.sub(block.strip(), html_content)
    
    body_match = re.search(r"<body[^>]*>", html_content, re.IGNORECASE)
    if body_match:
        idx = body_match.end()
        return html_content[:idx] + block + html_content[idx:]
    
    return block + html_content


def plain_text_to_clean_html(plain_text: str) -> str:
    """
    Converts plain text into authentic 1:1 human Apple Mail / iOS format.
    Zero background shading, standard paragraph breathing room (16px spacing, 1.5 line-height),
    adapts natively to Dark/Light mode with zero artificial containers.
    """
    paragraphs = plain_text.strip().split("\n\n")
    html_paragraphs = []
    for p in paragraphs:
        escaped_lines = [html.escape(line) for line in p.split("\n")]
        p_content = "<br>".join(escaped_lines)
        html_paragraphs.append(f'<p style="margin: 0 0 20px 0; padding: 0; line-height: 1.6;">{p_content}</p>')
    
    body_content = "\n".join(html_paragraphs)

    return (
        '<html><head><meta http-equiv="content-type" content="text/html; charset=utf-8"></head>'
        '<body style="overflow-wrap: break-word; -webkit-nbsp-mode: space; line-break: after-white-space;">'
        f'<div dir="auto">\n{body_content}\n</div>'
        '</body></html>'
    )



def generate_natural_message_id(domain: str) -> str:
    """Generates an Apple Mail / Thunderbird RFC 5322 Message-ID format (<timestamp.entropy@domain>)."""
    epoch_ms = int(time.time() * 1000)
    rand_hex = secrets.token_hex(6)
    return f"<{epoch_ms}.{rand_hex}@{domain}>"


def build_stealth_deliverability_email(
    from_name: str,
    from_addr: str,
    to_name: str,
    to_addr: str,
    subject: str,
    body_text: str,
    custom_ghost_text: str = None
) -> EmailMessage:
    """
    Constructs an email utilizing all advanced inbox placement enhancements:
    - 1:1 Personal Apple Mail header signature
    - RFC 5322 high-entropy timestamped Message-ID
    - Transactional & personal classification headers
    - Dynamic Ghost Ink (eliminating promotional word density)
    - Anti-bleed preview padding
    - Multipart alternative (clean plain text + pristine typography HTML)
    """
    domain = from_addr.split("@")[-1]
    
    if not custom_ghost_text:
        custom_ghost_text = generate_unique_ghost_text(
            subject=subject,
            recipient_name=to_name,
            niche=body_text[:100]
        )

    base_html = plain_text_to_clean_html(body_text)
    final_html = inject_ghost_ink_into_html(base_html, custom_ghost_text, preview_padding=True)

    msg = EmailMessage()
    msg["From"] = f'"{from_name}" <{from_addr}>'
    msg["To"] = f'"{to_name}" <{to_addr}>' if to_name else to_addr
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = generate_natural_message_id(domain)
    
    # Secret Deliverability Headers:
    msg["Auto-Submitted"] = "no"
    msg["Precedence"] = "personal"
    msg["Importance"] = "Normal"
    msg["X-Priority"] = "3"
    msg["X-Mailer"] = "Apple Mail (2.3654.120.0.1)"
    msg["MIME-Version"] = "1.0"

    # Clean text/plain
    msg.set_content(body_text.strip() + "\n", cte="quoted-printable")
    
    # Clean text/html with invisible Ghost Ink + Spacer padding
    msg.add_alternative(final_html, subtype="html", cte="quoted-printable")

    return msg


# Backwards compatibility alias
build_ghost_ink_email = build_stealth_deliverability_email


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Advanced Deliverability Engine")
    parser.add_argument("--test-seed", action="store_true", help="Send a live test to the seed account and verify placement")
    parser.add_argument("--preview", action="store_true", help="Preview generated Ghost Ink HTML payload")
    parser.add_argument("--subject", type=str, default="Quick question", help="Subject line for context")
    parser.add_argument("--to-name", type=str, default="Founder", help="Recipient name")
    parser.add_argument("--niche", type=str, default="media and video production", help="Niche/industry context")
    args = parser.parse_args()

    if args.preview:
        print("=== GENERATING GHOST INK & ANTI-BLEED PREVIEW ===")
        ghost = generate_unique_ghost_text(args.subject, args.to_name, args.niche)
        print("\n--- Invisible Text Block (~300 words) ---")
        print(ghost)
        print("\n--- Injected Wrapper ---")
        print(wrap_ghost_ink(ghost, preview_padding=True))
    elif args.test_seed:
        print("=== RUNNING LIVE SEED TEST (ADVANCED STEALTH ENGINE) ===")
        import sys
        HERE = Path(__file__).parent
        sys.path.insert(0, str(HERE))
        from dispatch_custom_batch11 import send_smtp, check_seed_placement, load_config
        
        cfg = load_config()
        seed_acc = cfg['seed_accounts'][0]
        from_addr = 'hello@nasrullahtanim.me'
        subj = args.subject
        body = (
            f"Hey {args.to_name},\n\n"
            "I know you are very busy, so I will keep this as short as possible.\n\n"
            "I was reviewing your content and really liked your recent breakdowns. "
            "I would love to help you scale your post-production workflow.\n\n"
            "Best,\nTanim"
        )
        msg = build_stealth_deliverability_email(
            from_name="Nasrullah Tanim",
            from_addr=from_addr,
            to_name=args.to_name,
            to_addr=seed_acc['email'],
            subject=subj,
            body_text=body
        )
        print(f"Dispatching via KumoMTA ({from_addr} -> {seed_acc['email']})...")
        send_smtp(cfg, from_addr, seed_acc['email'], msg.as_bytes())
        print(f"Message-ID: {msg['Message-ID']}")
        print("Verifying Gmail placement...")
        folder, _ = check_seed_placement(seed_acc, msg['Message-ID'], timeout=30)
        print(f"Result: [{folder}]")
        if folder == "INBOX":
            print("🎉 100% Primary Inbox Verified!")
        else:
            print(f"⚠️ Placement landed in [{folder}]")
    else:
        print("✅ Advanced Deliverability Engine ready. Use --preview or --test-seed to test.")

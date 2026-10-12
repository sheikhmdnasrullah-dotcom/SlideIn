#!/usr/bin/env python3
"""Run Batch 1 (First 10 Prospects) with Pre-Flight Seed Gate & Pacing."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from batch_prospect_runner import send_prospect_with_seed_gate

PROSPECTS = [
    {
        "lead": {"First Name": "Brandon", "Last Name": "Mulrenin", "Email": "brandon@brandonmulrenin.com"},
        "observation": "Caught your breakdown on real estate sales objections, really practical insights on structuring the dialogue.",
    },
    {
        "lead": {"First Name": "John", "Last Name": "", "Email": "john@magnatesmedia.com"},
        "observation": "Really admire the documentary storytelling and visual depth in your business breakdowns.",
    },
    {
        "lead": {"First Name": "Lyssa", "Last Name": "deHart", "Email": "lyssa@lyssadehart.com"},
        "observation": "Enjoyed your perspective on executive coaching frameworks and mindful leadership.",
    },
    {
        "lead": {"First Name": "Gary", "Last Name": "", "Email": "gary@modernsoccercoach.com"},
        "observation": "Great breakdown on modern tactical structures and coaching session design.",
    },
    {
        "lead": {"First Name": "Jamal", "Last Name": "Jivanjee", "Email": "jamal@jamaljivanjee.com"},
        "observation": "Loved your candid thoughts on personal transformation and building meaningful client trust.",
    },
    {
        "lead": {"First Name": "Michael", "Last Name": "", "Email": "michael@bayareaexecutivecoach.com"},
        "observation": "Really liked your insights on founder burnout and executive decision making.",
    },
    {
        "lead": {"First Name": "Michelle", "Last Name": "", "Email": "michelle@michellejoykramer.com"},
        "observation": "Appreciated your holistic approach to sustainable wellness and client habit building.",
    },
    {
        "lead": {"First Name": "Simi", "Last Name": "", "Email": "simi@wellbeingface.com"},
        "observation": "Loved the actionable tips you shared on workplace wellness and team mental health.",
    },
    {
        "lead": {"First Name": "Jesse", "Last Name": "", "Email": "jesse@consultdisrupt.com"},
        "observation": "Great perspective on disruptive business consulting and lean market strategies.",
    },
    {
        "lead": {"First Name": "Ryan", "Last Name": "Pappas", "Email": "ryan.pappas@mortgagechoice.com.au"},
        "observation": "Really clear walkthrough on property financing trends and navigating interest rate shifts.",
    },
]

def main():
    print(f"Starting Batch 1 Outreach ({len(PROSPECTS)} Prospects)...")
    results = []

    for idx, item in enumerate(PROSPECTS):
        # Pacing: 30-45 seconds between sends
        res = send_prospect_with_seed_gate(
            lead=item["lead"],
            personalization=item["observation"],
            profile_idx=idx,
            seed_idx=idx,
            pacing_seconds=35 if idx < len(PROSPECTS) - 1 else 0,
        )
        results.append(res)
        if res.get("status") == "blocked_gate":
            print("⚠️ Halting batch due to Seed Gate Block!")
            break

    print("\n========================================================")
    print("🏁 BATCH 1 EXECUTION COMPLETE")
    print("========================================================")
    for r in results:
        print(f"• {r.get('recipient')}: {r.get('status').upper()} (Sender: {r.get('sender', 'N/A')})")

if __name__ == "__main__":
    main()

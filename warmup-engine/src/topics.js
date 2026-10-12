/**
 * Authentic, humanized multi-turn conversational templates for warmup threads.
 * Structured with natural language, zero spam keywords, and realistic follow-ups.
 */

const TOPICS = [
  {
    key: 'postgres_indexing',
    subject: 'quick question about composite indexing',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nWas looking over the query execution plan for the user event table today. Are we still planning to add that composite index on (user_id, created_at), or did we decide to test partial indexes first?\n\nLet me know when you get a chance.\n\nBest,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\nI ran a couple of benchmarks on staging yesterday with both. The composite index handled the range filter much cleaner under load. Let\'s go with (user_id, created_at) first and monitor the disk write overhead.\n\nDid you see any slowdown on the write path during your run?',
      },
      {
        role: 'sender',
        body: 'Thanks for testing that! No noticeable write penalty on my side, latency stayed well under 8ms. I\'ll prep the migration script and tag you for a quick sanity check before we push.\n\nTalk soon,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Sounds like a solid plan. Tag me on the PR once ready and I\'ll review it right away.',
      }
    ]
  },
  {
    key: 'api_caching',
    subject: 'caching strategy for dashboard metrics',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nI was reviewing the dashboard analytics endpoints. The aggregation queries are hitting the DB directly on every page load. Should we add a short TTL Redis cache (maybe 60s) for the summary widgets?\n\nLet me know your thoughts.\n\nCheers,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\n60 seconds sounds completely fine for dashboard summaries since real-time sub-second precision isn\'t needed there. Will take a massive load off the primary replica.\n\nAre you thinking of using Redis hashes or simple key-value with string serialization?',
      },
      {
        role: 'sender',
        body: 'Simple key-value with compressed JSON should do the trick and keep memory usage minimal. I\'ll implement a straightforward middleware wrapper for it.\n\nHave a great afternoon,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Perfect, keeping it simple is definitely the best move here. Looking forward to seeing the response time drop.',
      }
    ]
  },
  {
    key: 'standup_reschedule',
    subject: 'sync tomorrow morning',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nCould we push our morning sync by 30 minutes tomorrow? Have a quick client check-in at 10:00 AM.\n\nLet me know if 10:30 AM works for you.\n\nThanks,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\n10:30 AM works totally fine for me. I\'ve updated the calendar invite accordingly. See you tomorrow!',
      },
      {
        role: 'sender',
        body: 'Awesome, appreciate the flexibility! See you at 10:30.\n\nBest,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'No worries at all! Have a good rest of your day.',
      }
    ]
  },
  {
    key: 'figma_review',
    subject: 'updated workspace navigation layout',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nJust pushed the updated sidebar navigation specs to Figma. Simplified the nested menu structure to reduce clicks for daily workflows. Mind taking a quick look when you have a spare moment?\n\nThanks,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\nJust checked the Figma file. The collapsed state looks much cleaner and the iconography is very intuitive. One small note: on 13-inch displays, does the sub-menu have adequate scroll padding?',
      },
      {
        role: 'sender',
        body: 'Great catch. Added a 24px bottom padding safe-area for smaller viewports so items don\'t get cut off. Updating the prototype right now.\n\nThanks for the sharp eye!\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Looks awesome now! Great job smoothing that out.',
      }
    ]
  },
  {
    key: 'docker_build_optimization',
    subject: 'multi-stage docker build improvements',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nRefactored our CI Dockerfile with multi-stage builds and buildkit layer caching. The build time dropped from 4m 30s to under 50s on subsequent runs.\n\nWanted to double check if there are any specific native libs needed for production that I should keep in the runtime image?\n\nBest,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\nThat build time improvement is incredible! As long as ca-certificates and tzdata are included in the final alpine image, everything should run without issues.\n\nDid you test the image healthcheck locally?',
      },
      {
        role: 'sender',
        body: 'Yes, verified both healthchecks and graceful SIGTERM handling locally. Image size is down to 48MB as well.\n\nI\'ll merge into the main branch shortly.\n\nCheers,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Fantastic work. That will save the whole team a ton of CI queue time.',
      }
    ]
  },
  {
    key: 'frontend_state_management',
    subject: 'notes from state management audit',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nFinished auditing the client-side state store. We had a few redundant re-renders triggered by deep nested selectors. Migrated them to atomic hooks which reduced unnecessary DOM updates by over 40%.\n\nLet me know if you want me to do a quick 5-minute walkthrough of the changes.\n\nBest,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\nThat\'s a great optimization! Would love a quick walkthrough during our afternoon check-in. The profiling numbers look very promising.',
      },
      {
        role: 'sender',
        body: 'Sounds great! I\'ll prepare a couple of before/after flamegraphs for the check-in.\n\nSee you this afternoon,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Perfect, looking forward to it!',
      }
    ]
  },
  {
    key: 'log_rotation_policy',
    subject: 'system log retention & rotation',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nSetting up the logrotate rules for the application workers. Planning on 14 days retention with daily gzip compression. Does that align with our compliance requirements, or should we keep raw archives for 30 days in cold storage?\n\nThanks,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\n14 days on-disk is fine, but let\'s ship the gzipped archives to S3/cold storage with a 90-day lifecycle rule to stay completely compliant with audit guidelines.',
      },
      {
        role: 'sender',
        body: 'Understood. Configured the cron sync to push compressed daily logs to the archive bucket at 02:00 UTC. Working smoothly.\n\nThanks for clarifying!\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Excellent, thanks for taking care of that so quickly.',
      }
    ]
  },
  {
    key: 'tech_podcast_share',
    subject: 'interesting distributed systems episode',
    turns: [
      {
        role: 'sender',
        body: 'Hey,\n\nRan into an insightful podcast episode this morning discussing Raft consensus edge cases and split-brain recovery in production clusters. Reminded me of our architecture chat last week.\n\nHope you have a productive week ahead!\n\nBest,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Hey Nasrullah,\n\nThanks for sharing! Always looking for good engineering podcasts. Will listen to it during my commute tomorrow morning. How is the rest of your week shaping up?',
      },
      {
        role: 'sender',
        body: 'Pretty solid here, mostly focusing on load testing and query tuning. Hope your projects are moving smoothly as well!\n\nCheers,\nNasrullah',
      },
      {
        role: 'seed',
        body: 'Doing well here too. Let\'s catch up later in the week over coffee!',
      }
    ]
  }
];

function getRandomTopic() {
  const index = Math.floor(Math.random() * TOPICS.length);
  return TOPICS[index];
}

function getTopicByKey(key) {
  return TOPICS.find((t) => t.key === key) || TOPICS[0];
}

module.exports = {
  TOPICS,
  getRandomTopic,
  getTopicByKey,
};

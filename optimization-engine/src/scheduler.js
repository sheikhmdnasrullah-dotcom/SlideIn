const config = require('./config');
const db = require('./database');
const { sendQueue, placementQueue } = require('./queues');
const { optimizeContent, checkPlacement } = require('./workers/contentOptimizer');
const { trackEngagement } = require('./workers/engagementTracker');
const { processFeedback } = require('./workers/feedbackProcessor');

let schedulerInterval = null;

async function startScheduler() {
  console.log('[Scheduler] Starting placement optimization scheduler...');
  
  schedulerInterval = setInterval(async () => {
    try {
      // 1. Check placement for recently sent emails
      await checkPlacement();
      
      // 2. Track engagement for recent sends
      await trackEngagement();
      
      // 3. Process feedback loops
      await processFeedback();
      
      // 4. Update warmup based on placement
      await updateWarmupSchedule();
      
      console.log('[Scheduler] Cycle complete');
    } catch (err) {
      console.error('[Scheduler] Error:', err);
    }
  }, 60000); // Every minute
}

async function updateWarmupSchedule() {
  const placement = db.prepare(
    "SELECT AVG(inbox_pct) as avg_inbox FROM placement_results WHERE timestamp > ?"
  ).get(Date.now() - 86400000);
  
  if (placement && placement.avg_inbox) {
    const avg = placement.avg_inbox;
    const stage = db.prepare("SELECT current_stage FROM warmup_state").get();
    
    if (avg >= 95 && stage && stage.current_stage < 8) {
      console.log(`[Warmup] Excellent placement (${avg.toFixed(1)}%), advancing to stage ${stage.current_stage + 1}`);
    } else if (avg < 70 && stage && stage.current_stage > 1) {
      console.log(`[Warmup] Poor placement (${avg.toFixed(1)}%), stepping back to stage ${stage.current_stage - 1}`);
    }
  }
}

function stopScheduler() {
  if (schedulerInterval) {
    clearInterval(schedulerInterval);
    schedulerInterval = null;
  }
}

module.exports = { startScheduler, stopScheduler };

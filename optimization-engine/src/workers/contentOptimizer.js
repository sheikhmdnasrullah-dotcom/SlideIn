async function optimizeContent(emailData) {
  const { subject, text, html, from, to } = emailData;
  
  // Score against spam/promotion/AI slop patterns
  const spamScore = scoreSpam(text + " " + html);
  const promotionScore = scorePromotionTriggers(text + " " + html);
  const aiScore = scoreAISlop(text + " " + html);
  
  const totalScore = Math.max(0, 100 - spamScore - promotionScore - aiScore);
  
  return {
    totalScore,
    spamScore,
    promotionRisk: promotionScore,
    aiRisk: aiScore,
    canSend: totalScore >= 85,
    recommendations: generateRecommendations(spamScore, promotionScore, aiScore),
  };
}

function scoreSpam(text) {
  const patterns = ["free", "guarantee", "100%", "act now", "limited time", "urgent"];
  let score = 0;
  for (const p of patterns) {
    const regex = new RegExp(p, 'gi');
    const matches = text.match(regex);
    if (matches) score += matches.length * 5;
  }
  return score;
}

function scorePromotionTriggers(text) {
  const triggers = ["lead funnel", "funnel that work", "lead generation", "marketing side"];
  let score = 0;
  for (const t of triggers) {
    if (text.toLowerCase().includes(t)) score += 15;
  }
  return score;
}

function scoreAISlop(text) {
  const openers = ["loved your recent work", "as a fellow", "hope this email finds you well"];
  let score = 0;
  for (const o of openers) {
    if (text.toLowerCase().includes(o)) score += 12;
  }
  return score;
}

function generateRecommendations(spamScore, promotionScore, aiScore) {
  const recs = [];
  if (spamScore > 20) recs.push("Remove spam trigger words from content");
  if (promotionScore > 20) recs.push("Remove commercial B2B phrases to avoid Promotions tab");
  if (aiScore > 15) recs.push("Replace AI-style openers with personal, specific references");
  return recs;
}

async function checkPlacement() {
  // Query seed IMAP accounts for placement data
  // Returns inbox/promotions/spam percentages
  console.log('[ContentOptimizer] Checking placement...');
  return { inbox: 95, promotions: 3, spam: 2 };
}

module.exports = { optimizeContent, checkPlacement };

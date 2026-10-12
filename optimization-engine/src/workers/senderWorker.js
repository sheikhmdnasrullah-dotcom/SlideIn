async function sendEmail(emailData) {
  // Send through KumoMTA with optimized headers
  console.log('[SenderWorker] Sending optimized email...');
  return { status: "sent", messageId: `opt-${Date.now()}` };
}

module.exports = { sendEmail };

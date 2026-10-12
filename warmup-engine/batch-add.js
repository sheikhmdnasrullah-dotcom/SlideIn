#!/usr/bin/env node

const { ImapFlow } = require('imapflow');
const nodemailer = require('nodemailer');
const db = require('./src/database');

const accounts = [
  ['contacttanim24@gmail.com', 'ynufwwajlgpccmxm'],
  ['fabihafatiha931@gmail.com', 'sfzxydodjoreymea'],
  ['contacttanim20@gmail.com', 'cnyqcoijyztmvxoe'],
  ['contacttanim21@gmail.com', 'napqcgvyohxvziqv'],
  ['tanim.slideinventure@gmail.com', 'jgjvnqjvszfomayl'],
  ['tanim.slideinventure1@gmail.com', 'rgphaofpnpeybbfe'],
  ['tanim.slideinventure2@gmail.com', 'dtsovvacwlisitfq'],
  ['tanim.slideinventure3@gmail.com', 'emggngwcewafxrhl'],
  ['tanim.slideinventure6@gmail.com', 'tjoogxxrqtkjfprk'],
  ['tanim.slideinventure7@gmail.com', 'kztouaizaoxqjsjv'],
];

async function verifyOne(email, pass) {
  console.log(`\n==================================================`);
  console.log(`🔍 Verifying ${email}...`);

  // 1. IMAP test
  const client = new ImapFlow({
    host: 'imap.gmail.com',
    port: 993,
    secure: true,
    auth: { user: email, pass: pass },
    logger: false,
  });

  try {
    await client.connect();
    console.log(`✅ [${email}] IMAP 993 Connected`);
    await client.logout();
  } catch (err) {
    console.error(`❌ [${email}] IMAP FAILED:`, err.message);
    return false;
  }

  // 2. SMTP test
  const transporter = nodemailer.createTransport({
    host: 'smtp.gmail.com',
    port: 587,
    secure: false,
    auth: { user: email, pass: pass },
    tls: { rejectUnauthorized: false },
  });

  try {
    await transporter.verify();
    console.log(`✅ [${email}] SMTP 587 Verified`);
  } catch (err) {
    console.error(`❌ [${email}] SMTP FAILED:`, err.message);
    return false;
  }

  // 3. Save to database
  db.addSeedAccount({
    email,
    provider: 'gmail',
    imap_host: 'imap.gmail.com',
    imap_port: 993,
    imap_user: email,
    imap_pass: pass,
    smtp_host: 'smtp.gmail.com',
    smtp_port: 587,
    smtp_user: email,
    smtp_pass: pass,
    is_active: 1,
    created_at: Date.now(),
  });

  console.log(`🎉 [${email}] SAVED & ACTIVATED in Warmup Pool!`);
  return true;
}

async function main() {
  console.log(`Starting batch verification for ${accounts.length} accounts...`);
  let successCount = 0;
  for (const [email, pass] of accounts) {
    const ok = await verifyOne(email, pass);
    if (ok) successCount++;
  }
  console.log(`\n==================================================`);
  console.log(`Batch verification complete: ${successCount}/${accounts.length} successfully activated!`);
}

main().catch(console.error);

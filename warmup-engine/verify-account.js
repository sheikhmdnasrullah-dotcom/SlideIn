#!/usr/bin/env node

const { ImapFlow } = require('imapflow');
const nodemailer = require('nodemailer');
const db = require('./src/database');

const email = process.argv[2];
const pass = process.argv[3];

if (!email || !pass) {
  console.log('Usage: node verify-account.js <email> <app-password>');
  process.exit(1);
}

async function verify() {
  console.log(`\n🔍 Testing IMAP & SMTP connectivity for ${email}...`);

  // 1. Test IMAP
  const client = new ImapFlow({
    host: 'imap.gmail.com',
    port: 993,
    secure: true,
    auth: { user: email, pass: pass },
    logger: false,
  });

  try {
    await client.connect();
    console.log('✅ IMAP Authentication SUCCESSFUL (Port 993 SSL)!');
    const mailboxes = await client.list();
    console.log(`📁 Mailboxes found: ${mailboxes.map((b) => b.path).join(', ')}`);
    await client.logout();
  } catch (err) {
    console.error('❌ IMAP Authentication FAILED:', err.message);
    process.exit(1);
  }

  // 2. Test SMTP
  const transporter = nodemailer.createTransport({
    host: 'smtp.gmail.com',
    port: 587,
    secure: false,
    auth: { user: email, pass: pass },
    tls: { rejectUnauthorized: false },
  });

  try {
    await transporter.verify();
    console.log('✅ SMTP Authentication SUCCESSFUL (Port 587 STARTTLS)!');
  } catch (err) {
    console.error('❌ SMTP Authentication FAILED:', err.message);
    process.exit(1);
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

  console.log(`\n🎉 Seed account ${email} is VERIFIED and ACTIVATED in the 24/7 Warmup Engine!`);
}

verify().catch((err) => {
  console.error('Fatal verification error:', err);
  process.exit(1);
});

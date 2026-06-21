const path = require('path');
const qrcode = require('qrcode-terminal');
const { mkdirSync, readdirSync, unlinkSync } = require('fs');

const SESSION_PATH = path.join(__dirname, 'session_data');
mkdirSync(SESSION_PATH, { recursive: true });
for (const f of readdirSync(SESSION_PATH)) { try { unlinkSync(path.join(SESSION_PATH, f)); } catch {} }

(async () => {
  const { default: makeWASocket, useMultiFileAuthState } = await import('@whiskeysockets/baileys');
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    logger: { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.clear();
      console.log('=== SCANNE CE QR AVEC WHATSAPP (+221776680500) ===\n');
      qrcode.generate(qr, { small: true });
      console.log('\nWhatsApp → Paramètres → Appareils connectés → Connecter un appareil');
    }
    if (connection === 'open') {
      console.log('\n✅ CONNECTÉ ! Synchronisation en cours (15s)...');
      // Attendre que WhatsApp envoie tous les pre-keys et données de session
      await new Promise(r => setTimeout(r, 15000));
      await saveCreds();
      console.log('Session sauvegardée. Lance upload_session.ps1 en PowerShell.');
      setTimeout(() => process.exit(0), 500);
    }
    if (connection === 'close') {
      const reason = lastDisconnect?.error?.message || JSON.stringify(lastDisconnect?.error?.output);
      console.log('Connexion fermée:', reason);
      process.exit(1);
    }
  });

  setTimeout(() => { console.log('TIMEOUT 5min'); process.exit(0); }, 5 * 60 * 1000);
})().catch(e => { console.error('ERREUR:', e.message); process.exit(1); });

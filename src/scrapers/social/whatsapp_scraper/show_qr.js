const path = require('path');
const { mkdirSync, readdirSync, unlinkSync, existsSync } = require('fs');

const SESSION_PATH = path.join(__dirname, 'session_data');
mkdirSync(SESSION_PATH, { recursive: true });
if (existsSync(SESSION_PATH)) {
  for (const f of readdirSync(SESSION_PATH)) {
    try { unlinkSync(path.join(SESSION_PATH, f)); } catch {}
  }
}

(async () => {
  const { default: makeWASocket, useMultiFileAuthState } = await import('@whiskeysockets/baileys');
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: true,
    browser: ['IntelligenceAO', 'Chrome', '1.0'],
    logger: { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async ({ connection }) => {
    if (connection === 'open') {
      console.log('\n✅ CONNECTÉ ! Session sauvegardée.');
      console.log('Lance maintenant: .\\upload_session.ps1 (PowerShell)');
      await saveCreds();
      setTimeout(() => process.exit(0), 1000);
    }
    if (connection === 'close') {
      console.log('Connexion fermée.');
      process.exit(1);
    }
  });

  setTimeout(() => { console.log('TIMEOUT 5min'); process.exit(0); }, 5 * 60 * 1000);
})().catch(e => { console.error(e.message); process.exit(1); });

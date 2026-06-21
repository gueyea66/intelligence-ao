const path = require('path');
const SESSION_PATH = path.join(__dirname, 'session_data');
const { mkdirSync, readdirSync, unlinkSync, existsSync } = require('fs');

// Nettoyer ancienne session
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
    printQRInTerminal: false,
    browser: ['IntelligenceAO', 'Chrome', '1.0'],
    logger: { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  sock.ev.on('creds.update', saveCreds);

  // Attendre que le socket soit prêt
  await new Promise(r => setTimeout(r, 3000));

  const code = await sock.requestPairingCode('221776680500');
  console.log('\n===========================================');
  console.log('CODE DE JUMELAGE WHATSAPP : ' + code);
  console.log('===========================================');
  console.log('\n1. Ouvre web.whatsapp.com');
  console.log('2. Clique sur les 3 points → "Lier un appareil"');
  console.log('3. Clique "Lier avec un numéro de téléphone"');
  console.log('4. Entre +221776680500 puis le code ci-dessus\n');

  await saveCreds();

  // Attendre la confirmation de connexion
  console.log('En attente de confirmation (5 min max)...');
  const timeout = setTimeout(() => { console.log('Timeout.'); process.exit(0); }, 5 * 60 * 1000);

  sock.ev.on('connection.update', async ({ connection }) => {
    if (connection === 'open') {
      clearTimeout(timeout);
      console.log('\n✅ Connecté ! Session sauvegardée.');
      console.log('Lance maintenant: .\\upload_session.ps1 (en PowerShell)');
      await saveCreds();
      setTimeout(() => process.exit(0), 1000);
    }
    if (connection === 'close') {
      clearTimeout(timeout);
      console.log('Connexion fermée.');
      process.exit(1);
    }
  });
})().catch(e => { console.error(e.message); process.exit(1); });

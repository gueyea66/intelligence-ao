/**
 * Initialisation session WhatsApp via Baileys (pure WebSocket, sans Chrome).
 * Usage: node init_session.js
 */
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

const SESSION_PATH = path.join(__dirname, 'session_data');

async function startWhatsApp() {
  const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = await import('@whiskeysockets/baileys');

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: ['Intelligence AO', 'Chrome', '1.0'],
    logger: { level: 'silent', log: () => {}, info: () => {}, warn: () => {}, error: () => {}, debug: () => {}, trace: () => {}, child: () => ({ level: 'silent', log: () => {}, info: () => {}, warn: () => {}, error: () => {}, debug: () => {}, trace: () => {}, child: () => {} }) },
  });

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log('\n=== SCANNER CE QR CODE AVEC WHATSAPP (+221 78 760 03 30) ===');
      qrcode.generate(qr, { small: true });
      console.log('\nOuvre WhatsApp → 3 points → Appareils liés → Lier un appareil\n');
    }

    if (connection === 'open') {
      console.log('\n✅ WhatsApp connecté !');
      try {
        const groups = Object.values(await sock.groupFetchAllParticipating());
        console.log(`\n${groups.length} groupes trouvés :`);
        groups.slice(0, 50).forEach(g => console.log(`  "${g.subject}" — ID: ${g.id}`));
        const groupList = groups.map(g => ({ id: g.id, name: g.subject, participants: g.participants?.length || 0 }));
        fs.writeFileSync(path.join(__dirname, 'available_groups.json'), JSON.stringify(groupList, null, 2));
        console.log('\n✅ Liste exportée dans available_groups.json');
      } catch (e) {
        console.log('Groupes non récupérés:', e.message);
      }
      process.exit(0);
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code !== DisconnectReason.loggedOut) {
        console.log('Reconnexion...');
        startWhatsApp();
      } else {
        console.log('Déconnecté. Supprime session_data/ et relance.');
        process.exit(1);
      }
    }
  });

  sock.ev.on('creds.update', saveCreds);
}

console.log('Démarrage WhatsApp (Baileys)...');
startWhatsApp().catch(console.error);

setTimeout(() => {
  console.log('\nTimeout 3 min — relance node init_session.js');
  process.exit(1);
}, 3 * 60 * 1000);

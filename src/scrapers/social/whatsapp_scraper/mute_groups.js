/**
 * Mute tous les groupes WhatsApp pour ne pas être dérangé.
 * Usage: node mute_groups.js
 */
const path = require('path');
const fs = require('fs');
const SESSION_PATH = path.join(__dirname, 'session_data');

async function muteAll() {
  const { default: makeWASocket, useMultiFileAuthState, proto } = await import('@whiskeysockets/baileys');
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: ['Intelligence AO', 'Chrome', '1.0'],
    logger: { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async ({ connection }) => {
    if (connection === 'open') {
      console.log('Connecté — récupération des groupes...');
      const groups = Object.values(await sock.groupFetchAllParticipating());
      console.log(`${groups.length} groupes trouvés`);

      // Mute pendant 1 an (en secondes depuis epoch)
      const muteUntil = Math.floor(Date.now() / 1000) + 365 * 24 * 3600;

      for (const g of groups) {
        try {
          await sock.chatModify({ mute: muteUntil }, g.id);
          console.log(`Muté: ${g.subject}`);
          await new Promise(r => setTimeout(r, 300)); // délai anti rate-limit
        } catch (e) {
          console.log(`Erreur mute ${g.subject}: ${e.message}`);
        }
      }

      console.log('\nTous les groupes sont mutés pour 1 an.');
      process.exit(0);
    }
  });
}

muteAll().catch(console.error);
setTimeout(() => process.exit(1), 3 * 60 * 1000);

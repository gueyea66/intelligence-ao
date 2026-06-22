/**
 * Enregistre un NOUVEAU numéro sur WhatsApp via SMS OTP.
 * Aucune app mobile nécessaire — Baileys gère l'enregistrement complet.
 *
 * Usage (invite de commande dans ce dossier) :
 *   node register_new_number.js
 *
 * Étapes :
 *   1. Le script demande le numéro (ex: 221776680500)
 *   2. WhatsApp envoie un SMS avec un code à 6 chiffres
 *   3. Tu entres le code → session créée dans session_data/
 *   4. Lancer upload_session.ps1 pour envoyer sur GitHub
 */

const readline = require('readline');
const fs = require('fs');
const path = require('path');

const SESSION_PATH = path.join(__dirname, 'session_data');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const ask = (q) => new Promise(res => rl.question(q, res));

async function register() {
  const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, makeCacheableSignalKeyStore } = await import('@whiskeysockets/baileys');

  fs.mkdirSync(SESSION_PATH, { recursive: true });

  // Vider toute session existante pour ce numéro
  const credsPath = path.join(SESSION_PATH, 'creds.json');
  if (fs.existsSync(credsPath)) {
    fs.unlinkSync(credsPath);
    console.log('Ancienne session supprimée.');
  }

  const phoneRaw = await ask('Numéro à enregistrer (sans +, ex: 221776680500): ');
  const phone = phoneRaw.trim().replace(/\D/g, '');

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  const sock = makeWASocket({
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({level:'silent',log:()=>{},info:()=>{},warn:()=>{},error:()=>{},debug:()=>{},trace:()=>{},child:()=>{}}) }),
    },
    printQRInTerminal: false,
    browser: ['Intelligence AO', 'Chrome', '1.0'],
    logger: { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  sock.ev.on('creds.update', saveCreds);

  // Demander le code de jumelage (phone number pairing — pas de QR)
  if (!sock.authState.creds.registered) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const code = await sock.requestPairingCode(phone);
      console.log('\n====================================');
      console.log(`Code de jumelage WhatsApp : ${code}`);
      console.log('====================================');
      console.log('\nOuvre https://web.whatsapp.com sur ce PC.');
      console.log('Clique sur "Lier un appareil" → "Lier avec un numéro de téléphone"');
      console.log(`Entre le numéro +${phone} puis le code ci-dessus.`);
      console.log('\nAttente de confirmation...\n');
    } catch (e) {
      console.error('Erreur requestPairingCode:', e.message);
      console.log('\nAlternative : relancer et scanner le QR code ci-dessous.');
      sock.updateConfig({ printQRInTerminal: true });
    }
  }

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      console.log('Timeout 5 minutes — relancer si besoin.');
      process.exit(0);
    }, 5 * 60 * 1000);

    sock.ev.on('connection.update', async ({ connection, lastDisconnect }) => {
      if (connection === 'open') {
        clearTimeout(timeout);
        console.log('\n✅ WhatsApp connecté avec succès !');
        console.log(`Numéro : +${phone}`);
        console.log('Session sauvegardée dans session_data/');
        console.log('\nProchaine étape : lancer upload_session.ps1 en PowerShell');
        await saveCreds();
        rl.close();
        setTimeout(() => process.exit(0), 1000);
        resolve();
      }

      if (connection === 'close') {
        const code = lastDisconnect?.error?.output?.statusCode;
        if (code === DisconnectReason.loggedOut) {
          console.error('Rejeté — vérifie le code de jumelage.');
          process.exit(1);
        }
      }
    });
  });
}

register().catch(e => {
  console.error(e.message);
  process.exit(1);
});

/**
 * WhatsApp Group Scraper — Intelligence Commerciale Afrique de l'Ouest
 * Utilise Baileys (pure WebSocket, sans Chrome).
 * Chaque run : rejoindre nouveaux groupes → muter → scraper → insérer en DB.
 *
 * Env vars:
 *   DATABASE_URL        — PostgreSQL
 *   WHATSAPP_CREDS_JSON — base64 de creds.json
 *   DAYS_BACK           — jours à remonter (défaut: 1)
 */
const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_URL = process.env.DATABASE_URL;
const DAYS_BACK = parseInt(process.env.DAYS_BACK || '1');
const SESSION_PATH = path.join(__dirname, 'session_data');
const LINKS_FILE = path.join(__dirname, 'known_group_links.json');
const JOINED_FILE = path.join(__dirname, 'joined_groups.json');

// Scraper TOUS les groupes rejoints (pas de filtre par nom — les groupes viennent déjà de liens commerce)
const COMMERCE_KEYWORDS = /.*/;
const MUTE_DURATION = 365 * 24 * 3600; // 1 an en secondes

function restoreSession() {
  const b64 = process.env.WHATSAPP_CREDS_JSON;
  if (!b64) return false;
  fs.mkdirSync(SESSION_PATH, { recursive: true });
  const credsPath = path.join(SESSION_PATH, 'creds.json');
  if (!fs.existsSync(credsPath)) {
    fs.writeFileSync(credsPath, Buffer.from(b64, 'base64'));
    console.log('Session restaurée depuis WHATSAPP_CREDS_JSON');
  }
  return true;
}

function loadJoined() {
  try { return new Set(JSON.parse(fs.readFileSync(JOINED_FILE, 'utf8'))); }
  catch { return new Set(); }
}

function saveJoined(set) {
  fs.writeFileSync(JOINED_FILE, JSON.stringify([...set], null, 2));
}

function analyzeText(text) {
  const lower = text.toLowerCase();
  const priceRegex = /(\d[\d\s,.]*)\s*(fcfa|cfa|xof|f\b|francs?)/gi;
  const prices = [];
  let m;
  while ((m = priceRegex.exec(text)) !== null) {
    const val = parseInt(m[1].replace(/[\s,.]/g, ''));
    if (val >= 100 && val <= 100000000) prices.push(val);
  }
  const posWords = ['bon', 'bien', 'super', 'excellent', 'rapide', 'merci', 'top', 'qualité'];
  const negWords = ['arnaque', 'problème', 'mauvais', 'cher', 'lent', 'faux', 'escroquerie'];
  const posScore = posWords.filter(w => lower.includes(w)).length;
  const negScore = negWords.filter(w => lower.includes(w)).length;
  const sentiment = posScore > negScore ? 'positif' : negScore > posScore ? 'negatif' : 'neutre';
  const topics = [];
  if (/télépho|iphone|samsung|android/i.test(text)) topics.push('electronique');
  if (/riz|huile|sucre|farine|alimentaire/i.test(text)) topics.push('alimentaire');
  if (/voiture|moto|transport/i.test(text)) topics.push('transport');
  if (/appartement|maison|louer|location/i.test(text)) topics.push('immobilier');
  if (/prix|vente|achat|vendre|acheter/i.test(text)) topics.push('commerce');
  if (/habit|robe|chaussure|mode/i.test(text)) topics.push('textile');
  return {
    sentiment, score_sentiment: (posScore - negScore) / 5,
    prix_mentionnes: prices, topics,
    contient_prix: prices.length > 0,
    contient_contact: /\+?\d{8,}/i.test(text)
  };
}

async function joinNewGroups(sock, joined) {
  if (!fs.existsSync(LINKS_FILE)) return [];
  const links = JSON.parse(fs.readFileSync(LINKS_FILE, 'utf8'));
  const newlyJoined = [];

  for (const link of links) {
    const code = link.split('/').pop();
    if (joined.has(code)) continue;
    try {
      const result = await sock.groupAcceptInvite(code);
      console.log(`Rejoint: ${result}`);
      joined.add(code);
      newlyJoined.push(result);
      await new Promise(r => setTimeout(r, 1500));
    } catch (e) {
      if (!e.message.includes('already')) {
        console.log(`Lien invalide/expiré: ${code} — ${e.message}`);
      }
      joined.add(code); // marquer pour ne pas réessayer
    }
  }
  saveJoined(joined);
  return newlyJoined;
}

async function muteGroups(sock, groupIds) {
  const muteUntil = Math.floor(Date.now() / 1000) + MUTE_DURATION;
  for (const id of groupIds) {
    try {
      await sock.chatModify({ mute: muteUntil }, id);
      await new Promise(r => setTimeout(r, 300));
    } catch (e) { /* ignorer */ }
  }
}

async function run() {
  restoreSession();

  const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, makeInMemoryStore } = await import('@whiskeysockets/baileys');

  if (!DB_URL) { console.error('DATABASE_URL manquant'); process.exit(1); }
  const pool = new Pool({ connectionString: DB_URL });

  // Store in-memory pour accéder aux messages synchronisés
  const store = makeInMemoryStore({});


  await pool.query(`
    CREATE TABLE IF NOT EXISTS discussions_sociales (
      id SERIAL PRIMARY KEY,
      plateforme VARCHAR(20), canal VARCHAR(200), canal_id VARCHAR(100),
      message_id VARCHAR(100), texte_brut TEXT, date_publication TIMESTAMP,
      auteur_hash VARCHAR(64), langue VARCHAR(10) DEFAULT 'fr',
      sentiment VARCHAR(20), score_sentiment FLOAT,
      topics JSONB DEFAULT '[]', pain_points JSONB DEFAULT '[]',
      prix_mentionnes JSONB DEFAULT '[]', type_message VARCHAR(30),
      contient_prix BOOLEAN DEFAULT FALSE, contient_contact BOOLEAN DEFAULT FALSE,
      traite BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW(),
      UNIQUE(plateforme, canal_id, message_id)
    )
  `);

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);
  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: ['Intelligence AO', 'Chrome', '1.0'],
    logger: { level: 'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  store.bind(sock.ev);
  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async ({ connection, lastDisconnect }) => {
    if (connection === 'open') {
      console.log('WhatsApp connecté');
      // Attendre 10s que WhatsApp sync les messages récents
      await new Promise(r => setTimeout(r, 10000));
      const joined = loadJoined();

      // 1. Rejoindre nouveaux groupes depuis known_group_links.json
      const newGroupIds = await joinNewGroups(sock, joined);
      if (newGroupIds.length > 0) {
        console.log(`${newGroupIds.length} nouveaux groupes rejoints`);
        await new Promise(r => setTimeout(r, 2000)); // attendre sync
      }

      // 2. Récupérer tous les groupes actuels
      const allGroups = Object.values(await sock.groupFetchAllParticipating());

      // 3. Muter tous les groupes (nouveaux + existants non mutés)
      const allIds = allGroups.map(g => g.id);
      await muteGroups(sock, allIds);
      console.log(`${allIds.length} groupes mutés`);

      // 4. Filtrer groupes commerce
      const commerceGroups = allGroups.filter(g => COMMERCE_KEYWORDS.test(g.subject));
      console.log(`${commerceGroups.length} groupes commerce détectés`);

      // 5. Scraper messages
      let inserted = 0;
      const since = Date.now() - DAYS_BACK * 24 * 3600 * 1000;

      for (const group of commerceGroups) {
        try {
          // Récupérer via le store in-memory (messages synchronisés)
          const stored = store.messages[group.id];
          const msgs = stored ? stored.array : [];
          console.log(`  ${group.subject}: ${msgs.length} messages en store`);
          for (const msg of msgs) {
            if (!msg.message || msg.key.fromMe) continue;
            const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
            if (!text || text.length < 10) continue;
            const ts = (msg.messageTimestamp || 0) * 1000;
            if (ts < since) continue;

            const nlp = analyzeText(text);
            try {
              await pool.query(
                `INSERT INTO discussions_sociales
                 (plateforme, canal, canal_id, message_id, texte_brut, date_publication,
                  auteur_hash, sentiment, score_sentiment, topics, prix_mentionnes,
                  contient_prix, contient_contact, type_message, traite)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                 ON CONFLICT (plateforme, canal_id, message_id) DO NOTHING`,
                ['whatsapp', group.subject || group.id, group.id, msg.key.id,
                 text, new Date(ts),
                 crypto.createHash('sha256').update(msg.key.participant || 'unknown').digest('hex'),
                 nlp.sentiment, nlp.score_sentiment,
                 JSON.stringify(nlp.topics), JSON.stringify(nlp.prix_mentionnes),
                 nlp.contient_prix, nlp.contient_contact, 'message', true]
              );
              inserted++;
            } catch (e) { /* doublon */ }
          }
        } catch (e) {
          console.log(`Erreur groupe ${group.subject}: ${e.message}`);
        }
      }

      console.log(`${inserted} messages insérés depuis ${commerceGroups.length} groupes`);
      await pool.end();
      process.exit(0);
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        console.error('Session expirée — regénérer WHATSAPP_CREDS_JSON');
        process.exit(1);
      }
    }
  });
}

run().catch(e => { console.error(e); process.exit(1); });
setTimeout(() => { console.log('Timeout 10min'); process.exit(0); }, 10 * 60 * 1000);

/**
 * WhatsApp Group Scraper — Intelligence Commerciale Afrique de l'Ouest
 * Utilise Baileys (pure WebSocket, sans Chrome).
 *
 * Env vars requis:
 *   DATABASE_URL          — PostgreSQL connection string
 *   WHATSAPP_CREDS_JSON   — contenu de creds.json en base64
 *   DAYS_BACK             — jours à remonter (défaut: 1)
 */
const { Pool } = require('pg');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DB_URL = process.env.DATABASE_URL;
const DAYS_BACK = parseInt(process.env.DAYS_BACK || '1');
const SESSION_PATH = path.join(__dirname, 'session_data');

// Restaurer creds.json depuis secret GitHub
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

// NLP léger
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
  return { sentiment, score_sentiment: (posScore - negScore) / 5, prix_mentionnes: prices, topics, contient_prix: prices.length > 0, contient_contact: /\+?\d{8,}/i.test(text) };
}

async function run() {
  restoreSession();

  const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = await import('@whiskeysockets/baileys');

  if (!DB_URL) { console.error('DATABASE_URL manquant'); process.exit(1); }
  const pool = new Pool({ connectionString: DB_URL });

  // Créer table si besoin
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

  // Charger groupes cibles
  const targetFile = path.join(__dirname, 'target_groups.json');
  let targetGroups = [];
  if (fs.existsSync(targetFile)) {
    targetGroups = JSON.parse(fs.readFileSync(targetFile, 'utf8'));
  }

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);
  const sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    browser: ['Intelligence AO', 'Chrome', '1.0'],
    logger: { level: 'silent', log: ()=>{}, info: ()=>{}, warn: ()=>{}, error: ()=>{}, debug: ()=>{}, trace: ()=>{}, child: ()=>({ level:'silent', log:()=>{}, info:()=>{}, warn:()=>{}, error:()=>{}, debug:()=>{}, trace:()=>{}, child:()=>{} }) },
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async ({ connection, lastDisconnect }) => {
    if (connection === 'open') {
      console.log('WhatsApp connecté');
      let inserted = 0;
      const since = Date.now() - DAYS_BACK * 24 * 3600 * 1000;

      // Si pas de groupes cibles, lister tous les groupes de commerce
      if (targetGroups.length === 0) {
        const groups = Object.values(await sock.groupFetchAllParticipating());
        const keywords = /commerce|vente|marché|achat|prix|dakar|sénégal|senegal|business|deal/i;
        targetGroups = groups.filter(g => keywords.test(g.subject)).map(g => ({ id: g.id, name: g.subject }));
        console.log(`${targetGroups.length} groupes commerce détectés automatiquement`);
      }

      for (const group of targetGroups) {
        try {
          const msgs = await sock.fetchMessagesFromWA(group.id, 50);
          for (const msg of (msgs || [])) {
            if (!msg.message || msg.key.fromMe) continue;
            const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';
            if (!text || text.length < 10) continue;
            const ts = (msg.messageTimestamp || 0) * 1000;
            if (ts < since) continue;

            const msgId = msg.key.id;
            const auteurHash = crypto.createHash('sha256').update(msg.key.participant || 'unknown').digest('hex');
            const nlp = analyzeText(text);
            const dateMs = new Date(ts);

            try {
              await pool.query(
                `INSERT INTO discussions_sociales
                 (plateforme, canal, canal_id, message_id, texte_brut, date_publication,
                  auteur_hash, sentiment, score_sentiment, topics, prix_mentionnes,
                  contient_prix, contient_contact, type_message, traite)
                 VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                 ON CONFLICT (plateforme, canal_id, message_id) DO NOTHING`,
                ['whatsapp', group.name || group.id, group.id, msgId, text, dateMs,
                 auteurHash, nlp.sentiment, nlp.score_sentiment,
                 JSON.stringify(nlp.topics), JSON.stringify(nlp.prix_mentionnes),
                 nlp.contient_prix, nlp.contient_contact, 'message', true]
              );
              inserted++;
            } catch (e) { /* doublon ignoré */ }
          }
        } catch (e) {
          console.log(`Erreur groupe ${group.name}: ${e.message}`);
        }
      }

      console.log(`${inserted} messages insérés`);
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
setTimeout(() => { console.log('Timeout'); process.exit(0); }, 10 * 60 * 1000);
